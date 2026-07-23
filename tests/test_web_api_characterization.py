# Characterization tests for SolarInspector web pages and HTTP APIs.

import csv
import io
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

import pytest
import solarinspector as si

EXPORT_FIELDS = [
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


class ConfigStub:
    def __init__(self) -> None:
        self.config = si.deep_merge(si.DEFAULT_CONFIG, {})
        self.saved: list[dict[str, Any]] = []
        self.error: Exception | None = None

    def get(self) -> dict[str, Any]:
        return deepcopy(self.config)

    def save(self, config: dict[str, Any]) -> None:
        if self.error:
            raise self.error
        self.config = deepcopy(config)
        self.saved.append(deepcopy(config))


class DatabaseStub:
    def __init__(self) -> None:
        self.latest_value: dict[str, Any] | None = None
        self.rows: list[dict[str, Any]] = []
        self.bounds: tuple[float, float] | None = None
        self.actions: list[str] | None = None

    def latest(self) -> dict[str, Any] | None:
        return deepcopy(self.latest_value)

    def rows_between(self, start: float, end: float) -> list[dict[str, Any]]:
        self.bounds = (start, end)
        return deepcopy(self.rows)

    def stats(self) -> dict[str, Any]:
        return {
            "count": len(self.rows),
            "first_epoch": None,
            "last_epoch": None,
            "db_size_bytes": 16384,
        }

    def delete_all(self) -> None:
        if self.actions is not None:
            self.actions.append("delete")


class ReaderStub:
    def __init__(self) -> None:
        self.reading: si.MeterReading | None = None
        self.error: Exception | None = None
        self.calls: list[tuple[dict[str, Any], str]] = []

    def read(self, config: dict[str, Any], role: str) -> si.MeterReading:
        self.calls.append((deepcopy(config), role))
        if self.error:
            raise self.error
        assert self.reading is not None
        return self.reading


class SolakonStub:
    def __init__(self) -> None:
        self.reading: si.SolakonOneReading | None = None
        self.error: Exception | None = None
        self.calls: list[dict[str, Any]] = []

    def test(self, config: dict[str, Any]) -> si.SolakonOneReading:
        self.calls.append(deepcopy(config))
        if self.error:
            raise self.error
        assert self.reading is not None
        return self.reading


class CollectorStub:
    def __init__(self) -> None:
        self.running = False
        self.start_result = True
        self.stop_result = True
        self.last_error = ""
        self.cycles = 0
        self.last_sample: dict[str, Any] | None = None
        self.collect_result: dict[str, Any] = {"id": 1}
        self.collect_error: Exception | None = None
        self.actions: list[str] | None = None
        self.reader = ReaderStub()
        self.solakon_reader = SolakonStub()

    def is_running(self) -> bool:
        return self.running

    def start(self) -> bool:
        if self.start_result:
            self.running = True
        return self.start_result

    def stop(self) -> bool:
        if self.actions is not None:
            self.actions.append("stop")
        if self.stop_result:
            self.running = False
        return self.stop_result

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "started_at": None,
            "cycles": self.cycles,
            "last_error": self.last_error,
            "last_sample": deepcopy(self.last_sample),
        }

    def collect_once(self) -> dict[str, Any]:
        if self.collect_error:
            raise self.collect_error
        return deepcopy(self.collect_result)

    def reset_state(self) -> None:
        if self.actions is not None:
            self.actions.append("reset")


@pytest.fixture
def web_context(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ConfigStub, DatabaseStub, CollectorStub]:
    config = ConfigStub()
    database = DatabaseStub()
    collector = CollectorStub()
    monkeypatch.setattr(si, "config_manager", config)
    monkeypatch.setattr(si, "database", database)
    monkeypatch.setattr(si, "collector", collector)
    si.app.config.update(TESTING=True)
    return config, database, collector


@pytest.mark.parametrize(
    "route",
    ["/", "/acquisition", "/configuration", "/data"],
)
def test_page_routes_render_html(web_context: Any, route: str) -> None:
    response = si.app.test_client().get(route)
    assert response.status_code == 200
    assert response.content_type.startswith("text/html")


