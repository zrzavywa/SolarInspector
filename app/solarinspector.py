#!/usr/bin/env python3
"""SolarInspector 4.0.1

Lokale Web-Anwendung zur Erfassung und Auswertung einer Solakon-Anlage.
Unterstützt Solakon ONE über read-only Modbus TCP sowie Shelly-Messgeräte.
"""

from __future__ import annotations

import argparse
import atexit
import csv
from contextlib import contextmanager
import io
import json
import math
import os
import random
import sqlite3
import threading
import time
import webbrowser
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from github_updater import UpdateCheckError, check_for_update
from typing import Any, Iterator, Optional

import requests
from flask import Flask, Response, flash, jsonify, redirect, render_template, request, url_for
from requests.auth import HTTPDigestAuth
from waitress import serve

from modbus_solakon import ModbusError, SolakonOneReader, SolakonOneReading


APP_VERSION = "4.0.1"
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "solarinspector.db"
LOG_PATH = DATA_DIR / "solarinspector.log"
PID_PATH = DATA_DIR / "solarinspector.pid"

DEFAULT_CONFIG: dict[str, Any] = {
    "general": {
        "project_name": "SolarInspector",
        "site_name": "Solakon Anlage",
        "poll_interval_seconds": 10,
        "auto_start_collection": False,
        "bind_host": "127.0.0.1",
        "port": 8787,
        "open_browser": True,
        "solar_power_source": "auto",
        "grid_power_source": "auto",
    },
    "solakon_one": {
        "enabled": False,
        "host": "",
        "port": 502,
        "device_id": 1,
        "timeout_seconds": 5,
        "simulation": False,
    },
    "house_meter": {
        "enabled": False,
        "type": "shelly_3em_gen1",
        "host": "",
        "username": "",
        "password": "",
        "timeout_seconds": 3,
        "direction_factor": 1,
    },
    "solakon_meter": {
        "enabled": False,
        "type": "shelly_pm_mini_gen3",
        "host": "",
        "username": "",
        "password": "",
        "timeout_seconds": 3,
        "direction_factor": 1,
    },
}

DEVICE_TYPES = {
    "shelly_pm_mini_gen3": "Shelly PM Mini Gen 3 / PM1",
    "shelly_3em_gen1": "Shelly 3EM Gen 1",
    "shelly_pro_3em": "Shelly Pro 3EM / EM RPC",
    "simulation": "Simulation",
}


def get_installed_version() -> str:
    version_file = Path(__file__).resolve().parent.parent / "VERSION"

    try:
        version = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"

    return version or "0.0.0"


