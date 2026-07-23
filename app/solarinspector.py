#!/usr/bin/env python3
"""SolarInspector web application.

Lokale Web-Anwendung zur Erfassung und Auswertung einer Solakon-Anlage.
Unterstützt Solakon ONE über read-only Modbus TCP sowie Shelly-Messgeräte.
"""

from __future__ import annotations

import argparse
import atexit
import json
import math
import os
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from github_updater import (
    UpdateCheckError,
    UpdateVerificationError,
    check_for_update,
    download_and_verify_release,
)
from modbus_solakon import (
    SolakonOneReader,
)
from modbus_solakon import (
    SolakonOneReading as SolakonOneReading,
)
from solarinspector_core.adapters.shelly import (
    ShellyReader as _ShellyReader,
)
from solarinspector_core.adapters.shelly import (
    _float_or_none as _float_or_none_core,
)
from solarinspector_core.adapters.shelly import (
    _nested_float as _nested_float_core,
)
from solarinspector_core.config.defaults import (
    DEFAULT_CONFIG as _DEFAULT_CONFIG,
)
from solarinspector_core.config.defaults import (
    DEVICE_TYPES,
)
from solarinspector_core.config.manager import (
    ConfigManager as CoreConfigManager,
)
from solarinspector_core.config.manager import (
    deep_merge as _deep_merge,
)
from solarinspector_core.logging import log
from solarinspector_core.models.legacy import MeterReading as MeterReading
from solarinspector_core.paths import (
    BASE_DIR as _BASE_DIR,
)
from solarinspector_core.paths import (
    CONFIG_PATH,
    DB_PATH,
    PID_PATH,
    UPDATE_CACHE_DIR,
    UPDATE_REQUEST_PATH,
    UPDATE_STATUS_PATH,
)
from solarinspector_core.paths import (
    DATA_DIR as _DATA_DIR,
)
from solarinspector_core.paths import (
    LOG_PATH as LOG_PATH,
)
from solarinspector_core.persistence.database import Database
from solarinspector_core.services.collector import Collector as CoreCollector
from solarinspector_core.services.dashboard import build_dashboard as _build_dashboard
from solarinspector_core.services.periods import (
    bucket_index as _bucket_index,
)
from solarinspector_core.services.periods import (
    parse_anchor as _parse_anchor,
)
from solarinspector_core.services.periods import (
    period_bounds as _period_bounds,
)
from solarinspector_core.web.api import (
    build_collect_once_api_response,
    build_dashboard_api_response,
    build_delete_all_api_response,
    build_health_api_response,
    build_live_api_response,
    build_start_api_response,
    build_status_api_response,
    build_stop_api_response,
    build_system_version_api_response,
    build_test_device_api_response,
    build_test_solakon_one_api_response,
)
from solarinspector_core.web.configuration import (
    apply_configuration_form,
)
from solarinspector_core.web.context import build_template_context
from solarinspector_core.web.export import build_csv_export
from solarinspector_core.web.pages import (
    render_acquisition_page,
    render_dashboard_page,
    render_data_page,
)
from update_status import read_update_status, write_update_status
from waitress import serve

BASE_DIR = _BASE_DIR
DATA_DIR = _DATA_DIR
DEFAULT_CONFIG = _DEFAULT_CONFIG
deep_merge = _deep_merge
ShellyReader = _ShellyReader
_float_or_none = _float_or_none_core
_nested_float = _nested_float_core
parse_anchor = _parse_anchor
period_bounds = _period_bounds
bucket_index = _bucket_index
build_dashboard = _build_dashboard

def write_update_request(
    version: str,
    archive_path: str,
) -> None:
    payload = {
        "version": version,
        "archive_path": archive_path,
    }

    UPDATE_REQUEST_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = UPDATE_REQUEST_PATH.with_suffix(
        ".tmp"
    )

    temporary.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary.replace(UPDATE_REQUEST_PATH)


def get_installed_version() -> str:
    version_file = Path(__file__).resolve().parent.parent / "VERSION"

    try:
        version = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"

    return version or "0.0.0"


APP_VERSION = get_installed_version()



class ConfigManager(CoreConfigManager):
    """Compatibility wrapper for the historic public import path."""

    def __init__(self, path: Path) -> None:
        super().__init__(
            path,
            logger=lambda message: log(message),
        )








class Collector(CoreCollector):
    """Preserve the legacy SolarInspector Collector interface."""

    @staticmethod
    def _create_shelly_reader() -> ShellyReader:
        return ShellyReader()

    @staticmethod
    def _create_solakon_reader() -> SolakonOneReader:
        return SolakonOneReader()

    @staticmethod
    def _now() -> datetime:
        return datetime.now().astimezone()

    @staticmethod
    def _monotonic() -> float:
        return time.monotonic()

    @staticmethod
    def _log(message: str) -> None:
        log(message)

    @staticmethod
    def _create_thread(
        *,
        target: Any,
        name: str,
        daemon: bool,
    ) -> threading.Thread:
        return threading.Thread(
            target=target,
            name=name,
            daemon=daemon,
        )











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
    return build_template_context(
        config=config_manager.get(),
        collector_running=collector.is_running(),
        app_version=APP_VERSION,
        device_types=DEVICE_TYPES,
    )


@app.get("/")
def dashboard_page():
    return render_dashboard_page(render_template)


@app.get("/acquisition")
def acquisition_page():
    return render_acquisition_page(
        render_template,
        status=collector.status(),
        config=config_manager.get(),
    )