def test_configuration_post_maps_form_and_redirects(web_context: Any) -> None:
    config, _database, _collector = web_context
    response = si.app.test_client().post(
        "/configuration",
        data={
            "project_name": "Test Project",
            "site_name": "Test Site",
            "poll_interval_seconds": "17",
            "auto_start_collection": "on",
            "bind_host": "0.0.0.0",
            "port": "9000",
            "open_browser": "on",
            "solar_power_source": "solakon_ac",
            "grid_power_source": "solakon_one",
            "solakon_one_enabled": "on",
            "solakon_one_host": "192.0.2.10",
            "solakon_one_port": "1502",
            "solakon_one_device_id": "7",
            "solakon_one_timeout_seconds": "9",
            "solakon_one_simulation": "on",
            "house_meter_enabled": "on",
            "house_meter_type": "shelly_3em",
            "house_meter_direction_factor": "-1",
            "solakon_meter_enabled": "on",
            "solakon_meter_type": "shelly_pro_3em",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/configuration")
    saved = config.saved[0]
    assert saved["general"]["project_name"] == "Test Project"
    assert saved["general"]["auto_start_collection"] is True
    assert saved["solakon_one"]["simulation"] is True
    assert saved["solakon_one"]["port"] == "1502"
    assert saved["house_meter"]["direction_factor"] == "-1"
    assert saved["solakon_meter"]["type"] == "shelly_pro_3em"


def test_configuration_save_error_is_flashed(web_context: Any) -> None:
    config, _database, _collector = web_context
    config.error = RuntimeError("disk full")
    response = si.app.test_client().post(
        "/configuration",
        data={},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Konfiguration konnte nicht gespeichert werden: disk full" in (
        response.get_data(as_text=True)
    )


@pytest.mark.parametrize(
    (
        "start_result",
        "running",
        "last_error",
        "expected_status",
        "expected_ok",
    ),
    [
        (True, False, "", 200, True),
        (False, True, "", 200, True),
        (False, False, "Keine Messstelle aktiviert.", 400, False),
    ],
)
def test_start_api_contract(
    web_context: Any,
    start_result: bool,
    running: bool,
    last_error: str,
    expected_status: int,
    expected_ok: bool,
) -> None:
    _config, _database, collector = web_context
    collector.start_result = start_result
    collector.running = running
    collector.last_error = last_error
    response = si.app.test_client().post("/api/start")
    payload = response.get_json()
    assert response.status_code == expected_status
    assert payload["ok"] is expected_ok
    assert payload["started"] is start_result
    assert payload["status"]["running"] is (running or start_result)
    if not expected_ok:
        assert payload["error"] == last_error


def test_stop_api_returns_result_and_status(web_context: Any) -> None:
    _config, _database, collector = web_context
    collector.running = True
    response = si.app.test_client().post("/api/stop")
    assert response.status_code == 200
    assert response.get_json()["stopped"] is True
    assert response.get_json()["status"]["running"] is False


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [(None, 200), (RuntimeError("collection failed"), 500)],
)
def test_collect_once_api_contract(
    web_context: Any,
    error: Exception | None,
    expected_status: int,
) -> None:
    _config, _database, collector = web_context
    collector.collect_result = {"id": 9, "solar_power_w": 410.0}
    collector.collect_error = error
    response = si.app.test_client().post("/api/collect-once")
    assert response.status_code == expected_status
    payload = response.get_json()
    if error is None:
        assert payload == {
            "ok": True,
            "sample": {"id": 9, "solar_power_w": 410.0},
        }
    else:
        assert payload == {"ok": False, "error": "collection failed"}


def test_status_api_returns_collector_status(web_context: Any) -> None:
    _config, _database, collector = web_context
    collector.running = True
    collector.cycles = 4
    collector.last_error = "warning"
    collector.last_sample = {"id": 8}
    response = si.app.test_client().get("/api/status")
    assert response.status_code == 200
    assert response.get_json() == collector.status()


@pytest.mark.parametrize(
    ("timestamp", "now", "expected_age"),
    [(970.0, 1000.0, 30), (1030.0, 1000.0, 0)],
)
def test_live_api_adds_non_negative_age(
    web_context: Any,
    monkeypatch: pytest.MonkeyPatch,
    timestamp: float,
    now: float,
    expected_age: int,
) -> None:
    _config, database, collector = web_context
    database.latest_value = {"id": 5, "ts_epoch": timestamp}
    collector.cycles = 2
    monkeypatch.setattr(si.time, "time", lambda: now)
    response = si.app.test_client().get("/api/live")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["latest"]["age_seconds"] == expected_age
    assert payload["collector"]["cycles"] == 2


def test_live_api_returns_null_without_samples(web_context: Any) -> None:
    response = si.app.test_client().get("/api/live")
    assert response.status_code == 200
    assert response.get_json()["latest"] is None


def test_dashboard_api_unknown_period_falls_back_to_day(
    web_context: Any,
) -> None:
    _config, database, _collector = web_context
    response = si.app.test_client().get(
        "/api/dashboard?period=quarter&anchor=2026-07-23"
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["period"] == "day"
    assert payload["anchor"] == "2026-07-23"
    assert len(payload["labels"]) == 24
    assert payload["kpi"]["sample_count"] == 0
    assert database.bounds is not None


def test_device_api_rejects_unknown_role(web_context: Any) -> None:
    response = si.app.test_client().post("/api/test-device/unknown")
    assert response.status_code == 404
    assert response.get_json() == {
        "ok": False,
        "error": "Unbekannte Messstelle.",
    }


def test_device_api_rejects_disabled_device(web_context: Any) -> None:
    response = si.app.test_client().post(
        "/api/test-device/house_meter",
        json={"enabled": False},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Messstelle ist deaktiviert."


def test_device_api_returns_reading(web_context: Any) -> None:
    _config, _database, collector = web_context
    collector.reader.reading = si.MeterReading(
        power_w=123.0,
        voltage_v=230.0,
        current_a=0.6,
        power_factor=0.98,
        frequency_hz=50.0,
        source="Fixture",
    )
    response = si.app.test_client().post(
        "/api/test-device/house_meter",
        json={
            "enabled": True,
            "type": "simulation",
            "direction_factor": -1,
        },
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["reading"]["power_w"] == 123.0
    assert payload["reading"]["source"] == "Fixture"
    assert collector.reader.calls[0][1] == "house_meter"
    assert collector.reader.calls[0][0]["direction_factor"] == -1


def test_device_api_converts_reader_error_to_502(web_context: Any) -> None:
    _config, _database, collector = web_context
    collector.reader.error = RuntimeError("meter offline")
    response = si.app.test_client().post(
        "/api/test-device/solakon_meter",
        json={"enabled": True, "type": "simulation"},
    )
    assert response.status_code == 502
    assert response.get_json()["error"] == "meter offline"


def test_solakon_api_rejects_disabled_device(web_context: Any) -> None:
    response = si.app.test_client().post(
        "/api/test-solakon-one",
        json={"enabled": False},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Solakon ONE ist deaktiviert."


def test_solakon_api_returns_reading(web_context: Any) -> None:
    _config, _database, collector = web_context
    collector.solakon_reader.reading = si.SolakonOneReading(
        status="Betrieb",
        total_pv_power_w=500.0,
        active_power_w=380.0,
        battery_power_w=50.0,
        battery_soc_pct=65.0,
        load_power_w=450.0,
        meter_power_w=-70.0,
        power_factor=0.99,
        grid_frequency_hz=50.0,
    )
    response = si.app.test_client().post(
        "/api/test-solakon-one",
        json={
            "enabled": True,
            "simulation": True,
            "port": 502,
            "device_id": 1,
            "timeout_seconds": 2,
        },
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["reading"]["status"] == "Betrieb"
    assert payload["reading"]["total_pv_power_w"] == 500.0
    assert collector.solakon_reader.calls[0]["simulation"] is True


def test_solakon_api_converts_reader_error_to_502(web_context: Any) -> None:
    _config, _database, collector = web_context
    collector.solakon_reader.error = RuntimeError("modbus timeout")
    response = si.app.test_client().post(
        "/api/test-solakon-one",
        json={"enabled": True, "simulation": False},
    )
    assert response.status_code == 502
    assert response.get_json()["error"] == "modbus timeout"


def test_csv_export_contract_and_date_range(web_context: Any) -> None:
    _config, database, _collector = web_context
    database.rows = [
        {
            "ts_local": "2026-07-23T12:00:00+02:00",
            "grid_power_w": 120.0,
            "solar_power_w": 400.0,
            "solar_source": "Shelly AC",
            "grid_source": "Hausanschluss",
            "error_text": "",
            "ignored_column": "not exported",
        }
    ]
    response = si.app.test_client().get("/api/export.csv?from=2026-07-23&to=2026-07-24")
    assert response.status_code == 200
    assert response.content_type.startswith("text/csv")
    assert response.headers["Content-Disposition"] == (
        'attachment; filename="solarinspector_2026-07-23_2026-07-24.csv"'
    )

    reader = csv.DictReader(
        io.StringIO(response.get_data(as_text=True)),
        delimiter=";",
    )
    rows = list(reader)
    assert reader.fieldnames == EXPORT_FIELDS
    assert rows[0]["ts_local"] == "2026-07-23T12:00:00+02:00"
    assert rows[0]["grid_power_w"] == "120.0"
    assert rows[0]["solar_source"] == "Shelly AC"
    assert "ignored_column" not in rows[0]

    timezone = datetime.now().astimezone().tzinfo
    expected_start = datetime(2026, 7, 23, tzinfo=timezone).timestamp()
    expected_end = (
        datetime(2026, 7, 24, tzinfo=timezone) + timedelta(days=1)
    ).timestamp()
    assert database.bounds == (expected_start, expected_end)


def test_delete_all_calls_stop_delete_reset_in_order(
    web_context: Any,
) -> None:
    _config, database, collector = web_context
    actions: list[str] = []
    database.actions = actions
    collector.actions = actions
    collector.running = True
    response = si.app.test_client().post("/api/delete-all")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
    assert actions == ["stop", "delete", "reset"]


@pytest.mark.parametrize(
    "route",
    ["/api/start", "/api/stop", "/api/collect-once", "/api/delete-all"],
)
def test_post_only_endpoints_reject_get(
    web_context: Any,
    route: str,
) -> None:
    response = si.app.test_client().get(route)
    assert response.status_code == 405
