"""Characterization tests for the SolarInspector 4.1.3 Modbus integration."""

import json
import socket
import struct
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import modbus_solakon as ms
import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "solarkon"


def load_fixture(filename: str) -> dict[str, Any]:
    """Load one synthetic Solakon register fixture."""
    return json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))


class FixtureModbusConnection:
    """Serve fixture registers through the connection interface used by reader."""

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.requests: list[tuple[int, int]] = []
        self.connection_arguments: tuple[str, int, int, float] | None = None

    def __enter__(self) -> "FixtureModbusConnection":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read_holding_registers(
        self,
        address: int,
        count: int,
    ) -> list[int]:
        self.requests.append((address, count))
        if address in self.payload.get("fail_blocks", []):
            raise ms.ModbusError(f"Synthetischer Fehler für Block {address}")

        registers = self.payload["registers"]
        return [int(registers.get(str(address + offset), 0)) for offset in range(count)]


def install_fixture_connection(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
) -> FixtureModbusConnection:
    """Replace the TCP connection with one deterministic fixture connection."""
    connection = FixtureModbusConnection(payload)

    def create_connection(
        host: str,
        port: int,
        unit_id: int,
        timeout: float,
    ) -> FixtureModbusConnection:
        connection.connection_arguments = (
            host,
            port,
            unit_id,
            timeout,
        )
        return connection

    monkeypatch.setattr(ms, "ModbusTcpConnection", create_connection)
    return connection


def read_fixture(
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
) -> tuple[ms.SolakonOneReading, FixtureModbusConnection]:
    """Read one fixture through the public SolakonOneReader API."""
    payload = load_fixture(filename)
    connection = install_fixture_connection(monkeypatch, payload)
    reading = ms.SolakonOneReader().read(
        {
            "host": "192.168.188.60",
            "port": 502,
            "device_id": 1,
            "timeout_seconds": 5,
            "simulation": False,
        }
    )
    return reading, connection


def test_normal_register_fixture_maps_current_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The normal fixture documents register scaling and preferred values."""
    reading, connection = read_fixture(
        monkeypatch,
        "normal_registers.json",
    )

    assert reading.model_name == "Solakon ONE H3"
    assert reading.serial_number == "SYNTHETIC-001"
    assert reading.status == "Betrieb"
    assert reading.total_pv_power_w == 960.0
    assert reading.active_power_w == 740.0
    assert reading.battery_power_w == 220.0
    assert reading.load_power_w == 590.0
    assert reading.meter_power_w == -150.0
    assert reading.battery_soc_pct == 76.0
    assert reading.internal_temperature_c == pytest.approx(31.5)
    assert reading.grid_frequency_hz == pytest.approx(50.01)
    assert reading.power_factor == pytest.approx(0.99)
    assert reading.total_pv_energy_kwh == pytest.approx(1234.56)
    assert reading.daily_pv_energy_kwh == pytest.approx(3.45)
    assert reading.battery_total_charge_kwh == pytest.approx(456.78)
    assert reading.battery_total_discharge_kwh == pytest.approx(419.22)
    assert reading.pv1_voltage_v == pytest.approx(36.2)
    assert reading.pv1_current_a == pytest.approx(1.23)
    assert reading.pv1_power_w == 480.0
    assert reading.pv2_voltage_v == pytest.approx(35.8)
    assert reading.pv2_current_a == pytest.approx(1.11)
    assert reading.pv2_power_w == 480.0
    assert reading.warnings == ""
    assert connection.connection_arguments == (
        "192.168.188.60",
        502,
        1,
        5.0,
    )
    assert connection.requests == list(ms.SolakonOneReader.BLOCKS)


def test_positive_battery_power_means_charging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Positive battery power is currently preserved as charging power."""
    reading, _ = read_fixture(
        monkeypatch,
        "battery_charging.json",
    )

    assert reading.battery_power_w == 450.0
    assert reading.total_pv_power_w == 900.0
    assert reading.active_power_w == 420.0
    assert reading.battery_soc_pct == 64.0


def test_negative_battery_power_means_discharging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative battery power is currently preserved as discharging power."""
    reading, _ = read_fixture(
        monkeypatch,
        "battery_discharging.json",
    )

    assert reading.battery_power_w == -300.0
    assert reading.total_pv_power_w == 100.0
    assert reading.active_power_w == 380.0
    assert reading.battery_soc_pct == 38.0


def test_zero_generation_values_remain_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read zero register values remain numeric zeros rather than None."""
    reading, _ = read_fixture(
        monkeypatch,
        "zero_generation.json",
    )

    assert reading.status == "Standby"
    assert reading.total_pv_power_w == 0.0
    assert reading.active_power_w == 0.0
    assert reading.battery_power_w == 0.0
    assert reading.load_power_w == 280.0
    assert reading.meter_power_w == -280.0
    assert reading.pv1_power_w == 0.0
    assert reading.pv2_power_w == 0.0


