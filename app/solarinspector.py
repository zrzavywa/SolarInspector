#!/usr/bin/env python3
"""SolarInspector web application.

Lokale Web-Anwendung zur Erfassung und Auswertung einer Solakon-Anlage.
Unterstützt Solakon ONE über read-only Modbus TCP sowie Shelly-Messgeräte.
"""

from __future__ import annotations

import argparse
import atexit
import os
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

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
from solarinspector_core.runtime import (
    cleanup_runtime_pid_file,
    parse_runtime_args,
    run_application,
)
from solarinspector_core.services.collector import Collector as CoreCollector
from solarinspector_core.services.dashboard import build_dashboard as _build_dashboard
from solarinspector_core.services.demo import generate_demo_samples
from solarinspector_core.services.periods import (
    bucket_index as _bucket_index,
)
from solarinspector_core.services.periods import (
    parse_anchor as _parse_anchor,
)
from solarinspector_core.services.periods import (
    period_bounds as _period_bounds,
)
from solarinspector_core.services.update import (
    build_update_check_response,
    perform_update_download,
    queue_update_installation,
    read_update_status_response,
    write_update_request_file,
)
from solarinspector_core.services.version import read_installed_version
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
    write_update_request_file(
        UPDATE_REQUEST_PATH,
        version,
        archive_path,
    )


def get_installed_version() -> str:
    return read_installed_version(
        Path(__file__).resolve().parent.parent
        / "VERSION"
    )


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
    payload, status_code = (
        build_update_check_response(
            get_installed_version(),
            check_for_update,
        )
    )

    if status_code is not None:
        return payload, status_code

    return payload

@app.get("/api/update/status")
def api_update_status():
    return read_update_status_response(
        UPDATE_STATUS_PATH,
        read_update_status,
    )

@app.post("/api/update/download")
def api_update_download():
    payload, status_code = (
        perform_update_download(
            installed_version=(
                get_installed_version()
            ),
            status_path=UPDATE_STATUS_PATH,
            cache_directory=UPDATE_CACHE_DIR,
            update_checker=check_for_update,
            release_downloader=(
                download_and_verify_release
            ),
            status_writer=write_update_status,
        )
    )

    if status_code is not None:
        return payload, status_code

    return payload


@app.get("/update")
def update_page():
    return render_template("update.html")

def generate_demo_data(
    days: int = 400,
    interval_minutes: int = 15,
) -> None:
    generate_demo_samples(
        database,
        days=days,
        interval_minutes=interval_minutes,
        end_time=(
            datetime.now().astimezone()
        ),
        log_message=log,
    )


@app.post("/api/update/install")
def api_update_install():
    return queue_update_installation(
        status_path=UPDATE_STATUS_PATH,
        status_reader=read_update_status,
        request_writer=write_update_request,
        status_writer=write_update_status,
    )


def parse_args() -> argparse.Namespace:
    return parse_runtime_args(
        APP_VERSION
    )


def main() -> None:
    run_application(
        parse_args(),
        application=app,
        config_manager=config_manager,
        collector=collector,
        generate_demo_data=generate_demo_data,
        log_message=log,
        pid_path=PID_PATH,
        process_id=os.getpid(),
        version=APP_VERSION,
        timer_factory=threading.Timer,
        browser_open=webbrowser.open,
        serve_application=serve,
    )





def cleanup_pid_file() -> None:
    cleanup_runtime_pid_file(
        PID_PATH,
        os.getpid(),
    )





atexit.register(collector.stop)
atexit.register(cleanup_pid_file)

if __name__ == "__main__":
    main()
