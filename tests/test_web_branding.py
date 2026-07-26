"""Web branding and compatibility contracts for block R.7."""

from __future__ import annotations

from pathlib import Path

import zrzavy_energy_monitor as application
from zrzavy_energy_monitor_core.config.manager import ConfigManager

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_pages_use_full_canonical_product_name() -> None:
    """Expose the full name while keeping ZEM supplementary."""

    client = application.app.test_client()

    for route in ("/", "/acquisition", "/configuration", "/data", "/update"):
        response = client.get(route)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Zrzavy Energy Monitor" in html
        assert ">ZEM<" in html
        assert "· SolarInspector</title>" not in html


def test_update_script_has_no_current_legacy_product_messages() -> None:
    """Keep the old name out of current browser status messages."""

    script = (PROJECT_ROOT / "app/static/update.js").read_text(encoding="utf-8")

    assert "Zrzavy Energy Monitor" in script
    assert "SolarInspector" not in script


def test_legacy_default_project_name_is_normalized(tmp_path: Path) -> None:
    """Upgrade the former default without replacing custom installation names."""

    legacy_config = tmp_path / "legacy.json"
    legacy_config.write_text(
        '{"general": {"project_name": "SolarInspector"}}',
        encoding="utf-8",
    )
    custom_config = tmp_path / "custom.json"
    custom_config.write_text(
        '{"general": {"project_name": "Hauskraftwerk"}}',
        encoding="utf-8",
    )

    assert (
        ConfigManager(legacy_config).get()["general"]["project_name"]
        == "Zrzavy Energy Monitor"
    )
    assert (
        ConfigManager(custom_config).get()["general"]["project_name"] == "Hauskraftwerk"
    )
