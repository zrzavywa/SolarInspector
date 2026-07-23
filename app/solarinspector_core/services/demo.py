"""Generate deterministic SolarInspector demonstration samples."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol


class SampleDatabase(Protocol):
    """Persistence operations required for demo data."""

    def insert_sample(
        self,
        sample: dict[str, Any],
    ) -> Any:
        """Persist one measurement sample."""


def generate_demo_samples(
    database: SampleDatabase,
    *,
    days: int = 400,
    interval_minutes: int = 15,
    end_time: datetime,
    log_message: Callable[[str], None],
) -> None:
    """Generate and persist the existing demonstration data."""
    log_message(f"Erzeuge Demodaten für {days} Tage.")

    end = end_time
    start = end - timedelta(days=days)
    current = start
    previous_values: dict[str, float] | None = None
    battery_soc = 55.0

    while current <= end:
        seconds = current.hour * 3600 + current.minute * 60 + current.second

        season = 0.45 + 0.55 * max(
            0.0,
            math.sin(math.pi * (current.timetuple().tm_yday - 15) / 365.0),
        )

        daylight = max(
            0.0,
            math.sin(math.pi * (seconds - 6 * 3600) / (14 * 3600)),
        )

        weather = 0.55 + 0.45 * math.sin(current.toordinal() * 1.73) ** 2

        pv_dc = max(
            0.0,
            980.0 * season * daylight * weather,
        )

        house = 230.0 + 120.0 * (math.sin(seconds / 2100.0) ** 2)

        if 18 <= current.hour <= 22:
            house += 220.0

        desired_charge = (
            max(
                0.0,
                min(
                    420.0,
                    pv_dc - house - 80.0,
                ),
            )
            if battery_soc < 94
            else 0.0
        )

        desired_discharge = (
            max(
                0.0,
                min(
                    300.0,
                    house - pv_dc,
                ),
            )
            if (battery_soc > 18 and (current.hour >= 18 or current.hour < 7))
            else 0.0
        )

        battery_power = desired_charge - desired_discharge

        ac_solar = max(
            0.0,
            (pv_dc - desired_charge + desired_discharge) * 0.94,
        )

        shelly_ac = max(
            0.0,
            ac_solar * (1.0 + 0.015 * math.sin(seconds / 1700.0)),
        )

        grid = house - shelly_ac
        meter_power = -grid

        dt_hours = interval_minutes / 60.0 if previous_values else 0.0

        battery_soc += (
            (desired_charge * 0.93 - desired_discharge / 0.93)
            * dt_hours
            / 2110.0
            * 100.0
        )

        battery_soc = max(
            10.0,
            min(
                98.0,
                battery_soc,
            ),
        )

        values = {
            "grid_import_w": max(
                0.0,
                grid,
            ),
            "feed_in_w": max(
                0.0,
                -grid,
            ),
            "solar_power_w": shelly_ac,
            "house_power_w": house,
            "self_consumption_w": min(
                shelly_ac,
                house,
            ),
            "shelly_solar_power_w": (shelly_ac),
            "solakon_pv_power_w": pv_dc,
            "solakon_ac_power_w": ac_solar,
            "battery_charge_w": max(
                0.0,
                battery_power,
            ),
            "battery_discharge_w": max(
                0.0,
                -battery_power,
            ),
        }

        def energy(key: str) -> float:
            if not previous_values:
                return 0.0

            return ((values[key] + previous_values[key]) / 2.0) * dt_hours

        difference = shelly_ac - ac_solar

        sample = {
            "ts_epoch": current.timestamp(),
            "ts_local": current.isoformat(timespec="seconds"),
            "grid_power_w": grid,
            "solar_power_w": shelly_ac,
            "house_power_w": house,
            "grid_import_w": values["grid_import_w"],
            "feed_in_w": values["feed_in_w"],
            "self_consumption_w": values["self_consumption_w"],
            "voltage_v": 230.0,
            "current_a": abs(grid) / 230.0,
            "power_factor": 0.99,
            "frequency_hz": 50.0,
            "grid_import_wh": energy("grid_import_w"),
            "feed_in_wh": energy("feed_in_w"),
            "solar_wh": energy("solar_power_w"),
            "house_wh": energy("house_power_w"),
            "self_consumption_wh": energy("self_consumption_w"),
            "shelly_solar_wh": energy("shelly_solar_power_w"),
            "solakon_pv_wh": energy("solakon_pv_power_w"),
            "solakon_ac_wh": energy("solakon_ac_power_w"),
            "battery_charge_wh": energy("battery_charge_w"),
            "battery_discharge_wh": energy("battery_discharge_w"),
            "house_ok": 1,
            "solar_ok": 1,
            "error_text": "",
            "shelly_solar_power_w": (shelly_ac),
            "solakon_pv_power_w": pv_dc,
            "solakon_ac_power_w": ac_solar,
            "solakon_battery_power_w": (battery_power),
            "solakon_battery_soc_pct": (battery_soc),
            "solakon_load_power_w": house,
            "solakon_meter_power_w": (meter_power),
            "solakon_temperature_c": (28.0 + 8.0 * daylight),
            "solakon_daily_pv_kwh": 0.0,
            "solakon_total_pv_kwh": 1200.0,
            "solakon_pv1_power_w": (pv_dc / 2.0),
            "solakon_pv2_power_w": (pv_dc / 2.0),
            "solakon_pv3_power_w": 0.0,
            "solakon_pv4_power_w": 0.0,
            "solar_difference_w": difference,
            "solar_difference_pct": (
                difference / ac_solar * 100.0 if ac_solar >= 10 else None
            ),
            "solar_source": ("Shelly AC (Auto)"),
            "grid_source": ("Separate Hausmessung (Auto)"),
            "solakon_model": ("Solakon ONE Simulation"),
            "solakon_serial": ("SIM-ONE-4000"),
            "solakon_status": "Betrieb",
            "solakon_ok": 1,
        }

        database.insert_sample(sample)
        previous_values = values

        current += timedelta(minutes=interval_minutes)

    log_message("Demodaten fertig.")
