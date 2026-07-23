"""Read existing Shelly power meters.

This module preserves the HTTP access, response parsing, simulation,
direction handling, and error behavior of SolarInspector 4.1.3.
"""

from __future__ import annotations

import math
import random
import time
from datetime import datetime
from typing import Any, Optional

import requests
from requests.auth import HTTPDigestAuth

from solarinspector_core.models.legacy import MeterReading


class ShellyReader:
    def __init__(self):
        self._session = requests.Session()
        self._simulation_start = time.monotonic()

    @staticmethod
    def _url(host: str, path: str) -> str:
        return f"http://{host}{path}"

    def _get_json(self, device: dict[str, Any], path: str) -> dict[str, Any]:
        if not device.get("host"):
            raise ValueError("Keine IP-Adresse oder kein Hostname konfiguriert.")
        auth = None
        if device.get("username"):
            auth = HTTPDigestAuth(device["username"], device.get("password", ""))
        response = self._session.get(
            self._url(device["host"], path),
            timeout=device.get("timeout_seconds", 3),
            auth=auth,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Das Gerät lieferte keine gültige JSON-Antwort.")
        return payload

    def read(self, device: dict[str, Any], role: str) -> MeterReading:
        device_type = device.get("type")
        factor = float(device.get("direction_factor", 1))

        if device_type == "simulation":
            reading = self._simulate(role)
        elif device_type == "shelly_pm_mini_gen3":
            reading = self._read_pm1(device)
        elif device_type == "shelly_3em_gen1":
            reading = self._read_3em_gen1(device)
        elif device_type == "shelly_pro_3em":
            reading = self._read_pro_3em(device)
        else:
            raise ValueError(f"Nicht unterstützter Gerätetyp: {device_type}")

        reading.power_w *= factor
        return reading

    def _read_pm1(self, device: dict[str, Any]) -> MeterReading:
        data = self._get_json(device, "/rpc/PM1.GetStatus?id=0")
        return MeterReading(
            power_w=float(data.get("apower", 0.0)),
            voltage_v=_float_or_none(data.get("voltage")),
            current_a=_float_or_none(data.get("current")),
            power_factor=_float_or_none(data.get("pf")),
            frequency_hz=_float_or_none(data.get("freq")),
            energy_total_wh=_nested_float(data, "aenergy", "total"),
            returned_energy_total_wh=_nested_float(data, "ret_aenergy", "total"),
            source="PM1.GetStatus",
        )

    def _read_3em_gen1(self, device: dict[str, Any]) -> MeterReading:
        data = self._get_json(device, "/status")
        emeters = data.get("emeters") or []
        if not isinstance(emeters, list) or not emeters:
            raise ValueError("Keine emeters-Daten in der Shelly-3EM-Antwort.")
        power = data.get("total_power")
        if power is None:
            power = sum(float(item.get("power", 0.0)) for item in emeters)
        voltages = [_float_or_none(item.get("voltage")) for item in emeters]
        valid_voltages = [item for item in voltages if item is not None]
        total_wh = sum(float(item.get("total", 0.0)) for item in emeters)
        returned_wh = sum(float(item.get("total_returned", 0.0)) for item in emeters)
        return MeterReading(
            power_w=float(power),
            voltage_v=(sum(valid_voltages) / len(valid_voltages))
            if valid_voltages
            else None,
            energy_total_wh=total_wh,
            returned_energy_total_wh=returned_wh,
            source="/status emeters",
        )

    def _read_pro_3em(self, device: dict[str, Any]) -> MeterReading:
        data = self._get_json(device, "/rpc/EM.GetStatus?id=0")
        phase_power = [
            _float_or_none(data.get("a_act_power")),
            _float_or_none(data.get("b_act_power")),
            _float_or_none(data.get("c_act_power", data.get("c_active_power"))),
        ]
        power = _float_or_none(data.get("total_act_power"))
        if power is None:
            power = sum(item or 0.0 for item in phase_power)
        voltages = [
            _float_or_none(data.get("a_voltage")),
            _float_or_none(data.get("b_voltage")),
            _float_or_none(data.get("c_voltage")),
        ]
        valid_voltages = [item for item in voltages if item is not None]
        currents = [
            _float_or_none(data.get("a_current")),
            _float_or_none(data.get("b_current")),
            _float_or_none(data.get("c_current")),
        ]
        valid_currents = [item for item in currents if item is not None]
        pfs = [
            _float_or_none(data.get("a_pf")),
            _float_or_none(data.get("b_pf")),
            _float_or_none(data.get("c_pf")),
        ]
        valid_pfs = [item for item in pfs if item is not None]
        freqs = [
            _float_or_none(data.get("a_freq")),
            _float_or_none(data.get("b_freq")),
            _float_or_none(data.get("c_freq")),
        ]
        valid_freqs = [item for item in freqs if item is not None]
        return MeterReading(
            power_w=float(power),
            voltage_v=(sum(valid_voltages) / len(valid_voltages))
            if valid_voltages
            else None,
            current_a=sum(valid_currents) if valid_currents else None,
            power_factor=(sum(valid_pfs) / len(valid_pfs)) if valid_pfs else None,
            frequency_hz=(sum(valid_freqs) / len(valid_freqs)) if valid_freqs else None,
            source="EM.GetStatus",
        )

    def _simulate(self, role: str) -> MeterReading:
        now = datetime.now().astimezone()
        seconds = now.hour * 3600 + now.minute * 60 + now.second
        daylight = max(0.0, math.sin(math.pi * (seconds - 6 * 3600) / (14 * 3600)))
        solar = 850.0 * daylight + random.uniform(-20, 20)
        solar = max(0.0, solar)
        household = 280 + 120 * math.sin(seconds / 2400.0) + random.uniform(-35, 35)
        household = max(90.0, household)
        if role == "solakon_meter":
            power = solar
            source = "Simulation Solakon"
        else:
            power = household - solar
            source = "Simulation Hausanschluss"
        return MeterReading(
            power_w=power,
            voltage_v=230 + random.uniform(-1.5, 1.5),
            current_a=abs(power) / 230.0,
            power_factor=0.97,
            frequency_hz=50 + random.uniform(-0.03, 0.03),
            source=source,
        )


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nested_float(data: dict[str, Any], parent: str, child: str) -> Optional[float]:
    item = data.get(parent)
    if not isinstance(item, dict):
        return None
    return _float_or_none(item.get(child))
