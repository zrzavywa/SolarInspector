"""Collect and persist SolarInspector measurements.

This module preserves the existing source selection, fallback handling,
energy integration, lifecycle, and persistence behavior.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Optional

from solarinspector_core.adapters.compatibility import (
    meter_reading_from_snapshot,
    solakon_reading_from_snapshot,
)
from solarinspector_core.adapters.shelly import (
    ShellyMeasurementAdapter,
    ShellyReader,
)
from solarinspector_core.adapters.solakon import SolakonOneReader, SolakonOneReading
from solarinspector_core.adapters.solakon_measurement import SolakonMeasurementAdapter
from solarinspector_core.adapters.tasmota_grid_meter import (
    TasmotaHttpGridMeterAdapter,
)
from solarinspector_core.config.manager import ConfigManager
from solarinspector_core.logging import log
from solarinspector_core.models.device import DeviceSnapshot
from solarinspector_core.models.legacy import MeterReading
from solarinspector_core.models.metrics import Metric
from solarinspector_core.models.roles import MeasurementRole
from solarinspector_core.persistence.database import Database


@dataclass(frozen=True, slots=True)
class _GridMeasurementSelection:
    """Describe the active compatible grid-power values."""

    grid_power_w: Optional[float]
    grid_import_power_w: Optional[float]
    grid_export_power_w: Optional[float]
    source_label: str
    source_id: Optional[str]


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
        self._last_grid_meter_snapshot: Optional[DeviceSnapshot] = None
        self._last_grid_meter_poll_monotonic: Optional[float] = None

    @staticmethod
    def _create_shelly_reader() -> ShellyReader:
        """Create the existing default Shelly reader."""
        return ShellyReader()

    @staticmethod
    def _create_solakon_reader() -> SolakonOneReader:
        """Create the existing default Solakon reader."""
        return SolakonOneReader()

    @staticmethod
    def _create_grid_meter_adapter(
        config: dict[str, Any],
    ) -> TasmotaHttpGridMeterAdapter:
        """Create the official grid-meter adapter on demand."""

        return TasmotaHttpGridMeterAdapter(config)

    def _read_solakon_snapshot(
        self,
        config: dict[str, Any],
    ) -> tuple[Optional[SolakonOneReading], Optional[str]]:
        """Read Solakon through the normalized adapter and restore legacy data."""

        try:
            snapshot = SolakonMeasurementAdapter(
                source_id="solakon_one",
                name="Solakon ONE",
                config=config,
                reader=self.solakon_reader,
            ).read_snapshot()
        except Exception as exc:
            # Preserve the collector's historical catch-all error behavior.
            return None, str(exc)

        reading = solakon_reading_from_snapshot(snapshot)
        if reading is not None:
            return reading, None
        if snapshot.error:
            _prefix, separator, detail = snapshot.error.partition(": ")
            return None, detail if separator else snapshot.error
        return None, "Keine Solakon-Messwerte verfügbar."

    def _read_grid_meter_snapshot(
        self,
        config: dict[str, Any],
    ) -> tuple[Optional[DeviceSnapshot], Optional[str]]:
        """Read or reuse the official grid-meter snapshot safely."""

        now_monotonic = self._monotonic()
        poll_interval = max(
            1.0,
            float(config.get("poll_interval_seconds", 5)),
        )
        if (
            self._last_grid_meter_snapshot is not None
            and self._last_grid_meter_poll_monotonic is not None
            and max(
                0.0,
                now_monotonic - self._last_grid_meter_poll_monotonic,
            )
            < poll_interval
        ):
            return self._last_grid_meter_snapshot, None

        try:
            snapshot = self._create_grid_meter_adapter(config).read_snapshot()
        except Exception:
            # Do not expose arbitrary exception text because it may
            # contain request details or configured credentials.
            self._last_grid_meter_snapshot = None
            self._last_grid_meter_poll_monotonic = now_monotonic
            return (
                None,
                "Unexpected grid-meter adapter failure.",
            )

        self._last_grid_meter_snapshot = snapshot
        self._last_grid_meter_poll_monotonic = now_monotonic
        return snapshot, None

    def _read_shelly_snapshot_result(
        self,
        config: dict[str, Any],
        *,
        source_id: str,
        name: str,
        role: MeasurementRole,
    ) -> tuple[
        Optional[MeterReading],
        Optional[DeviceSnapshot],
        Optional[str],
    ]:
        """Read Shelly and retain the normalized snapshot for persistence."""

        try:
            snapshot = ShellyMeasurementAdapter(
                source_id=source_id,
                name=name,
                device=config,
                role=role,
                reader=self.reader,
            ).read_snapshot()
        except Exception as exc:
            # Preserve the collector's historical catch-all error behavior.
            return None, None, str(exc)

        reading = meter_reading_from_snapshot(snapshot, role)
        if reading is not None:
            return reading, snapshot, None
        if snapshot.error:
            _prefix, separator, detail = snapshot.error.partition(": ")
            return (
                None,
                snapshot,
                detail if separator else snapshot.error,
            )
        return None, snapshot, "Keine Shelly-Messwerte verfügbar."

    def _read_shelly_snapshot(
        self,
        config: dict[str, Any],
        *,
        source_id: str,
        name: str,
        role: MeasurementRole,
    ) -> tuple[Optional[MeterReading], Optional[str]]:
        """Preserve the existing temporary normalized Shelly bridge API."""

        reading, _snapshot, error = self._read_shelly_snapshot_result(
            config,
            source_id=source_id,
            name=name,
            role=role,
        )
        return reading, error

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
            bool(config.get(name, {}).get("enabled"))
            for name in (
                "grid_meter",
                "house_meter",
                "solakon_meter",
                "solakon_one",
            )
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

    @staticmethod
    def _select_grid_measurements(
        *,
        fallback_source: str,
        official_enabled: bool,
        official_name: str,
        official_snapshot: Optional[DeviceSnapshot],
        house_reading: Optional[MeterReading],
        solakon: Optional[SolakonOneReading],
    ) -> _GridMeasurementSelection:
        """Prefer valid official values and mark legacy fallback."""

        official_power = _snapshot_measurement_value(
            official_snapshot,
            Metric.GRID_POWER,
        )
        if official_power is not None and official_snapshot is not None:
            import_power = _snapshot_measurement_value(
                official_snapshot,
                Metric.GRID_IMPORT_POWER,
            )
            export_power = _snapshot_measurement_value(
                official_snapshot,
                Metric.GRID_EXPORT_POWER,
            )
            return _GridMeasurementSelection(
                grid_power_w=official_power,
                grid_import_power_w=(
                    import_power
                    if import_power is not None
                    else max(0.0, official_power)
                ),
                grid_export_power_w=(
                    export_power
                    if export_power is not None
                    else max(0.0, -official_power)
                ),
                source_label=official_name,
                source_id=official_snapshot.source_id,
            )

        fallback_power, fallback_label = Collector._select_grid_power(
            fallback_source,
            house_reading,
            solakon,
        )
        if official_enabled:
            fallback_label = (
                f"{fallback_label} (Fallback)"
                if fallback_power is not None
                else ("Keine Quelle (offizieller Netzstromzähler nicht verfügbar)")
            )
        return _GridMeasurementSelection(
            grid_power_w=fallback_power,
            grid_import_power_w=(
                max(0.0, fallback_power) if fallback_power is not None else None
            ),
            grid_export_power_w=(
                max(0.0, -fallback_power) if fallback_power is not None else None
            ),
            source_label=fallback_label,
            source_id=_legacy_grid_source_id(
                fallback_source=fallback_source,
                fallback_power=fallback_power,
                house_reading=house_reading,
                solakon=solakon,
            ),
        )

    def collect_once(self) -> dict[str, Any]:
        config = self.config_manager.get()
        if not self._has_enabled_source(config):
            raise ValueError(
                "Keine Messstelle aktiviert. Bitte zuerst die Konfiguration prüfen."
            )

        now = self._now()
        now_epoch = now.timestamp()
        grid_cfg = config.get("grid_meter", {})
        house_cfg = config["house_meter"]
        solar_cfg = config["solakon_meter"]
        one_cfg = config["solakon_one"]

        errors: list[str] = []
        grid_meter_snapshot: Optional[DeviceSnapshot] = None
        house_reading: Optional[MeterReading] = None
        house_snapshot: Optional[DeviceSnapshot] = None
        solar_reading: Optional[MeterReading] = None
        solakon_reading: Optional[SolakonOneReading] = None

        if grid_cfg.get("enabled"):
            (
                grid_meter_snapshot,
                grid_meter_error,
            ) = self._read_grid_meter_snapshot(grid_cfg)
            if grid_meter_error:
                errors.append(f"Offizieller Netzstromzähler: {grid_meter_error}")
            elif grid_meter_snapshot is not None and grid_meter_snapshot.error:
                errors.append(
                    f"Offizieller Netzstromzähler: {grid_meter_snapshot.error}"
                )
        else:
            self._last_grid_meter_snapshot = None
            self._last_grid_meter_poll_monotonic = None

        if one_cfg.get("enabled"):
            solakon_reading, solakon_error = self._read_solakon_snapshot(one_cfg)
            if solakon_error:
                errors.append(f"Solakon ONE: {solakon_error}")

        if house_cfg.get("enabled"):
            (
                house_reading,
                house_snapshot,
                house_error,
            ) = self._read_shelly_snapshot_result(
                house_cfg,
                source_id="house_meter",
                name="Hausanschluss",
                role=MeasurementRole.GRID_METER,
            )
            if house_error:
                errors.append(f"Hausanschluss: {house_error}")

        if solar_cfg.get("enabled"):
            solar_reading, solar_error = self._read_shelly_snapshot(
                solar_cfg,
                source_id="solakon_meter",
                name="Shelly AC-Erzeugung",
                role=MeasurementRole.PLANT_METER,
            )
            if solar_error:
                errors.append(f"Shelly AC-Erzeugung: {solar_error}")

        shelly_solar_power = max(0.0, solar_reading.power_w) if solar_reading else None
        solar_power, solar_source = self._select_solar_power(
            config["general"].get("solar_power_source", "auto"),
            shelly_solar_power,
            solakon_reading,
        )
        grid_selection = self._select_grid_measurements(
            fallback_source=config["general"].get(
                "grid_power_source",
                "auto",
            ),
            official_enabled=bool(grid_cfg.get("enabled")),
            official_name=(
                str(grid_cfg.get("name") or "Offizieller Netzstromzähler").strip()
                or "Offizieller Netzstromzähler"
            ),
            official_snapshot=grid_meter_snapshot,
            house_reading=house_reading,
            solakon=solakon_reading,
        )
        grid_power = grid_selection.grid_power_w
        grid_source = grid_selection.source_label
        grid_meter_persistence_snapshot = _grid_meter_snapshot_for_persistence(
            grid_meter_snapshot,
            config=grid_cfg,
            active_source_id=grid_selection.source_id,
        )

        solakon_ac = solakon_reading.active_power_w if solakon_reading else None
        solakon_pv = solakon_reading.total_pv_power_w if solakon_reading else None
        solakon_battery = solakon_reading.battery_power_w if solakon_reading else None

        grid_import = grid_selection.grid_import_power_w
        feed_in = grid_selection.grid_export_power_w

        # For the household balance always prefer an AC measurement. The DC PV
        # input is useful as a production source, but must not be added directly
        # to the household grid balance while the battery is charging.
        balance_generation: Optional[float] = shelly_solar_power
        if balance_generation is None and solakon_ac is not None:
            balance_generation = max(0.0, solakon_ac)
        if balance_generation is None:
            balance_generation = solar_power

        house_power: Optional[float]
        self_consumption: Optional[float]

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
        phase_snapshot = (
            house_snapshot
            if str(house_cfg.get("type")) in _MULTI_PHASE_SHELLY_TYPES
            else None
        )
        sample_id = self._insert_sample(
            sample,
            phase_snapshot=phase_snapshot,
            grid_meter_snapshot=(grid_meter_persistence_snapshot),
            measurement_role=str(
                house_cfg.get(
                    "measurement_role",
                    "house_total",
                )
            ),
        )
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

    def _insert_sample(
        self,
        sample: dict[str, Any],
        *,
        phase_snapshot: DeviceSnapshot | None,
        grid_meter_snapshot: DeviceSnapshot | None,
        measurement_role: str,
    ) -> int:
        """Persist normalized details with test-double support."""

        insert_with_snapshots = getattr(
            self.database,
            "insert_sample_with_snapshots",
            None,
        )
        if callable(insert_with_snapshots):
            return int(
                insert_with_snapshots(
                    sample,
                    phase_snapshot=phase_snapshot,
                    grid_meter_snapshot=grid_meter_snapshot,
                    measurement_role=measurement_role,
                )
            )

        insert_with_phases = getattr(
            self.database,
            "insert_sample_with_phase_snapshot",
            None,
        )
        if callable(insert_with_phases):
            return int(
                insert_with_phases(
                    sample,
                    phase_snapshot,
                    measurement_role=measurement_role,
                )
            )
        return int(self.database.insert_sample(sample))

    def reset_state(self) -> None:
        with self._lock:
            self._last_sample = None
            self._last_error = ""
            self._cycles = 0
            self._started_at = None
            self._previous_power = None
            self._previous_epoch = None
            self._last_grid_meter_snapshot = None
            self._last_grid_meter_poll_monotonic = None

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


def _snapshot_measurement_value(
    snapshot: Optional[DeviceSnapshot],
    metric: Metric,
) -> Optional[float]:
    """Return one normalized GRID_METER value if available."""

    if snapshot is None:
        return None
    for measurement in snapshot.measurements:
        if (
            measurement.role is MeasurementRole.GRID_METER
            and measurement.metric is metric
        ):
            return float(measurement.value)
    return None


def _legacy_grid_source_id(
    *,
    fallback_source: str,
    fallback_power: Optional[float],
    house_reading: Optional[MeterReading],
    solakon: Optional[SolakonOneReading],
) -> Optional[str]:
    """Identify the compatible fallback source actually used."""

    if fallback_power is None:
        return None
    if fallback_source == "house_meter":
        return "house_meter"
    if fallback_source == "solakon_one":
        return "solakon_one"
    if house_reading is not None:
        return "house_meter"
    if solakon is not None and solakon.meter_power_w is not None:
        return "solakon_one"
    return None


def _grid_meter_snapshot_for_persistence(
    snapshot: Optional[DeviceSnapshot],
    *,
    config: dict[str, Any],
    active_source_id: Optional[str],
) -> Optional[DeviceSnapshot]:
    """Add non-sensitive identity and selection metadata."""

    if snapshot is None:
        return None

    metadata = dict(snapshot.metadata)
    metadata["source_name"] = (
        str(config.get("name") or "Offizieller Netzstromzähler").strip()
        or "Offizieller Netzstromzähler"
    )
    metadata["adapter"] = (
        str(config.get("adapter") or "tasmota_http").strip() or "tasmota_http"
    )
    if active_source_id is not None:
        metadata["active_source_id"] = active_source_id

    return DeviceSnapshot(
        source_id=snapshot.source_id,
        status=snapshot.status,
        measurements=snapshot.measurements,
        received_at=snapshot.received_at,
        error=snapshot.error,
        metadata=tuple(
            sorted(
                (
                    str(key),
                    str(value),
                )
                for key, value in metadata.items()
            )
        ),
    )


_MULTI_PHASE_SHELLY_TYPES: Final[frozenset[str]] = frozenset(
    {"shelly_3em_gen1", "shelly_pro_3em"}
)