@app.route("/configuration", methods=["GET", "POST"])
def configuration_page():
    if request.method == "POST":
        current = apply_configuration_form(
            config_manager.get(),
            request.form,
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
    return render_data_page(
        render_template,
        stats=database.stats(),
        db_path=str(DB_PATH),
    )


@app.post("/api/start")
def api_start():
    payload, status_code = build_start_api_response(
        collector
    )
    response = jsonify(payload)
    if status_code is not None:
        return response, status_code
    return response


@app.post("/api/stop")
def api_stop():
    return jsonify(
        build_stop_api_response(collector)
    )


@app.post("/api/collect-once")
def api_collect_once():
    payload, status_code = (
        build_collect_once_api_response(
            collector
        )
    )
    response = jsonify(payload)
    if status_code is not None:
        return response, status_code
    return response


@app.get("/api/status")
def api_status():
    return jsonify(
        build_status_api_response(collector)
    )


@app.get("/api/health")
def api_health():
    return build_health_api_response(
        get_installed_version()
    )
    

@app.get("/api/live")
def api_live():
    return jsonify(
        build_live_api_response(
            database,
            collector,
            time.time(),
        )
    )


@app.get("/api/dashboard")
def api_dashboard():
    return jsonify(
        build_dashboard_api_response(
            database,
            request.args.get(
                "period",
                "day",
            ),
            request.args.get("anchor"),
        )
    )


@app.post("/api/test-device/<role>")
def api_test_device(role: str):
    payload, status_code = (
        build_test_device_api_response(
            config_manager.get(),
            role,
            request.get_json(
                silent=True
            )
            or {},
            collector.reader,
        )
    )

    response = jsonify(payload)

    if status_code is not None:
        return response, status_code

    return response


@app.post("/api/test-solakon-one")
def api_test_solakon_one():
    payload, status_code = (
        build_test_solakon_one_api_response(
            config_manager.get(),
            request.get_json(
                silent=True
            )
            or {},
            collector.solakon_reader,
        )
    )

    response = jsonify(payload)

    if status_code is not None:
        return response, status_code

    return response


@app.get("/api/export.csv")
def api_export_csv():
    start_date = parse_anchor(request.args.get("from"))
    end_date = parse_anchor(request.args.get("to")) + timedelta(days=1)
    tz = datetime.now().astimezone().tzinfo
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
    end = datetime.combine(end_date, datetime.min.time(), tzinfo=tz)
    rows = database.rows_between(start.timestamp(), end.timestamp())

    csv_content, filename = build_csv_export(
        rows,
        start_date,
        end_date - timedelta(days=1),
    )

    return Response(
        csv_content,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            )
        },
    )


@app.post("/api/delete-all")
def api_delete_all():
    return jsonify(
        build_delete_all_api_response(
            collector,
            database,
        )
    )


@app.get("/api/system/version")
def api_system_version():
    return build_system_version_api_response(
        get_installed_version()
    )


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

@app.get("/api/update/status")
def api_update_status():
    return read_update_status(UPDATE_STATUS_PATH)

@app.post("/api/update/download")
def api_update_download():
    installed_version = get_installed_version()

    write_update_status(
        UPDATE_STATUS_PATH,
        state="checking",
        progress=10,
        message="GitHub Release wird geprüft.",
        installed_version=installed_version,
    )

    try:
        release = check_for_update(installed_version)

        if not release.update_available:
            status = write_update_status(
                UPDATE_STATUS_PATH,
                state="idle",
                progress=0,
                message="Keine neuere Version verfügbar.",
                available_version=release.available_version,
            )
            return status, 409

        write_update_status(
            UPDATE_STATUS_PATH,
            state="downloading",
            progress=30,
            message="Release-Paket wird heruntergeladen.",
            available_version=release.available_version,
        )

        target_directory = (
            UPDATE_CACHE_DIR / release.available_version
        )

        archive_path = download_and_verify_release(
            release,
            target_directory=target_directory,
        )

        status = write_update_status(
            UPDATE_STATUS_PATH,
            state="verified",
            progress=100,
            message="Release-Paket wurde erfolgreich heruntergeladen und geprüft.",
            archive_path=str(archive_path),
            available_version=release.available_version,
        )

        return status

    except (UpdateCheckError, UpdateVerificationError) as exc:
        status = write_update_status(
            UPDATE_STATUS_PATH,
            state="failed",
            progress=0,
            message=str(exc),
        )
        return status, 502


@app.get("/update")
def update_page():
    return render_template("update.html")

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


@app.post("/api/update/install")
def api_update_install():
    status = read_update_status(
        UPDATE_STATUS_PATH
    )

    if status.get("state") != "verified":
        return {
            "status": "error",
            "message": (
                "Es liegt kein verifiziertes "
                "Update-Paket vor."
            ),
        }, 409

    version = status.get(
        "available_version"
    )
    archive_path = status.get(
        "archive_path"
    )

    if not version or not archive_path:
        return {
            "status": "error",
            "message": (
                "Updateinformationen sind "
                "unvollständig."
            ),
        }, 409

    write_update_request(
        version=version,
        archive_path=archive_path,
    )

    write_update_status(
        UPDATE_STATUS_PATH,
        state="queued",
        progress=0,
        message=(
            "Update wurde zur Installation "
            "vorgemerkt."
        ),
    )

    return {
        "status": "queued",
        "version": version,
    }, 202


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"SolarInspector {APP_VERSION}",
    )
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