def test_partial_block_failures_return_identity_and_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful blocks survive while failed blocks are collected as warnings."""
    reading, connection = read_fixture(
        monkeypatch,
        "incomplete_registers.json",
    )

    assert reading.model_name == "Solakon ONE H3"
    assert reading.serial_number == "SYNTHETIC-PART"
    assert reading.status == "Unbekannt"
    assert reading.total_pv_power_w is None
    assert reading.active_power_w is None
    assert reading.battery_power_w is None
    assert reading.battery_soc_pct is None
    assert "Register 39000–39077" in reading.warnings
    assert "Register 39601–39632" in reading.warnings
    assert len(reading.warnings.split(" | ")) == 8
    assert connection.requests == list(ms.SolakonOneReader.BLOCKS)


def test_modern_energy_registers_are_preferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 396xx energy registers win over historical 391xx counters."""
    reading, _ = read_fixture(
        monkeypatch,
        "normal_registers.json",
    )

    assert reading.total_pv_energy_kwh == pytest.approx(1234.56)
    assert reading.daily_pv_energy_kwh == pytest.approx(3.45)


def test_historical_energy_registers_are_used_as_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure of block 39601 activates the older energy counters."""
    payload = load_fixture("normal_registers.json")
    payload["fail_blocks"] = [39601]
    install_fixture_connection(monkeypatch, payload)

    reading = ms.SolakonOneReader().read(
        {
            "host": "192.168.188.60",
            "port": 502,
            "device_id": 1,
            "timeout_seconds": 5,
        }
    )

    assert reading.total_pv_energy_kwh == pytest.approx(6543.21)
    assert reading.daily_pv_energy_kwh == pytest.approx(7.89)
    assert reading.battery_total_charge_kwh is None
    assert reading.battery_total_discharge_kwh is None
    assert "Register 39601–39632" in reading.warnings


def test_storage_module_power_is_used_when_battery_block_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Battery power falls back from 39237 to the older 39162 register."""
    payload = load_fixture("normal_registers.json")
    payload["fail_blocks"] = [39219]
    install_fixture_connection(monkeypatch, payload)

    reading = ms.SolakonOneReader().read(
        {
            "host": "192.168.188.60",
            "port": 502,
            "device_id": 1,
            "timeout_seconds": 5,
        }
    )

    assert reading.battery_power_w == 210.0
    assert "Register 39219–39238" in reading.warnings


def test_all_failed_blocks_raise_no_registers_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A complete block failure raises after all blocks have been attempted."""
    payload = {
        "registers": {},
        "fail_blocks": [start for start, _count in ms.SolakonOneReader.BLOCKS],
    }
    connection = install_fixture_connection(monkeypatch, payload)

    with pytest.raises(
        ms.ModbusError,
        match="keine Register gelesen",
    ):
        ms.SolakonOneReader().read(
            {
                "host": "192.168.188.60",
                "port": 502,
                "device_id": 1,
                "timeout_seconds": 5,
            }
        )

    assert connection.requests == list(ms.SolakonOneReader.BLOCKS)


def test_unrecognizable_register_response_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An isolated SOC block is not accepted as a recognizable device."""
    fail_blocks = [
        start for start, _count in ms.SolakonOneReader.BLOCKS if start != 39424
    ]
    payload = {
        "registers": {
            "39424": 55,
        },
        "fail_blocks": fail_blocks,
    }
    install_fixture_connection(monkeypatch, payload)

    with pytest.raises(
        ms.ModbusError,
        match="Keine erkennbaren",
    ):
        ms.SolakonOneReader().read(
            {
                "host": "192.168.188.60",
                "port": 502,
                "device_id": 1,
                "timeout_seconds": 5,
            }
        )


def test_reader_requires_host() -> None:
    """A missing host is rejected before creating a Modbus connection."""
    with pytest.raises(
        ValueError,
        match="Keine IP-Adresse",
    ):
        ms.SolakonOneReader().read(
            {
                "host": "",
                "simulation": False,
            }
        )


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (0x0000, 0),
        (0x7FFF, 32767),
        (0x8000, -32768),
        (0xFFFF, -1),
    ],
)
def test_i16_signed_conversion(
    raw_value: int,
    expected: int,
) -> None:
    """Signed 16-bit conversion follows two's-complement rules."""
    assert ms.SolakonOneReader._i16({1: raw_value}, 1) == expected


