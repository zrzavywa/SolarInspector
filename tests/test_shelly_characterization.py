"""Characterization tests for the SolarInspector 4.1.3 Shelly integration."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
import solarinspector as si

pytestmark = pytest.mark.characterization


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "shelly"


def load_fixture(filename: str) -> dict[str, object]:
    """Load one synthetic Shelly response fixture."""
    return json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))


def device_config(
    device_type: str,
    *,
    direction_factor: int = 1,
) -> dict[str, object]:
    """Return the minimum device configuration used by ShellyReader."""
    return {
        "type": device_type,
        "host": "192.168.188.50",
        "username": "",
        "password": "",
        "timeout_seconds": 3,
        "direction_factor": direction_factor,
    }


def read_fixture(
    monkeypatch: pytest.MonkeyPatch,
    device_type: str,
    filename: str,
    *,
    direction_factor: int = 1,
) -> si.MeterReading:
    """Read one fixture through the public ShellyReader.read method."""
    payload = load_fixture(filename)
    reader = si.ShellyReader()
    monkeypatch.setattr(
        reader,
        "_get_json",
        lambda _device, _path: payload,
    )
    return reader.read(
        device_config(
            device_type,
            direction_factor=direction_factor,
        ),
        "house_meter",
    )


def test_pm_mini_gen3_normal_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The current PM1 parser maps all supported scalar and energy fields."""
    reading = read_fixture(
        monkeypatch,
        "shelly_pm_mini_gen3",
        "pm_mini_gen3_normal.json",
    )

    assert reading.power_w == pytest.approx(412.7)
    assert reading.voltage_v == pytest.approx(230.4)
    assert reading.current_a == pytest.approx(1.79)
    assert reading.power_factor == pytest.approx(0.99)
    assert reading.frequency_hz == pytest.approx(50.01)
    assert reading.energy_total_wh == pytest.approx(12345.6)
    assert reading.returned_energy_total_wh == pytest.approx(78.9)
    assert reading.source == "PM1.GetStatus"


def test_pm_mini_gen3_zero_power_is_a_valid_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PM1 power value of zero remains zero and is not converted to None."""
    reading = read_fixture(
        monkeypatch,
        "shelly_pm_mini_gen3",
        "pm_mini_gen3_zero_power.json",
    )

    assert reading.power_w == 0.0
    assert reading.current_a == 0.0


def test_pm_mini_gen3_negative_power_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative PM1 power values are preserved by the current parser."""
    reading = read_fixture(
        monkeypatch,
        "shelly_pm_mini_gen3",
        "pm_mini_gen3_negative_power.json",
    )

    assert reading.power_w == pytest.approx(-120.5)
    assert reading.power_factor == pytest.approx(-0.98)


def test_pm_mini_gen3_missing_power_defaults_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing PM1 apower field currently becomes zero."""
    reading = read_fixture(
        monkeypatch,
        "shelly_pm_mini_gen3",
        "pm_mini_gen3_incomplete.json",
    )

    assert reading.power_w == 0.0
    assert reading.power_available is False
    assert reading.voltage_v == pytest.approx(229.8)
    assert reading.current_a is None
    assert reading.energy_total_wh is None
    assert reading.returned_energy_total_wh is None


def test_pm_mini_gen3_invalid_power_type_raises_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid PM1 apower value is not silently converted to None."""
    reader = si.ShellyReader()
    monkeypatch.setattr(
        reader,
        "_get_json",
        lambda _device, _path: {"apower": "not-a-number"},
    )

    with pytest.raises(ValueError):
        reader.read(
            device_config("shelly_pm_mini_gen3"),
            "solakon_meter",
        )


def test_3em_gen1_prefers_total_power_and_sums_energy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Gen 1 parser prefers total_power and sums phase energy counters."""
    reading = read_fixture(
        monkeypatch,
        "shelly_3em_gen1",
        "3em_gen1_normal.json",
    )

    assert reading.power_w == pytest.approx(610.0)
    assert reading.voltage_v == pytest.approx(230.0)
    assert reading.energy_total_wh == pytest.approx(6000.0)
    assert reading.returned_energy_total_wh == pytest.approx(60.0)
    assert reading.current_a is None
    assert reading.power_factor is None
    assert reading.frequency_hz is None
    assert reading.source == "/status emeters"


def test_3em_gen1_sums_phases_when_total_power_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A negative phase participates in the fallback phase sum."""
    reading = read_fixture(
        monkeypatch,
        "shelly_3em_gen1",
        "3em_gen1_negative_phase.json",
    )

    assert reading.power_w == pytest.approx(120.0)
    assert reading.voltage_v == pytest.approx(230.0)
    assert reading.returned_energy_total_wh == pytest.approx(80.0)


