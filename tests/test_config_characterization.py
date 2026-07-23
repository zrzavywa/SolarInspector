"""Characterization tests for the SolarInspector 4.1.3 configuration logic."""

import json
from pathlib import Path

import pytest
import solarinspector as si

pytestmark = pytest.mark.characterization


def test_missing_configuration_file_creates_defaults(tmp_path: Path) -> None:
    """A missing configuration file is created with the current defaults."""
    config_path = tmp_path / "config.json"

    manager = si.ConfigManager(config_path)

    assert config_path.exists()
    assert manager.get() == si.DEFAULT_CONFIG
    assert json.loads(config_path.read_text(encoding="utf-8")) == si.DEFAULT_CONFIG


def test_partial_configuration_is_completed_with_defaults(tmp_path: Path) -> None:
    """Older partial configurations receive all currently known defaults."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "general": {
                    "site_name": "Legacy installation",
                },
                "house_meter": {
                    "enabled": True,
                    "host": "192.0.2.10",
                },
            }
        ),
        encoding="utf-8",
    )

    manager = si.ConfigManager(config_path)
    config = manager.get()

    assert config["general"]["site_name"] == "Legacy installation"
    assert config["general"]["port"] == 8787
    assert config["solakon_one"] == si.DEFAULT_CONFIG["solakon_one"]
    assert config["house_meter"]["enabled"] is True
    assert config["house_meter"]["host"] == "192.0.2.10"
    assert config["house_meter"]["type"] == "shelly_3em_gen1"
    assert config["solakon_meter"] == si.DEFAULT_CONFIG["solakon_meter"]


def test_unknown_fields_are_preserved_when_loading(tmp_path: Path) -> None:
    """Unknown top-level and nested fields survive configuration loading."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "future_section": {
                    "enabled": True,
                },
                "general": {
                    "future_option": "preserve-me",
                },
            }
        ),
        encoding="utf-8",
    )

    config = si.ConfigManager(config_path).get()

    assert config["future_section"] == {"enabled": True}
    assert config["general"]["future_option"] == "preserve-me"


def test_invalid_json_uses_defaults_without_replacing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid JSON is ignored while the original file remains unchanged."""
    config_path = tmp_path / "config.json"
    invalid_content = '{"general": '
    config_path.write_text(invalid_content, encoding="utf-8")
    log_messages: list[str] = []

    monkeypatch.setattr(si, "log", log_messages.append)

    manager = si.ConfigManager(config_path)

    assert manager.get() == si.DEFAULT_CONFIG
    assert config_path.read_text(encoding="utf-8") == invalid_content
    assert len(log_messages) == 1
    assert "Standardwerte werden verwendet" in log_messages[0]


def test_get_returns_an_independent_copy(tmp_path: Path) -> None:
    """Mutating a returned configuration does not change manager state."""
    manager = si.ConfigManager(tmp_path / "config.json")

    returned_config = manager.get()
    returned_config["general"]["site_name"] = "Changed externally"

    assert manager.get()["general"]["site_name"] == "Solakon Anlage"


def test_save_preserves_unknown_fields_and_removes_temporary_file(
    tmp_path: Path,
) -> None:
    """Saving preserves unknown values and leaves no temporary file behind."""
    config_path = tmp_path / "config.json"
    manager = si.ConfigManager(config_path)
    config = manager.get()
    config["general"]["site_name"] = "Saved installation"
    config["general"]["future_option"] = 42
    config["future_section"] = {"mode": "legacy"}

    manager.save(config)

    persisted = json.loads(config_path.read_text(encoding="utf-8"))

    assert persisted["general"]["site_name"] == "Saved installation"
    assert persisted["general"]["future_option"] == 42
    assert persisted["future_section"] == {"mode": "legacy"}
    assert not config_path.with_suffix(".tmp").exists()
    assert manager.get() == persisted


def test_hosts_and_direction_factors_are_normalized(tmp_path: Path) -> None:
    """Hosts and direction factors follow the current validation rules."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "solakon_one": {
                    "host": " https://192.0.2.20/ ",
                },
                "house_meter": {
                    "host": "http://192.0.2.21/",
                    "direction_factor": -9,
                },
                "solakon_meter": {
                    "host": " 192.0.2.22/ ",
                    "direction_factor": 0,
                },
            }
        ),
        encoding="utf-8",
    )

    config = si.ConfigManager(config_path).get()

    assert config["solakon_one"]["host"] == "192.0.2.20"
    assert config["house_meter"]["host"] == "192.0.2.21"
    assert config["solakon_meter"]["host"] == "192.0.2.22"
    assert config["house_meter"]["direction_factor"] == -1
    assert config["solakon_meter"]["direction_factor"] == 1


def test_non_empty_boolean_strings_are_treated_as_true(tmp_path: Path) -> None:
    """Document the current Python truth-value conversion of strings."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "general": {
                    "auto_start_collection": "false",
                    "open_browser": "false",
                },
                "solakon_one": {
                    "enabled": "false",
                    "simulation": "false",
                },
            }
        ),
        encoding="utf-8",
    )

    config = si.ConfigManager(config_path).get()

    assert config["general"]["auto_start_collection"] is True
    assert config["general"]["open_browser"] is True
    assert config["solakon_one"]["enabled"] is True
    assert config["solakon_one"]["simulation"] is True