def log(message: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"{stamp} {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigManager:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._config = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            self.path.write_text(
                json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return deep_merge(DEFAULT_CONFIG, {})
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            return self.validate(deep_merge(DEFAULT_CONFIG, loaded))
        except Exception as exc:
            log(f"Konfiguration konnte nicht gelesen werden: {exc}; Standardwerte werden verwendet.")
            return deep_merge(DEFAULT_CONFIG, {})

    def get(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._config))

    def save(self, config: dict[str, Any]) -> None:
        validated = self.validate(deep_merge(DEFAULT_CONFIG, config))
        with self._lock:
            temp = self.path.with_suffix(".tmp")
            temp.write_text(
                json.dumps(validated, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            temp.replace(self.path)
            self._config = validated

    @staticmethod
    def validate(config: dict[str, Any]) -> dict[str, Any]:
        general = config["general"]
        general["poll_interval_seconds"] = max(
            2, min(3600, int(general.get("poll_interval_seconds", 10)))
        )
        general["port"] = max(1, min(65535, int(general.get("port", 8787))))
        general["bind_host"] = str(general.get("bind_host", "127.0.0.1")).strip() or "127.0.0.1"
        general["project_name"] = str(general.get("project_name", "SolarInspector")).strip()
        general["site_name"] = str(general.get("site_name", "")).strip()
        general["auto_start_collection"] = bool(general.get("auto_start_collection", False))
        general["open_browser"] = bool(general.get("open_browser", True))
        if general.get("solar_power_source") not in {"auto", "shelly_ac", "solakon_ac", "solakon_pv"}:
            general["solar_power_source"] = "auto"
        if general.get("grid_power_source") not in {"auto", "house_meter", "solakon_one"}:
            general["grid_power_source"] = "auto"

        solakon = config["solakon_one"]
        solakon["enabled"] = bool(solakon.get("enabled", False))
        solakon["host"] = str(solakon.get("host", "")).strip().replace("http://", "").replace("https://", "").rstrip("/")
        solakon["port"] = max(1, min(65535, int(solakon.get("port", 502))))
        solakon["device_id"] = max(1, min(247, int(solakon.get("device_id", 1))))
        solakon["timeout_seconds"] = max(1, min(30, int(solakon.get("timeout_seconds", 5))))
        solakon["simulation"] = bool(solakon.get("simulation", False))

        for role in ("house_meter", "solakon_meter"):
            device = config[role]
            if device.get("type") not in DEVICE_TYPES:
                device["type"] = DEFAULT_CONFIG[role]["type"]
            device["enabled"] = bool(device.get("enabled", False))
            device["host"] = str(device.get("host", "")).strip().replace("http://", "").replace("https://", "").rstrip("/")
            device["username"] = str(device.get("username", "")).strip()
            device["password"] = str(device.get("password", ""))
            device["timeout_seconds"] = max(
                1, min(30, int(device.get("timeout_seconds", 3)))
            )
            try:
                factor = int(device.get("direction_factor", 1))
            except (TypeError, ValueError):
                factor = 1
            device["direction_factor"] = -1 if factor < 0 else 1
        return config


@dataclass
class MeterReading:
    power_w: float
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    power_factor: Optional[float] = None
    frequency_hz: Optional[float] = None
    energy_total_wh: Optional[float] = None
    returned_energy_total_wh: Optional[float] = None
    source: str = ""


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
            voltage_v=(sum(valid_voltages) / len(valid_voltages)) if valid_voltages else None,
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
            voltage_v=(sum(valid_voltages) / len(valid_voltages)) if valid_voltages else None,
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


class Database:
    def __init__(self, path: Path):
        self.path = path
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_epoch REAL NOT NULL,
                    ts_local TEXT NOT NULL,
                    grid_power_w REAL,
                    solar_power_w REAL,
                    house_power_w REAL,
                    grid_import_w REAL,
                    feed_in_w REAL,
                    self_consumption_w REAL,
                    voltage_v REAL,
                    current_a REAL,
                    power_factor REAL,
                    frequency_hz REAL,
                    grid_import_wh REAL NOT NULL DEFAULT 0,
                    feed_in_wh REAL NOT NULL DEFAULT 0,
                    solar_wh REAL NOT NULL DEFAULT 0,
                    house_wh REAL NOT NULL DEFAULT 0,
                    self_consumption_wh REAL NOT NULL DEFAULT 0,
                    house_ok INTEGER NOT NULL DEFAULT 0,
                    solar_ok INTEGER NOT NULL DEFAULT 0,
                    error_text TEXT
                )
                """
            )
            existing_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(samples)").fetchall()
            }
            additional_columns = {
                "shelly_solar_power_w": "REAL",
                "solakon_pv_power_w": "REAL",
                "solakon_ac_power_w": "REAL",
                "solakon_battery_power_w": "REAL",
                "solakon_battery_soc_pct": "REAL",
                "solakon_load_power_w": "REAL",
                "solakon_meter_power_w": "REAL",
                "solakon_temperature_c": "REAL",
                "solakon_daily_pv_kwh": "REAL",
                "solakon_total_pv_kwh": "REAL",
                "solakon_pv1_power_w": "REAL",
                "solakon_pv2_power_w": "REAL",
                "solakon_pv3_power_w": "REAL",
                "solakon_pv4_power_w": "REAL",
                "solar_difference_w": "REAL",
                "solar_difference_pct": "REAL",
                "solar_source": "TEXT",
                "grid_source": "TEXT",
                "solakon_model": "TEXT",
                "solakon_serial": "TEXT",
                "solakon_status": "TEXT",
                "solakon_ok": "INTEGER NOT NULL DEFAULT 0",
                "shelly_solar_wh": "REAL NOT NULL DEFAULT 0",
                "solakon_pv_wh": "REAL NOT NULL DEFAULT 0",
                "solakon_ac_wh": "REAL NOT NULL DEFAULT 0",
                "battery_charge_wh": "REAL NOT NULL DEFAULT 0",
                "battery_discharge_wh": "REAL NOT NULL DEFAULT 0"
            }
            for column, definition in additional_columns.items():
                if column not in existing_columns:
                    conn.execute(f"ALTER TABLE samples ADD COLUMN {column} {definition}")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_samples_ts_epoch ON samples(ts_epoch)"
            )
            conn.commit()

    def insert_sample(self, sample: dict[str, Any]) -> int:
        columns = list(sample.keys())
        placeholders = ",".join("?" for _ in columns)
        sql = f"INSERT INTO samples ({','.join(columns)}) VALUES ({placeholders})"
        with self.connect() as conn:
            cursor = conn.execute(sql, [sample[column] for column in columns])
            conn.commit()
            return int(cursor.lastrowid)

    def latest(self) -> Optional[dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM samples ORDER BY ts_epoch DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def rows_between(self, start_epoch: float, end_epoch: float) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM samples
                WHERE ts_epoch >= ? AND ts_epoch < ?
                ORDER BY ts_epoch
                """,
                (start_epoch, end_epoch),
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count,
                       MIN(ts_epoch) AS first_epoch,
                       MAX(ts_epoch) AS last_epoch
                FROM samples
                """
            ).fetchone()
        result = dict(row)
        result["db_size_bytes"] = self.path.stat().st_size if self.path.exists() else 0
        return result

    def delete_all(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM samples")
            conn.commit()
            conn.execute("VACUUM")


class Collector:
    def __init__(self, config_manager: ConfigManager, database: Database):
        self.config_manager = config_manager
        self.database = database
        self.reader = ShellyReader()
        self.solakon_reader = SolakonOneReader()
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
    def _has_enabled_source(config: dict[str, Any]) -> bool:
        return any(
            config[name].get("enabled")
            for name in ("house_meter", "solakon_meter", "solakon_one")
        )

    def start(self) -> bool:
        config = self.config_manager.get()
        if not self._has_enabled_source(config):
            with self._lock:
                self._last_error = "Keine Messstelle aktiviert. Bitte zuerst die Konfiguration prüfen."
            log(self._last_error)
            return False
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop_event.clear()
            self._started_at = datetime.now().astimezone().isoformat(timespec="seconds")
            self._thread = threading.Thread(
                target=self._run,
                name="SolarInspectorCollector",
                daemon=True,
            )
            self._thread.start()
            log("Datenerfassung gestartet.")
            return True

    def stop(self) -> bool:
        with self._lock:
            if not self._thread or not self._thread.is_alive():
                return False
            self._stop_event.set()
            thread = self._thread
        thread.join(timeout=10)
        log("Datenerfassung gestoppt.")
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
        solakon_ac = None if solakon is None or solakon.active_power_w is None else max(0.0, solakon.active_power_w)
        solakon_pv = None if solakon is None or solakon.total_pv_power_w is None else max(0.0, solakon.total_pv_power_w)
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
        return solakon_pv, "Solakon ONE PV-Eingang (Auto)" if solakon_pv is not None else "Keine Quelle"

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
        return solakon_grid, "Solakon ONE Meter (Auto)" if solakon_grid is not None else "Keine Quelle"

    def collect_once(self) -> dict[str, Any]:
        config = self.config_manager.get()
        if not self._has_enabled_source(config):
            raise ValueError("Keine Messstelle aktiviert. Bitte zuerst die Konfiguration prüfen.")

        now = datetime.now().astimezone()
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
            "solakon_pv_power_w": max(0.0, solakon_pv) if solakon_pv is not None else None,
            "solakon_ac_power_w": max(0.0, solakon_ac) if solakon_ac is not None else None,
            "battery_charge_w": max(0.0, solakon_battery) if solakon_battery is not None else None,
            "battery_discharge_w": max(0.0, -solakon_battery) if solakon_battery is not None else None,
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
                energy[energy_key] = ((float(current) + float(previous)) / 2.0) * dt_seconds / 3600.0

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
            "power_factor": preferred.power_factor if preferred else (solakon_reading.power_factor if solakon_reading else None),
            "frequency_hz": preferred.frequency_hz if preferred else (solakon_reading.grid_frequency_hz if solakon_reading else None),
            **energy,
            "house_ok": 1 if house_reading else 0,
            "solar_ok": 1 if solar_reading else 0,
            "error_text": " | ".join(errors),
            "shelly_solar_power_w": shelly_solar_power,
            "solakon_pv_power_w": solakon_pv,
            "solakon_ac_power_w": solakon_ac,
            "solakon_battery_power_w": solakon_battery,
            "solakon_battery_soc_pct": solakon_reading.battery_soc_pct if solakon_reading else None,
            "solakon_load_power_w": solakon_reading.load_power_w if solakon_reading else None,
            "solakon_meter_power_w": solakon_reading.meter_power_w if solakon_reading else None,
            "solakon_temperature_c": solakon_reading.internal_temperature_c if solakon_reading else None,
            "solakon_daily_pv_kwh": solakon_reading.daily_pv_energy_kwh if solakon_reading else None,
            "solakon_total_pv_kwh": solakon_reading.total_pv_energy_kwh if solakon_reading else None,
            "solakon_pv1_power_w": solakon_reading.pv1_power_w if solakon_reading else None,
            "solakon_pv2_power_w": solakon_reading.pv2_power_w if solakon_reading else None,
            "solakon_pv3_power_w": solakon_reading.pv3_power_w if solakon_reading else None,
            "solakon_pv4_power_w": solakon_reading.pv4_power_w if solakon_reading else None,
            "solar_difference_w": solar_difference,
            "solar_difference_pct": solar_difference_pct,
            "solar_source": solar_source,
            "grid_source": grid_source,
            "solakon_model": solakon_reading.model_name if solakon_reading else None,
            "solakon_serial": solakon_reading.serial_number if solakon_reading else None,
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
            log("Messzyklus mit Warnung: " + " | ".join(errors))
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
            cycle_started = time.monotonic()
            try:
                self.collect_once()
            except Exception as exc:
                with self._lock:
                    self._last_error = str(exc)
                log(f"Messzyklus fehlgeschlagen: {exc}")
            interval = self.config_manager.get()["general"]["poll_interval_seconds"]
            elapsed = time.monotonic() - cycle_started
            self._stop_event.wait(max(0.2, interval - elapsed))

def parse_anchor(value: Optional[str]) -> date:
    if not value:
        return datetime.now().astimezone().date()
    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.now().astimezone().date()


def period_bounds(period: str, anchor: date) -> tuple[datetime, datetime, list[str], str]:
    tz = datetime.now().astimezone().tzinfo
    weekdays_short = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    weekdays_long = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    if period == "week":
        start_date = anchor - timedelta(days=anchor.weekday())
        start = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end = start + timedelta(days=7)
        labels = [
            f"{weekdays_short[i]} {(start_date + timedelta(days=i)):%d.%m.}"
            for i in range(7)
        ]
        title = f"Woche {start_date.isocalendar().week} · {start_date:%d.%m.}–{(start_date + timedelta(days=6)):%d.%m.%Y}"
    elif period == "year":
        start = datetime(anchor.year, 1, 1, tzinfo=tz)
        end = datetime(anchor.year + 1, 1, 1, tzinfo=tz)
        labels = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
        title = f"Jahr {anchor.year}"
    else:
        period = "day"
        start = datetime.combine(anchor, datetime.min.time(), tzinfo=tz)
        end = start + timedelta(days=1)
        labels = [f"{hour:02d}:00" for hour in range(24)]
        title = f"{weekdays_long[anchor.weekday()]}, {anchor:%d.%m.%Y}"
    return start, end, labels, title


def bucket_index(period: str, start: datetime, sample_dt: datetime) -> int:
    if period == "week":
        return (sample_dt.date() - start.date()).days
    if period == "year":
        return sample_dt.month - 1
    return sample_dt.hour


def build_dashboard(database: Database, period: str, anchor: date) -> dict[str, Any]:
    start, end, labels, title = period_bounds(period, anchor)
    rows = database.rows_between(start.timestamp(), end.timestamp())
    series_keys = [
        "solar_wh",
        "house_wh",
        "grid_import_wh",
        "feed_in_wh",
        "self_consumption_wh",
        "shelly_solar_wh",
        "solakon_pv_wh",
        "solakon_ac_wh",
        "battery_charge_wh",
        "battery_discharge_wh",
    ]
    buckets = {key: [0.0] * len(labels) for key in series_keys}
    totals = {key: 0.0 for key in series_keys}
    soc_buckets: list[list[float]] = [[] for _ in labels]
    all_soc: list[float] = []
    difference_values: list[float] = []
    difference_pct_values: list[float] = []

    for row in rows:
        sample_dt = datetime.fromtimestamp(float(row["ts_epoch"])).astimezone()
        index = bucket_index(period, start, sample_dt)
        if not (0 <= index < len(labels)):
            continue
        for key in series_keys:
            value = float(row.get(key) or 0.0)
            buckets[key][index] += value
            totals[key] += value
        soc = row.get("solakon_battery_soc_pct")
        if soc is not None:
            soc_value = float(soc)
            soc_buckets[index].append(soc_value)
            all_soc.append(soc_value)
        if row.get("solar_difference_w") is not None:
            difference_values.append(float(row["solar_difference_w"]))
        if row.get("solar_difference_pct") is not None:
            difference_pct_values.append(float(row["solar_difference_pct"]))

    solar = totals["solar_wh"]
    house = totals["house_wh"]
    self_use = totals["self_consumption_wh"]
    latest_row = rows[-1] if rows else None

    return {
        "period": period,
        "anchor": anchor.isoformat(),
        "title": title,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "labels": labels,
        "series": {
            "solar_kwh": [round(v / 1000.0, 4) for v in buckets["solar_wh"]],
            "house_kwh": [round(v / 1000.0, 4) for v in buckets["house_wh"]],
            "grid_import_kwh": [round(v / 1000.0, 4) for v in buckets["grid_import_wh"]],
            "feed_in_kwh": [round(v / 1000.0, 4) for v in buckets["feed_in_wh"]],
            "self_consumption_kwh": [round(v / 1000.0, 4) for v in buckets["self_consumption_wh"]],
            "solakon_pv_kwh": [round(v / 1000.0, 4) for v in buckets["solakon_pv_wh"]],
            "solakon_ac_kwh": [round(v / 1000.0, 4) for v in buckets["solakon_ac_wh"]],
            "battery_charge_kwh": [round(v / 1000.0, 4) for v in buckets["battery_charge_wh"]],
            "battery_discharge_kwh": [round(v / 1000.0, 4) for v in buckets["battery_discharge_wh"]],
            "battery_soc_avg": [
                round(sum(values) / len(values), 1) if values else None
                for values in soc_buckets
            ],
        },
        "kpi": {
            "solar_kwh": round(solar / 1000.0, 3),
            "house_kwh": round(house / 1000.0, 3),
            "grid_import_kwh": round(totals["grid_import_wh"] / 1000.0, 3),
            "feed_in_kwh": round(totals["feed_in_wh"] / 1000.0, 3),
            "self_consumption_kwh": round(self_use / 1000.0, 3),
            "self_consumption_pct": round((self_use / solar * 100.0), 1) if solar > 0 else None,
            "autarky_pct": round((self_use / house * 100.0), 1) if house > 0 else None,
            "sample_count": len(rows),
            "shelly_ac_kwh": round(totals["shelly_solar_wh"] / 1000.0, 3),
            "solakon_pv_kwh": round(totals["solakon_pv_wh"] / 1000.0, 3),
            "solakon_ac_kwh": round(totals["solakon_ac_wh"] / 1000.0, 3),
            "battery_charge_kwh": round(totals["battery_charge_wh"] / 1000.0, 3),
            "battery_discharge_kwh": round(totals["battery_discharge_wh"] / 1000.0, 3),
            "battery_soc_avg": round(sum(all_soc) / len(all_soc), 1) if all_soc else None,
            "battery_soc_min": round(min(all_soc), 1) if all_soc else None,
            "battery_soc_max": round(max(all_soc), 1) if all_soc else None,
            "difference_avg_w": round(sum(difference_values) / len(difference_values), 1) if difference_values else None,
            "difference_avg_pct": round(sum(difference_pct_values) / len(difference_pct_values), 1) if difference_pct_values else None,
            "solar_source": latest_row.get("solar_source") if latest_row else None,
            "grid_source": latest_row.get("grid_source") if latest_row else None,
        },
    }


config_manager = ConfigManager(CONFIG_PATH)
database = Database(DB_PATH)
collector = Collector(config_manager, database)

app = Flask(__name__)
secret_key = os.environ.get("SOLARINSPECTOR_SECRET")
if not secret_key:
    raise RuntimeError(
        "SOLARINSPECTOR_SECRET ist nicht gesetzt. "
        "Bitte einen sicheren zufälligen Schlüssel konfigurieren."
    )
app.secret_key = secret_key


@app.context_processor
def template_context() -> dict[str, Any]:
    config = config_manager.get()
    return {
        "app_version": APP_VERSION,
        "project_name": config["general"]["project_name"],
        "site_name": config["general"]["site_name"],
        "collector_running": collector.is_running(),
        "device_types": DEVICE_TYPES,
        "solar_source_types": {
            "auto": "Automatisch: Shelly AC, sonst Solakon ONE AC",
            "shelly_ac": "Shelly PM Mini Gen 3 – AC-Ausgang",
            "solakon_ac": "Solakon ONE – AC-Wirkleistung",
            "solakon_pv": "Solakon ONE – PV-Eingangsleistung (DC)",
        },
        "grid_source_types": {
            "auto": "Automatisch: separate Hausmessung, sonst Solakon ONE Meter",
            "house_meter": "Separate Hausmessung (Shelly 3EM)",
            "solakon_one": "Solakon ONE – verbundenes Meter/CT",
        },
    }


@app.get("/")
def dashboard_page():
    return render_template("dashboard.html", active_page="dashboard")


@app.get("/acquisition")
def acquisition_page():
    return render_template(
        "acquisition.html",
        active_page="acquisition",
        status=collector.status(),
        config=config_manager.get(),
    )


@app.route("/configuration", methods=["GET", "POST"])
def configuration_page():
    if request.method == "POST":
        current = config_manager.get()
        form = request.form
        general = current["general"]
        general.update(
            {
                "project_name": form.get("project_name", ""),
                "site_name": form.get("site_name", ""),
                "poll_interval_seconds": form.get("poll_interval_seconds", "10"),
                "auto_start_collection": form.get("auto_start_collection") == "on",
                "bind_host": form.get("bind_host", "127.0.0.1"),
                "port": form.get("port", "8787"),
                "open_browser": form.get("open_browser") == "on",
                "solar_power_source": form.get("solar_power_source", "auto"),
                "grid_power_source": form.get("grid_power_source", "auto"),
            }
        )
        current["solakon_one"].update(
            {
                "enabled": form.get("solakon_one_enabled") == "on",
                "host": form.get("solakon_one_host", ""),
                "port": form.get("solakon_one_port", "502"),
                "device_id": form.get("solakon_one_device_id", "1"),
                "timeout_seconds": form.get("solakon_one_timeout_seconds", "5"),
                "simulation": form.get("solakon_one_simulation") == "on",
            }
        )
        for role in ("house_meter", "solakon_meter"):
            current[role].update(
                {
                    "enabled": form.get(f"{role}_enabled") == "on",
                    "type": form.get(f"{role}_type", current[role]["type"]),
                    "host": form.get(f"{role}_host", ""),
                    "username": form.get(f"{role}_username", ""),
                    "password": form.get(f"{role}_password", ""),
                    "timeout_seconds": form.get(f"{role}_timeout_seconds", "3"),
                    "direction_factor": form.get(f"{role}_direction_factor", "1"),
                }
            )
        try:
            config_manager.save(current)
            flash("Konfiguration gespeichert. Host und Port werden nach einem Neustart wirksam.", "success")
        except Exception as exc:
            flash(f"Konfiguration konnte nicht gespeichert werden: {exc}", "error")
        return redirect(url_for("configuration_page"))
    return render_template(
        "configuration.html",
        active_page="configuration",
        config=config_manager.get(),
    )


@app.get("/data")
def data_page():
    return render_template(
        "data.html",
        active_page="data",
        stats=database.stats(),
        db_path=str(DB_PATH),
    )


@app.post("/api/start")
def api_start():
    started = collector.start()
    status = collector.status()
    if not started and not status["running"]:
        return jsonify({"ok": False, "started": False, "error": status["last_error"], "status": status}), 400
    return jsonify({"ok": True, "started": started, "status": status})


@app.post("/api/stop")
def api_stop():
    stopped = collector.stop()
    return jsonify({"ok": True, "stopped": stopped, "status": collector.status()})


@app.post("/api/collect-once")
def api_collect_once():
    try:
        sample = collector.collect_once()
        return jsonify({"ok": True, "sample": sample})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/status")
def api_status():
    return jsonify(collector.status())


@app.get("/api/live")
def api_live():
    latest = database.latest()
    status = collector.status()
    if latest:
        latest["age_seconds"] = max(0, int(time.time() - float(latest["ts_epoch"])))
    return jsonify({"latest": latest, "collector": status})


@app.get("/api/dashboard")
def api_dashboard():
    period = request.args.get("period", "day")
    if period not in {"day", "week", "year"}:
        period = "day"
    anchor = parse_anchor(request.args.get("anchor"))
    return jsonify(build_dashboard(database, period, anchor))


@app.post("/api/test-device/<role>")
def api_test_device(role: str):
    if role not in {"house_meter", "solakon_meter"}:
        return jsonify({"ok": False, "error": "Unbekannte Messstelle."}), 404
    root_config = config_manager.get()
    payload = request.get_json(silent=True) or {}
    if payload:
        root_config[role].update({
            "enabled": bool(payload.get("enabled", True)),
            "type": payload.get("type", root_config[role]["type"]),
            "host": payload.get("host", ""),
            "username": payload.get("username", ""),
            "password": payload.get("password", ""),
            "timeout_seconds": payload.get("timeout_seconds", 3),
            "direction_factor": payload.get("direction_factor", 1),
        })
        root_config = ConfigManager.validate(root_config)
    config = root_config[role]
    if not config.get("enabled"):
        return jsonify({"ok": False, "error": "Messstelle ist deaktiviert."}), 400
    try:
        reading = collector.reader.read(config, role)
        return jsonify({"ok": True, "reading": asdict(reading)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


@app.post("/api/test-solakon-one")
def api_test_solakon_one():
    root_config = config_manager.get()
    payload = request.get_json(silent=True) or {}
    root_config["solakon_one"].update(
        {
            "enabled": bool(payload.get("enabled", True)),
            "host": payload.get("host", ""),
            "port": payload.get("port", 502),
            "device_id": payload.get("device_id", 1),
            "timeout_seconds": payload.get("timeout_seconds", 5),
            "simulation": bool(payload.get("simulation", False)),
        }
    )
    try:
        root_config = ConfigManager.validate(root_config)
        config = root_config["solakon_one"]
        if not config.get("enabled"):
            return jsonify({"ok": False, "error": "Solakon ONE ist deaktiviert."}), 400
        reading = collector.solakon_reader.test(config)
        return jsonify({"ok": True, "reading": reading.to_dict()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


@app.get("/api/export.csv")
def api_export_csv():
    start_date = parse_anchor(request.args.get("from"))
    end_date = parse_anchor(request.args.get("to")) + timedelta(days=1)
    tz = datetime.now().astimezone().tzinfo
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
    end = datetime.combine(end_date, datetime.min.time(), tzinfo=tz)
    rows = database.rows_between(start.timestamp(), end.timestamp())

    output = io.StringIO()
    fieldnames = [
        "ts_local",
        "grid_power_w",
        "solar_power_w",
        "house_power_w",
        "grid_import_w",
        "feed_in_w",
        "self_consumption_w",
        "solar_source",
        "grid_source",
        "shelly_solar_power_w",
        "solakon_pv_power_w",
        "solakon_ac_power_w",
        "solakon_battery_power_w",
        "solakon_battery_soc_pct",
        "solakon_load_power_w",
        "solakon_meter_power_w",
        "solakon_temperature_c",
        "solakon_daily_pv_kwh",
        "solakon_total_pv_kwh",
        "solakon_pv1_power_w",
        "solakon_pv2_power_w",
        "solakon_pv3_power_w",
        "solakon_pv4_power_w",
        "solar_difference_w",
        "solar_difference_pct",
        "solakon_model",
        "solakon_serial",
        "solakon_status",
        "voltage_v",
        "current_a",
        "power_factor",
        "frequency_hz",
        "grid_import_wh",
        "feed_in_wh",
        "solar_wh",
        "house_wh",
        "self_consumption_wh",
        "shelly_solar_wh",
        "solakon_pv_wh",
        "solakon_ac_wh",
        "battery_charge_wh",
        "battery_discharge_wh",
        "house_ok",
        "solar_ok",
        "solakon_ok",
        "error_text",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore", delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    filename = f"solarinspector_{start_date.isoformat()}_{(end_date - timedelta(days=1)).isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/delete-all")
def api_delete_all():
    collector.stop()
    database.delete_all()
    collector.reset_state()
    return jsonify({"ok": True})


@app.get("/api/system/version")
def api_system_version():
    return {
        "product": "SolarInspector",
        "version": get_installed_version(),
        "config_schema": 5,
    }


@app.get("/api/update/check")
def api_update_check():
    installed_version = get_installed_version()

    try:
        release = check_for_update(installed_version)
    except UpdateCheckError as exc:
        return {
            "status": "error",
            "installed_version": installed_version,
            "message": str(exc),
        }, 502

    return {
        "status": "ok",
        "installed_version": release.installed_version,
        "available_version": release.available_version,
        "update_available": release.update_available,
        "release_name": release.release_name,
        "release_notes": release.release_notes,
        "published_at": release.published_at,
        "release_url": release.html_url,
        "asset_name": release.asset_name,
        "asset_url": release.asset_url,
        "checksum_name": release.checksum_name,
        "checksum_url": release.checksum_url,
    }


def generate_demo_data(days: int = 400, interval_minutes: int = 15) -> None:
    log(f"Erzeuge Demodaten für {days} Tage.")
    end = datetime.now().astimezone()
    start = end - timedelta(days=days)
    current = start
    previous_values: Optional[dict[str, float]] = None
    battery_soc = 55.0

    while current <= end:
        seconds = current.hour * 3600 + current.minute * 60 + current.second
        season = 0.45 + 0.55 * max(0.0, math.sin(math.pi * (current.timetuple().tm_yday - 15) / 365.0))
        daylight = max(0.0, math.sin(math.pi * (seconds - 6 * 3600) / (14 * 3600)))
        weather = 0.55 + 0.45 * math.sin(current.toordinal() * 1.73) ** 2
        pv_dc = max(0.0, 980.0 * season * daylight * weather)
        house = 230.0 + 120.0 * (math.sin(seconds / 2100.0) ** 2)
        if 18 <= current.hour <= 22:
            house += 220.0

        desired_charge = max(0.0, min(420.0, pv_dc - house - 80.0)) if battery_soc < 94 else 0.0
        desired_discharge = max(0.0, min(300.0, house - pv_dc)) if battery_soc > 18 and (current.hour >= 18 or current.hour < 7) else 0.0
        battery_power = desired_charge - desired_discharge  # positive charging
        ac_solar = max(0.0, (pv_dc - desired_charge + desired_discharge) * 0.94)
        shelly_ac = max(0.0, ac_solar * (1.0 + 0.015 * math.sin(seconds / 1700.0)))
        grid = house - shelly_ac
        meter_power = -grid  # Solakon convention: feed-in positive

        dt_hours = interval_minutes / 60.0 if previous_values else 0.0
        battery_soc += (desired_charge * 0.93 - desired_discharge / 0.93) * dt_hours / 2110.0 * 100.0
        battery_soc = max(10.0, min(98.0, battery_soc))

        values = {
            "grid_import_w": max(0.0, grid),
            "feed_in_w": max(0.0, -grid),
            "solar_power_w": shelly_ac,
            "house_power_w": house,
            "self_consumption_w": min(shelly_ac, house),
            "shelly_solar_power_w": shelly_ac,
            "solakon_pv_power_w": pv_dc,
            "solakon_ac_power_w": ac_solar,
            "battery_charge_w": max(0.0, battery_power),
            "battery_discharge_w": max(0.0, -battery_power),
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
            "shelly_solar_power_w": shelly_ac,
            "solakon_pv_power_w": pv_dc,
            "solakon_ac_power_w": ac_solar,
            "solakon_battery_power_w": battery_power,
            "solakon_battery_soc_pct": battery_soc,
            "solakon_load_power_w": house,
            "solakon_meter_power_w": meter_power,
            "solakon_temperature_c": 28.0 + 8.0 * daylight,
            "solakon_daily_pv_kwh": 0.0,
            "solakon_total_pv_kwh": 1200.0,
            "solakon_pv1_power_w": pv_dc / 2.0,
            "solakon_pv2_power_w": pv_dc / 2.0,
            "solakon_pv3_power_w": 0.0,
            "solakon_pv4_power_w": 0.0,
            "solar_difference_w": difference,
            "solar_difference_pct": difference / ac_solar * 100.0 if ac_solar >= 10 else None,
            "solar_source": "Shelly AC (Auto)",
            "grid_source": "Separate Hausmessung (Auto)",
            "solakon_model": "Solakon ONE Simulation",
            "solakon_serial": "SIM-ONE-4000",
            "solakon_status": "Betrieb",
            "solakon_ok": 1,
        }
        database.insert_sample(sample)
        previous_values = values
        current += timedelta(minutes=interval_minutes)
    log("Demodaten fertig.")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SolarInspector 4.0.1")
    parser.add_argument("--host", help="Webserver-Bind-Adresse; überschreibt config.json")
    parser.add_argument("--port", type=int, help="Webserver-Port; überschreibt config.json")
    parser.add_argument("--no-browser", action="store_true", help="Browser nicht automatisch öffnen")
    parser.add_argument("--configuration", action="store_true", help="Beim Start direkt die Konfiguration öffnen")
    parser.add_argument("--demo-data", action="store_true", help="Demodaten erzeugen und beenden")
    parser.add_argument("--demo-days", type=int, default=400, help="Anzahl Tage für Demodaten")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.demo_data:
        generate_demo_data(days=max(1, args.demo_days))
        return

    config = config_manager.get()
    general = config["general"]
    host = args.host or general["bind_host"]
    port = args.port or int(general["port"])

    if general.get("auto_start_collection"):
        collector.start()

    should_open = general.get("open_browser", True) and not args.no_browser
    browse_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    page_path = "/configuration" if args.configuration else "/"
    url = f"http://{browse_host}:{port}{page_path}"
    PID_PATH.write_text(str(os.getpid()), encoding="ascii")
    if should_open:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    log(f"SolarInspector {APP_VERSION} läuft unter {url} (Bind: {host}:{port}).")
    serve(app, host=host, port=port, threads=8)


def cleanup_pid_file() -> None:
    try:
        if PID_PATH.exists() and PID_PATH.read_text(encoding="ascii").strip() == str(os.getpid()):
            PID_PATH.unlink()
    except OSError:
        pass


atexit.register(collector.stop)
atexit.register(cleanup_pid_file)

if __name__ == "__main__":
    main()
