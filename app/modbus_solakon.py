"""Read-only Modbus TCP client for the Solakon ONE.

The register profile follows the public Solakon ONE Modbus protocol 02/26.
Only function code 03 (Read Holding Registers) is implemented deliberately.
"""

from __future__ import annotations

import math
import random
import socket
import struct
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Optional


class ModbusError(RuntimeError):
    """Raised for Modbus protocol or transport errors."""


@dataclass
class SolakonOneReading:
    model_name: Optional[str] = None
    serial_number: Optional[str] = None
    status: str = "Unbekannt"
    total_pv_power_w: Optional[float] = None
    active_power_w: Optional[float] = None
    battery_power_w: Optional[float] = None
    battery_soc_pct: Optional[float] = None
    load_power_w: Optional[float] = None
    meter_power_w: Optional[float] = None
    internal_temperature_c: Optional[float] = None
    grid_frequency_hz: Optional[float] = None
    power_factor: Optional[float] = None
    total_pv_energy_kwh: Optional[float] = None
    daily_pv_energy_kwh: Optional[float] = None
    battery_total_charge_kwh: Optional[float] = None
    battery_total_discharge_kwh: Optional[float] = None
    pv1_voltage_v: Optional[float] = None
    pv1_current_a: Optional[float] = None
    pv1_power_w: Optional[float] = None
    pv2_voltage_v: Optional[float] = None
    pv2_current_a: Optional[float] = None
    pv2_power_w: Optional[float] = None
    pv3_voltage_v: Optional[float] = None
    pv3_current_a: Optional[float] = None
    pv3_power_w: Optional[float] = None
    pv4_voltage_v: Optional[float] = None
    pv4_current_a: Optional[float] = None
    pv4_power_w: Optional[float] = None
    source: str = "Solakon ONE Modbus TCP"
    warnings: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModbusTcpConnection:
    """Small synchronous Modbus TCP connection supporting read-only FC03."""

    def __init__(self, host: str, port: int, unit_id: int, timeout: float):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._socket: Optional[socket.socket] = None
        self._transaction = 0
        self._lock = threading.Lock()

    def __enter__(self) -> "ModbusTcpConnection":
        try:
            self._socket = socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            )
            self._socket.settimeout(self.timeout)
        except OSError as exc:
            raise ModbusError(
                f"Verbindung zu {self.host}:{self.port} fehlgeschlagen: {exc}"
            ) from exc
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._socket:
            try:
                self._socket.close()
            finally:
                self._socket = None

    @staticmethod
    def _recv_exact(sock: socket.socket, length: int) -> bytes:
        chunks: list[bytes] = []
        remaining = length
        while remaining:
            chunk = sock.recv(remaining)
            if not chunk:
                raise ModbusError("Modbus-Verbindung wurde unerwartet geschlossen.")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def read_holding_registers(self, address: int, count: int) -> list[int]:
        if not (0 <= address <= 65535):
            raise ValueError("Registeradresse außerhalb des gültigen Bereichs.")
        if not (1 <= count <= 125):
            raise ValueError("Pro Modbus-Abfrage sind 1 bis 125 Register zulässig.")
        if not self._socket:
            raise ModbusError("Modbus-Verbindung ist nicht geöffnet.")

        with self._lock:
            self._transaction = (self._transaction + 1) & 0xFFFF
            if self._transaction == 0:
                self._transaction = 1
            transaction = self._transaction
            pdu = struct.pack(">BHH", 3, address, count)
            request = struct.pack(">HHHB", transaction, 0, len(pdu) + 1, self.unit_id) + pdu
            try:
                self._socket.sendall(request)
                header = self._recv_exact(self._socket, 7)
                rx_transaction, protocol, length, rx_unit = struct.unpack(">HHHB", header)
                if rx_transaction != transaction:
                    raise ModbusError("Ungültige Modbus-Transaktionsnummer.")
                if protocol != 0:
                    raise ModbusError("Ungültige Modbus-Protokollkennung.")
                if rx_unit != self.unit_id:
                    raise ModbusError("Antwort stammt von einer anderen Geräte-ID.")
                if length < 2:
                    raise ModbusError("Modbus-Antwort ist zu kurz.")
                pdu_response = self._recv_exact(self._socket, length - 1)
            except (OSError, socket.timeout) as exc:
                raise ModbusError(f"Modbus-Kommunikation fehlgeschlagen: {exc}") from exc

            function = pdu_response[0]
            if function == 0x83:
                code = pdu_response[1] if len(pdu_response) > 1 else -1
                explanations = {
                    1: "ungültige Funktion",
                    2: "ungültige Registeradresse",
                    3: "ungültiger Registerwert",
                    4: "Gerätefehler",
                    6: "Gerät beschäftigt",
                }
                raise ModbusError(
                    f"Modbus-Ausnahme {code}: {explanations.get(code, 'unbekannt')}"
                )
            if function != 3 or len(pdu_response) < 2:
                raise ModbusError("Unerwartete Modbus-Antwort.")
            byte_count = pdu_response[1]
            data = pdu_response[2:]
            if byte_count != count * 2 or len(data) != byte_count:
                raise ModbusError("Modbus-Antwort enthält eine falsche Datenlänge.")
            return list(struct.unpack(">" + "H" * count, data))