def test_3em_gen1_empty_emeters_raises_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty emeters list is treated as an invalid Gen 1 response."""
    reader = si.ShellyReader()
    payload = load_fixture("3em_gen1_incomplete.json")
    monkeypatch.setattr(
        reader,
        "_get_json",
        lambda _device, _path: payload,
    )

    with pytest.raises(
        ValueError,
        match="Keine emeters-Daten",
    ):
        reader.read(
            device_config("shelly_3em_gen1"),
            "house_meter",
        )


def test_pro_3em_prefers_total_power_and_aggregates_phases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Pro parser prefers total power and aggregates phase measurements."""
    reading = read_fixture(
        monkeypatch,
        "shelly_pro_3em",
        "pro_3em_normal.json",
    )

    assert reading.power_w == pytest.approx(620.0)
    assert reading.voltage_v == pytest.approx(230.0)
    assert reading.current_a == pytest.approx(6.0)
    assert reading.power_factor == pytest.approx(0.96)
    assert reading.frequency_hz == pytest.approx(50.0)
    assert reading.energy_total_wh is None
    assert reading.returned_energy_total_wh is None
    assert reading.source == "EM.GetStatus"


def test_pro_3em_ignores_is_valid_and_invalid_phase_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The current parser does not evaluate the Pro 3EM is_valid field."""
    reading = read_fixture(
        monkeypatch,
        "shelly_pro_3em",
        "pro_3em_invalid_phase.json",
    )

    assert reading.power_w == pytest.approx(80.0)
    assert reading.voltage_v == pytest.approx(230.0)
    assert reading.current_a == pytest.approx(1.5)
    assert reading.power_factor == pytest.approx(0.90)
    assert reading.frequency_hz == pytest.approx(50.0)


def test_pro_3em_missing_measurements_become_zero_or_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A structurally valid but empty Pro response produces zero power."""
    reading = read_fixture(
        monkeypatch,
        "shelly_pro_3em",
        "pro_3em_incomplete.json",
    )

    assert reading.power_w == 0.0
    assert reading.voltage_v is None
    assert reading.current_a is None
    assert reading.power_factor is None
    assert reading.frequency_hz is None


@pytest.mark.parametrize(
    ("device_type", "filename", "expected_power"),
    [
        (
            "shelly_pm_mini_gen3",
            "pm_mini_gen3_normal.json",
            -412.7,
        ),
        (
            "shelly_3em_gen1",
            "3em_gen1_normal.json",
            -610.0,
        ),
        (
            "shelly_pro_3em",
            "pro_3em_normal.json",
            -620.0,
        ),
    ],
)
def test_direction_factor_changes_only_power(
    monkeypatch: pytest.MonkeyPatch,
    device_type: str,
    filename: str,
    expected_power: float,
) -> None:
    """direction_factor is applied after parsing and only changes power_w."""
    normal = read_fixture(
        monkeypatch,
        device_type,
        filename,
    )
    inverted = read_fixture(
        monkeypatch,
        device_type,
        filename,
        direction_factor=-1,
    )

    assert inverted.power_w == pytest.approx(expected_power)
    assert inverted.voltage_v == normal.voltage_v
    assert inverted.current_a == normal.current_a
    assert inverted.energy_total_wh == normal.energy_total_wh


def test_get_json_requires_a_host() -> None:
    """A missing Shelly host is rejected before an HTTP request is attempted."""
    reader = si.ShellyReader()

    with pytest.raises(
        ValueError,
        match="Keine IP-Adresse",
    ):
        reader._get_json(
            {
                "host": "",
                "timeout_seconds": 3,
            },
            "/status",
        )


def test_get_json_rejects_non_object_json() -> None:
    """A JSON list is rejected because device responses must be objects."""
    reader = si.ShellyReader()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = []
    reader._session.get = Mock(return_value=response)

    with pytest.raises(
        ValueError,
        match="keine gültige JSON-Antwort",
    ):
        reader._get_json(
            {
                "host": "192.168.188.50",
                "timeout_seconds": 3,
            },
            "/status",
        )


def test_get_json_propagates_invalid_json() -> None:
    """JSON decoding errors from requests currently propagate unchanged."""
    reader = si.ShellyReader()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.side_effect = ValueError("invalid JSON")
    reader._session.get = Mock(return_value=response)

    with pytest.raises(ValueError, match="invalid JSON"):
        reader._get_json(
            {
                "host": "192.168.188.50",
                "timeout_seconds": 3,
            },
            "/status",
        )


def test_get_json_propagates_http_error() -> None:
    """HTTP error responses currently propagate as requests exceptions."""
    reader = si.ShellyReader()
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("503")
    reader._session.get = Mock(return_value=response)

    with pytest.raises(requests.HTTPError, match="503"):
        reader._get_json(
            {
                "host": "192.168.188.50",
                "timeout_seconds": 3,
            },
            "/status",
        )


def test_get_json_propagates_timeout() -> None:
    """Connection timeouts currently propagate as requests exceptions."""
    reader = si.ShellyReader()
    reader._session.get = Mock(
        side_effect=requests.Timeout("timed out"),
    )

    with pytest.raises(requests.Timeout, match="timed out"):
        reader._get_json(
            {
                "host": "192.168.188.50",
                "timeout_seconds": 7,
            },
            "/status",
        )

    reader._session.get.assert_called_once_with(
        "http://192.168.188.50/status",
        timeout=7,
        auth=None,
    )
