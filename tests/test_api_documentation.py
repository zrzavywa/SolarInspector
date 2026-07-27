"""Keep the API reference synchronized with registered Flask routes."""

from __future__ import annotations

import re
from pathlib import Path

import zrzavy_energy_monitor as application

API_REFERENCE = Path(__file__).parents[1] / "docs" / "api.md"
ENDPOINT_HEADING = re.compile(
    r"^### `(?P<method>[A-Z]+) (?P<path>/api[^`]*)`$",
    re.MULTILINE,
)


def _registered_api_contracts() -> set[tuple[str, str]]:
    """Return explicit API methods while excluding Flask-derived methods."""

    contracts: set[tuple[str, str]] = set()
    for rule in application.app.url_map.iter_rules():
        path = str(rule)
        if not path.startswith("/api"):
            continue
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            contracts.add((method, path))
    return contracts


def _documented_api_contracts() -> list[tuple[str, str]]:
    """Return every METHOD-PATH contract heading from the API reference."""

    content = API_REFERENCE.read_text(encoding="utf-8")
    return [
        (match.group("method"), match.group("path"))
        for match in ENDPOINT_HEADING.finditer(content)
    ]


def test_every_registered_api_route_has_exactly_one_reference_section() -> None:
    """Require one discoverable section for every explicit API contract."""

    registered = _registered_api_contracts()
    documented = _documented_api_contracts()

    assert len(documented) == len(set(documented)), (
        "docs/api.md contains duplicate METHOD-PATH sections"
    )
    assert set(documented) == registered, (
        "docs/api.md must match the explicit Flask API contracts; "
        f"missing={sorted(registered - set(documented))}, "
        f"unexpected={sorted(set(documented) - registered)}"
    )


def test_api_inventory_excludes_derived_and_non_api_routes() -> None:
    """Document the counting policy for Flask-derived and page routes."""

    contracts = _registered_api_contracts()

    assert len(contracts) == 20
    assert all(method not in {"HEAD", "OPTIONS"} for method, _path in contracts)
    assert all(path.startswith("/api") for _method, path in contracts)
    assert ("GET", "/") not in contracts
    assert ("GET", "/static/<path:filename>") not in contracts