class SolakonOneReader:
    """Read the useful monitoring values from a Solakon ONE."""

    # Separate blocks keep requests within the official 125-register limit and
    # avoid very large gaps that some firmware versions reject.
    BLOCKS: tuple[tuple[int, int], ...] = (
        (30000, 32),   # alternative model and serial number block
        (39000, 78),   # protocol, model/SN, status and PV voltage/current
        (39118, 24),   # PV, inverter/grid values and temperature
        (39149, 4),    # generated energy
        (39162, 8),    # storage power and connected meter power
        (39219, 20),   # load and battery power
        (39279, 8),    # PV1..PV4 power
        (39424, 1),    # overall battery SOC
        (39601, 32),   # energy counters
    )

    def read(self, config: dict[str, Any]) -> SolakonOneReading:
        if config.get("simulation"):
            return self._simulate()

        host = str(config.get("host", "")).strip()
        if not host:
            raise ValueError("Keine IP-Adresse oder kein Hostname für Solakon ONE konfiguriert.")
        port = int(config.get("port", 502))
        unit_id = int(config.get("device_id", 1))
        timeout = float(config.get("timeout_seconds", 5))

        values: dict[int, int] = {}
        warnings: list[str] = []
        with ModbusTcpConnection(host, port, unit_id, timeout) as connection:
            for start, count in self.BLOCKS:
                try:
                    registers = connection.read_holding_registers(start, count)
                    values.update({start + index: value for index, value in enumerate(registers)})
                except ModbusError as exc:
                    warnings.append(f"Register {start}–{start + count - 1}: {exc}")

        if not values:
            raise ModbusError("Der Solakon ONE antwortet, aber es konnten keine Register gelesen werden.")
        if 30000 not in values and 39118 not in values and 39134 not in values:
            raise ModbusError("Keine erkennbaren Solakon-ONE-Register in der Antwort gefunden.")

        status_raw = self._u16(values, 39063)
        status = self._decode_status(status_raw)
        # Prefer the combined battery value so installations with an expansion
        # battery are represented correctly. Older firmware may expose only the
        # energy-storage-module or battery-1 register. All are read-only.
        battery_power = self._i32(values, 39237)
        if battery_power is None:
            battery_power = self._i32(values, 39162)
        if battery_power is None:
            battery_power = self._i32(values, 39230)

        reading = SolakonOneReading(
            model_name=self._string(values, 30000, 16) or self._string(values, 39002, 16),
            serial_number=self._string(values, 30016, 16) or self._string(values, 39018, 16),
            status=status,
            total_pv_power_w=self._scaled_i32(values, 39118, 1),
            active_power_w=self._scaled_i32(values, 39134, 1),
            battery_power_w=float(battery_power) if battery_power is not None else None,
            battery_soc_pct=self._scaled_i16(values, 39424, 1),
            load_power_w=self._scaled_i32(values, 39225, 1),
            meter_power_w=self._scaled_i32(values, 39168, 1),
            internal_temperature_c=self._scaled_i16(values, 39141, 10),
            grid_frequency_hz=self._scaled_i16(values, 39139, 100),
            power_factor=self._scaled_i16(values, 39138, 1000),
            total_pv_energy_kwh=(
                self._scaled_u32(values, 39601, 100)
                if self._u32(values, 39601) is not None
                else self._scaled_u32(values, 39149, 100)
            ),
            daily_pv_energy_kwh=(
                self._scaled_u32(values, 39603, 100)
                if self._u32(values, 39603) is not None
                else self._scaled_u32(values, 39151, 100)
            ),
            battery_total_charge_kwh=self._scaled_u32(values, 39605, 100),
            battery_total_discharge_kwh=self._scaled_u32(values, 39609, 100),
            pv1_voltage_v=self._scaled_i16(values, 39070, 10),
            pv1_current_a=self._scaled_i16(values, 39071, 100),
            pv1_power_w=self._scaled_i32(values, 39279, 1),
            pv2_voltage_v=self._scaled_i16(values, 39072, 10),
            pv2_current_a=self._scaled_i16(values, 39073, 100),
            pv2_power_w=self._scaled_i32(values, 39281, 1),
            pv3_voltage_v=self._scaled_i16(values, 39074, 10),
            pv3_current_a=self._scaled_i16(values, 39075, 100),
            pv3_power_w=self._scaled_i32(values, 39283, 1),
            pv4_voltage_v=self._scaled_i16(values, 39076, 10),
            pv4_current_a=self._scaled_i16(values, 39077, 100),
            pv4_power_w=self._scaled_i32(values, 39285, 1),
            warnings=" | ".join(warnings),
        )
        return reading

    def test(self, config: dict[str, Any]) -> SolakonOneReading:
        """Run the same read used for collection so the UI tests real registers."""
        return self.read(config)

    @staticmethod
    def _u16(values: dict[int, int], address: int) -> Optional[int]:
        return values.get(address)

    @staticmethod
    def _i16(values: dict[int, int], address: int) -> Optional[int]:
        value = values.get(address)
        if value is None:
            return None
        return value - 0x10000 if value > 0x7FFF else value

    @staticmethod
    def _u32(values: dict[int, int], address: int) -> Optional[int]:
        high = values.get(address)
        low = values.get(address + 1)
        if high is None or low is None:
            return None
        return (high << 16) | low

    @classmethod
    def _i32(cls, values: dict[int, int], address: int) -> Optional[int]:
        value = cls._u32(values, address)
        if value is None:
            return None
        return value - 0x100000000 if value > 0x7FFFFFFF else value

    @classmethod
    def _scaled_i16(cls, values: dict[int, int], address: int, scale: float) -> Optional[float]:
        value = cls._i16(values, address)
        return None if value is None else float(value) / scale

    @classmethod
    def _scaled_i32(cls, values: dict[int, int], address: int, scale: float) -> Optional[float]:
        value = cls._i32(values, address)
        return None if value is None else float(value) / scale

    @classmethod
    def _scaled_u32(cls, values: dict[int, int], address: int, scale: float) -> Optional[float]:
        value = cls._u32(values, address)
        return None if value is None else float(value) / scale

    @staticmethod
    def _string(values: dict[int, int], address: int, count: int) -> Optional[str]:
        chars: list[str] = []
        found = False
        for offset in range(count):
            value = values.get(address + offset)
            if value is None:
                continue
            found = True
            chars.append(chr((value >> 8) & 0xFF))
            chars.append(chr(value & 0xFF))
        if not found:
            return None
        text = "".join(chars).split("\x00", 1)[0].strip()
        return text or None

    @staticmethod
    def _decode_status(value: Optional[int]) -> str:
        if value is None:
            return "Unbekannt"
        parts: list[str] = []
        if value & (1 << 0):
            parts.append("Standby")
        if value & (1 << 2):
            parts.append("Betrieb")
        if value & (1 << 6):
            parts.append("Fehler")
        return ", ".join(parts) or f"Status {value}"

    @staticmethod
    def _simulate() -> SolakonOneReading:
        now = datetime.now().astimezone()
        seconds = now.hour * 3600 + now.minute * 60 + now.second
        daylight = max(0.0, math.sin(math.pi * (seconds - 6 * 3600) / (14 * 3600)))
        pv = max(0.0, 960.0 * daylight + random.uniform(-18, 18))
        battery_soc = 48 + 32 * math.sin((seconds - 8 * 3600) / 86400 * 2 * math.pi)
        battery_soc = max(10.0, min(98.0, battery_soc))
        charge = max(0.0, pv - 520.0)
        discharge = max(0.0, 250.0 - pv) if now.hour >= 18 or now.hour < 7 else 0.0
        battery_power = charge - discharge  # positive = charging
        ac = max(0.0, pv - max(0.0, battery_power) + max(0.0, -battery_power)) * 0.94
        load = 260.0 + 120.0 * (math.sin(seconds / 2100.0) ** 2)
        meter = ac - load  # positive feed-in, negative import
        return SolakonOneReading(
            model_name="Solakon ONE Simulation",
            serial_number="SIM-ONE-4000",
            status="Betrieb",
            total_pv_power_w=round(pv, 1),
            active_power_w=round(ac, 1),
            battery_power_w=round(battery_power, 1),
            battery_soc_pct=round(battery_soc, 1),
            load_power_w=round(load, 1),
            meter_power_w=round(meter, 1),
            internal_temperature_c=31.5 + 5 * daylight,
            grid_frequency_hz=50.0,
            power_factor=0.99,
            total_pv_energy_kwh=1234.56,
            daily_pv_energy_kwh=round(pv * max(0, now.hour - 6) / 1000, 2),
            battery_total_charge_kwh=456.78,
            battery_total_discharge_kwh=419.22,
            pv1_voltage_v=36.2,
            pv1_current_a=pv / 72.4 if pv else 0.0,
            pv1_power_w=pv / 2,
            pv2_voltage_v=36.1,
            pv2_current_a=pv / 72.2 if pv else 0.0,
            pv2_power_w=pv / 2,
            source="Solakon ONE Simulation",
        )