@pytest.mark.parametrize(
    ("high", "low", "expected"),
    [
        (0x0000, 0x0000, 0),
        (0x0000, 0x0001, 1),
        (0x7FFF, 0xFFFF, 2147483647),
        (0xFFFF, 0xFFFF, -1),
        (0xFFFF, 0xFF38, -200),
    ],
)
def test_i32_signed_conversion(
    high: int,
    low: int,
    expected: int,
) -> None:
    """Signed 32-bit conversion follows two's-complement rules."""
    values = {
        10: high,
        11: low,
    }

    assert ms.SolakonOneReader._i32(values, 10) == expected


def test_missing_half_of_32_bit_value_returns_none() -> None:
    """A 32-bit value requires both consecutive raw registers."""
    assert ms.SolakonOneReader._u32({10: 1}, 10) is None
    assert ms.SolakonOneReader._i32({11: 1}, 10) is None


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        (None, "Unbekannt"),
        (1 << 0, "Standby"),
        (1 << 2, "Betrieb"),
        ((1 << 2) | (1 << 6), "Betrieb, Fehler"),
        (1 << 4, "Status 16"),
    ],
)
def test_status_decoding(
    raw_status: int | None,
    expected: str,
) -> None:
    """Status bits are converted to the current German display strings."""
    assert ms.SolakonOneReader._decode_status(raw_status) == expected


@pytest.mark.parametrize(
    ("address", "count", "message"),
    [
        (-1, 1, "Registeradresse"),
        (65536, 1, "Registeradresse"),
        (1, 0, "1 bis 125"),
        (1, 126, "1 bis 125"),
    ],
)
def test_register_request_limits_are_validated(
    address: int,
    count: int,
    message: str,
) -> None:
    """Invalid Modbus ranges are rejected before transport access."""
    connection = ms.ModbusTcpConnection(
        "192.168.188.60",
        502,
        1,
        5,
    )

    with pytest.raises(ValueError, match=message):
        connection.read_holding_registers(address, count)


def test_read_requires_an_open_connection() -> None:
    """A valid request without an open socket raises a transport error."""
    connection = ms.ModbusTcpConnection(
        "192.168.188.60",
        502,
        1,
        5,
    )

    with pytest.raises(
        ms.ModbusError,
        match="nicht geöffnet",
    ):
        connection.read_holding_registers(39000, 1)


def test_connection_error_is_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Socket connection failures become ModbusError instances."""

    def fail_connection(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(
        ms.socket,
        "create_connection",
        fail_connection,
    )

    connection = ms.ModbusTcpConnection(
        "192.168.188.60",
        502,
        1,
        5,
    )

    with pytest.raises(
        ms.ModbusError,
        match="Verbindung zu 192.168.188.60:502 fehlgeschlagen",
    ):
        with connection:
            pass


def test_transport_timeout_is_wrapped() -> None:
    """A socket timeout during a request becomes a ModbusError."""
    connection = ms.ModbusTcpConnection(
        "192.168.188.60",
        502,
        1,
        5,
    )
    fake_socket = Mock()
    fake_socket.recv.side_effect = socket.timeout("timed out")
    connection._socket = fake_socket

    with pytest.raises(
        ms.ModbusError,
        match="Modbus-Kommunikation fehlgeschlagen",
    ):
        connection.read_holding_registers(39000, 1)


def test_modbus_exception_response_is_decoded() -> None:
    """A function-code exception is converted to a descriptive error."""
    connection = ms.ModbusTcpConnection(
        "192.168.188.60",
        502,
        1,
        5,
    )
    fake_socket = Mock()
    header = struct.pack(
        ">HHHB",
        1,
        0,
        3,
        1,
    )
    fake_socket.recv.side_effect = [
        header,
        bytes([0x83, 2]),
    ]
    connection._socket = fake_socket

    with pytest.raises(
        ms.ModbusError,
        match="ungültige Registeradresse",
    ):
        connection.read_holding_registers(39000, 1)


def test_unexpected_connection_close_is_reported() -> None:
    """A closed connection during a response is reported explicitly."""
    fake_socket = Mock()
    fake_socket.recv.side_effect = [
        b"\x01",
        b"",
    ]

    with pytest.raises(
        ms.ModbusError,
        match="unerwartet geschlossen",
    ):
        ms.ModbusTcpConnection._recv_exact(
            fake_socket,
            2,
        )
