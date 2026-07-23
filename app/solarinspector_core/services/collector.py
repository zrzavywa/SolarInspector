"""Collect and persist SolarInspector measurements.

This module preserves the existing source selection, fallback handling,
energy integration, lifecycle, and persistence behavior.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Optional

from modbus_solakon import (
    SolakonOneReader,
    SolakonOneReading,
)

from solarinspector_core.adapters.shelly import ShellyReader
from solarinspector_core.config.manager import ConfigManager
from solarinspector_core.logging import log
from solarinspector_core.models.legacy import MeterReading
from solarinspector_core.persistence.database import Database


class Collector:
    def __init__(self, config_manager: ConfigManager, database: Database):
        self.config_manager = config_manager
        self.database = database
        self.reader = self._create_shelly_reader()
        self.solakon_reader = self._create_solakon_reader()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._last_sample: Optional[dict[str, Any]] = database.latest()
        self._last_error = ""
        self._started_at: Optional[str] = None
        self._cycles = 0
        self._previous_power: Optional[dict[str, Any]] = None
        self._previous_epoch: Optional[float] = None

    @staticmethod
    def _create_shelly_reader() -> ShellyReader:
        """Create the existing default Shelly reader."""
        return ShellyReader()

    @staticmethod
    def _create_solakon_reader() -> SolakonOneReader:
        """Create the existing default Solakon reader."""
        return SolakonOneReader()

    @staticmethod
    def _now() -> datetime:
        """Return the current local time."""
        return datetime.now().astimezone()

    @staticmethod
    def _monotonic() -> float:
        """Return the monotonic runtime clock."""
        return time.monotonic()

    @staticmethod
    def _log(message: str) -> None:
        """Write a collector message through application logging."""
        log(message)

    @staticmethod
    def _create_thread(
        *,
        target: Any,
        name: str,
        daemon: bool,
    ) -> threading.Thread:
        """Create the existing collector worker thread."""
        return threading.Thread(
            target=target,
            name=name,
            daemon=daemon,
        )

    @staticmethod
    def _has_enabled_source(config: dict[str, Any]) -> bool:
        return any(
            config[name].get("enabled")
            for name in ("house_meter", "solakon_meter", "solakon_one")
        )

    def start(self) -> bool:
        config = self.config_manager.get()
        if not self._has_enabled_source(config):
            with self._lock:
                self._last_error = (
                    "Keine Messstelle aktiviert. Bitte zuerst die Konfiguration prüfen."
                )
            self._log(self._last_error)
            return False
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop_event.clear()
            self._started_at = self._now().isoformat(timespec="seconds")
            self._thread = self._create_thread(
                target=self._run,
                name="SolarInspectorCollector",
                daemon=True,
            )
            self._thread.start()
            self._log("Datenerfassung gestartet.")
            return True

    def stop(self) -> bool:
        with self._lock:
            if not self._thread or not self._thread.is_alive():
                return False
            self._stop_event.set()
            thread = self._thread
        thread.join(timeout=10)
        self._log("Datenerfassung gestoppt.")
        return True

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def status(self) -> dict[str, Any]:
        with self._lock:
            latest = dict(self._last_sample) if self._last_sample else None
            return {
                "running": self.is_running(),
                "started_at": self._started_at,
                "cycles": self._cycles,
                "last_error": self._last_error,
                "last_sample": latest,
            }

    @staticmethod
    def _select_solar_power(
        source: str,
        shelly_power: Optional[float],
        solakon: Optional[SolakonOneReading],
    ) -> tuple[Optional[float], str]:
        solakon_ac = (
            None
            if solakon is None or solakon.active_power_w is None
            else max(0.0, solakon.active_power_w)
        )
        solakon_pv = (
            None
            if solakon is None or solakon.total_pv_power_w is None
            else max(0.0, solakon.total_pv_power_w)
        )
        if source == "shelly_ac":
            return shelly_power, "Shelly AC"
        if source == "solakon_ac":
            return solakon_ac, "Solakon ONE AC"
        if source == "solakon_pv":
            return solakon_pv, "Solakon ONE PV-Eingang"
        if shelly_power is not None:
            return shelly_power, "Shelly AC (Auto)"
        if solakon_ac is not None:
            return solakon_ac, "Solakon ONE AC (Auto)"
        return (
            solakon_pv,
            "Solakon ONE PV-Eingang (Auto)"
            if solakon_pv is not None
            else "Keine Quelle",
        )

    @staticmethod
    def _select_grid_power(
        source: str,
        house_reading: Optional[MeterReading],
        solakon: Optional[SolakonOneReading],
    ) -> tuple[Optional[float], str]:
        house_power = house_reading.power_w if house_reading else None
        # Solakon register 39168: positive = feed-in, negative = grid import.
        # SolarInspector convention is the opposite: positive = import.
        solakon_grid = None
        if solakon is not None and solakon.meter_power_w is not None:
            solakon_grid = -solakon.meter_power_w
        if source == "house_meter":
            return house_power, "Separate Hausmessung"
        if source == "solakon_one":
            return solakon_grid, "Solakon ONE Meter"
        if house_power is not None:
            return house_power, "Separate Hausmessung (Auto)"
        return (
            solakon_grid,
            "Solakon ONE Meter (Auto)" if solakon_grid is not None else "Keine Quelle",
        )

    def collect_once(self) -> dict[str, Any]:
        config = self.config_manager.get()
        if not self._has_enabled_source(config):
            raise ValueError(
                "Keine Messstelle aktiviert. Bitte zuerst die Konfiguration prüfen."
            )

        now = self._now()
        now_epoch = now.timestamp()
        house_cfg = config["house_meter"]
        solar_cfg = config["solakon_meter"]
        one_cfg = config["solakon_one"]

        errors: list[str] = []
        house_reading: Optional[MeterReading] = None
        solar_reading: Optional[MeterReading] = None
        solakon_reading: Optional[SolakonOneReading] = None

        if one_cfg.get("enabled"):
            try:
                solakon_reading = self.solakon_reader.read(one_cfg)
            except Exception as exc:
                errors.append(f"Solakon ONE: {exc}")

        if house_cfg.get("enabled"):
            try:
                house_reading = self.reader.read(house_cfg, "house_meter")
            except Exception as exc:
                errors.append(f"Hausanschluss: {exc}")

        if solar_cfg.get("enabled"):
            try:
                solar_reading = self.reader.read(solar_cfg, "solakon_meter")
            except Exception as exc:
                errors.append(f"Shelly AC-Erzeugung: {exc}")

        shelly_solar_power = max(0.0, solar_reading.power_w) if solar_reading else None
        solar_power, solar_source = self._select_solar_power(
            config["general"].get("solar_power_source", "auto"),
            shelly_solar_power,
            solakon_reading,
        )
        grid_power, grid_source = self._select_grid_power(
            config["general"].get("grid_power_source", "auto"),
            house_reading,
            solakon_reading,
        )

        solakon_ac = solakon_reading.active_power_w if solakon_reading else None
        solakon_pv = solakon_reading.total_pv_power_w if solakon_reading else None
        solakon_battery = solakon_reading.battery_power_w if solakon_reading else None

        grid_import = max(0.0, grid_power) if grid_power is not None else None
        feed_in = max(0.0, -grid_power) if grid_power is not None else None

        # For the household balance always prefer an AC measurement. The DC PV
        # input is useful as a production source, but must not be added directly
        # to the household grid balance while the battery is charging.
        balance_generation = shelly_solar_power
        if balance_generation is None and solakon_ac is not None:
            balance_generation = max(0.0, solakon_ac)
        if balance_generation is None:
            balance_generation = solar_power

        if grid_power is not None and balance_generation is not None:
            house_power = max(0.0, grid_power + balance_generation)
            self_consumption = max(0.0, min(balance_generation, house_power))
        elif grid_power is not None:
            house_power = max(0.0, grid_power)
            self_consumption = None
        else:
            house_power = solakon_reading.load_power_w if solakon_reading else None
            self_consumption = None

        solar_difference = None
        solar_difference_pct = None
        if shelly_solar_power is not None and solakon_ac is not None:
            solar_difference = shelly_solar_power - solakon_ac
            if abs(solakon_ac) >= 10:
                solar_difference_pct = solar_difference / abs(solakon_ac) * 100.0

        interval = config["general"]["poll_interval_seconds"]
        if self._previous_epoch is None:
            dt_seconds = 0.0
        else:
            dt_seconds = max(0.0, min(now_epoch - self._previous_epoch, interval * 3.0))

        current_power = {
            "grid_import_w": grid_import,
            "feed_in_w": feed_in,
            "solar_power_w": solar_power,
            "house_power_w": house_power,
            "self_consumption_w": self_consumption,
            "shelly_solar_power_w": shelly_solar_power,
            "solakon_pv_power_w": max(0.0, solakon_pv)
            if solakon_pv is not None
            else None,
            "solakon_ac_power_w": max(0.0, solakon_ac)
            if solakon_ac is not None
            else None,
            "battery_charge_w": max(0.0, solakon_battery)
            if solakon_battery is not None
            else None,
            "battery_discharge_w": max(0.0, -solakon_battery)
            if solakon_battery is not None
            else None,
        }

        energy: dict[str, float] = {}
        for power_key, energy_key in (
            ("grid_import_w", "grid_import_wh"),
            ("feed_in_w", "feed_in_wh"),
            ("solar_power_w", "solar_wh"),
            ("house_power_w", "house_wh"),
            ("self_consumption_w", "self_consumption_wh"),
            ("shelly_solar_power_w", "shelly_solar_wh"),
            ("solakon_pv_power_w", "solakon_pv_wh"),
            ("solakon_ac_power_w", "solakon_ac_wh"),
            ("battery_charge_w", "battery_charge_wh"),
            ("battery_discharge_w", "battery_discharge_wh"),
        ):
            current = current_power.get(power_key)
            previous = (self._previous_power or {}).get(power_key)
            if current is None or previous is None or dt_seconds <= 0:
                energy[energy_key] = 0.0
            else:
                energy[energy_key] = (
                    ((float(current) + float(previous)) / 2.0) * dt_seconds / 3600.0
                )

        preferred = solar_reading or house_reading
        sample = {
            "ts_epoch": now_epoch,
            "ts_local": now.isoformat(timespec="seconds"),
            "grid_power_w": grid_power,
            "solar_power_w": solar_power,
            "house_power_w": house_power,
            "grid_import_w": grid_import,
            "feed_in_w": feed_in,
            "self_consumption_w": self_consumption,
            "voltage_v": preferred.voltage_v if preferred else None,
            "current_a": preferred.current_a if preferred else None,
            "power_factor": preferred.power_factor
            if preferred
            else (solakon_reading.power_factor if solakon_reading else None),
            "frequency_hz": preferred.frequency_hz
            if preferred
            else (solakon_reading.grid_frequency_hz if solakon_reading else None),
            **energy,
            "house_ok": 1 if house_reading else 0,
            "solar_ok": 1 if solar_reading else 0,
            "error_text": " | ".join(errors),
            "shelly_solar_power_w": shelly_solar_power,
            "solakon_pv_power_w": solakon_pv,
            "solakon_ac_power_w": solakon_ac,
            "solakon_battery_power_w": solakon_battery,
            "solakon_battery_soc_pct": solakon_reading.battery_soc_pct
            if solakon_reading
            else None,
            "solakon_load_power_w": solakon_reading.load_power_w
            if solakon_reading
            else None,
            "solakon_meter_power_w": solakon_reading.meter_power_w
            if solakon_reading
            else None,
            "solakon_temperature_c": solakon_reading.internal_temperature_c
            if solakon_reading
            else None,
            "solakon_daily_pv_kwh": solakon_reading.daily_pv_energy_kwh
            if solakon_reading
            else None,
            "solakon_total_pv_kwh": solakon_reading.total_pv_energy_kwh
            if solakon_reading
            else None,
            "solakon_pv1_power_w": solakon_reading.pv1_power_w
            if solakon_reading
            else None,
            "solakon_pv2_power_w": solakon_reading.pv2_power_w
            if solakon_reading
            else None,
            "solakon_pv3_power_w": solakon_reading.pv3_power_w
            if solakon_reading
            else None,
            "solakon_pv4_power_w": solakon_reading.pv4_power_w
            if solakon_reading
            else None,
            "solar_difference_w": solar_difference,
            "solar_difference_pct": solar_difference_pct,
            "solar_source": solar_source,
            "grid_source": grid_source,
            "solakon_model": solakon_reading.model_name if solakon_reading else None,
            "solakon_serial": solakon_reading.serial_number
            if solakon_reading
            else None,
            "solakon_status": solakon_reading.status if solakon_reading else None,
            "solakon_ok": 1 if solakon_reading else 0,
        }
        sample_id = self.database.insert_sample(sample)
        sample["id"] = sample_id

        self._previous_power = current_power
        self._previous_epoch = now_epoch

        with self._lock:
            self._last_sample = sample
            self._last_error = " | ".join(errors)
            self._cycles += 1

        if errors:
            self._log("Messzyklus mit Warnung: " + " | ".join(errors))
        return sample

    def reset_state(self) -> None:
        with self._lock:
            self._last_sample = None
            self._last_error = ""
            self._cycles = 0
            self._started_at = None
            self._previous_power = None
            self._previous_epoch = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            cycle_started = self._monotonic()
            try:
                self.collect_once()
            except Exception as exc:
                with self._lock:
                    self._last_error = str(exc)
                self._log(f"Messzyklus fehlgeschlagen: {exc}")
            interval = self.config_manager.get()["general"]["poll_interval_seconds"]
            elapsed = self._monotonic() - cycle_started
            self._stop_event.wait(max(0.2, interval - elapsed))
