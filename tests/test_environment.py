"""Tests for compatible Zrzavy Energy Monitor environment resolution."""

from __future__ import annotations

import logging

import pytest
from zrzavy_energy_monitor_core.environment import (
    CONFIG_PATH_VARIABLE,
    DATABASE_PATH_VARIABLE,
    ENVIRONMENT_VARIABLE_ALIASES,
    LEGACY_CONFIG_PATH_VARIABLE,
    LEGACY_DATABASE_PATH_VARIABLE,
    LEGACY_SECRET_VARIABLE,
    SECRET_VARIABLE,
    UPDATE_CACHE_DIR_VARIABLE,
    UPDATE_REQUEST_PATH_VARIABLE,
    UPDATE_STATUS_PATH_VARIABLE,
    resolve_environment_variable,
    resolve_known_environment_variable,
)


def test_all_canonical_variables_have_documented_legacy_aliases() -> None:
    """Cover every canonical variable required by the migration contract."""

    assert set(ENVIRONMENT_VARIABLE_ALIASES) == {
        SECRET_VARIABLE,
        CONFIG_PATH_VARIABLE,
        DATABASE_PATH_VARIABLE,
        UPDATE_STATUS_PATH_VARIABLE,
        UPDATE_REQUEST_PATH_VARIABLE,
        UPDATE_CACHE_DIR_VARIABLE,
    }
    assert set(ENVIRONMENT_VARIABLE_ALIASES.values()) == {
        "SOLARINSPECTOR_SECRET",
        "SOLARINSPECTOR_CONFIG_PATH",
        "SOLARINSPECTOR_DATABASE_PATH",
        "SOLARINSPECTOR_UPDATE_STATUS_PATH",
        "SOLARINSPECTOR_UPDATE_REQUEST_PATH",
        "SOLARINSPECTOR_UPDATE_CACHE_DIR",
    }


def test_canonical_variable_is_used_without_warning(caplog) -> None:
    """Prefer a canonical value when no legacy alias is present."""

    result = resolve_environment_variable(
        CONFIG_PATH_VARIABLE,
        LEGACY_CONFIG_PATH_VARIABLE,
        environ={CONFIG_PATH_VARIABLE: "/new/config.json"},
    )

    assert result == "/new/config.json"
    assert not caplog.records


def test_legacy_variable_is_used_with_one_warning(caplog) -> None:
    """Support one legacy fallback with one actionable warning."""

    with caplog.at_level(logging.WARNING):
        result = resolve_environment_variable(
            CONFIG_PATH_VARIABLE,
            LEGACY_CONFIG_PATH_VARIABLE,
            environ={LEGACY_CONFIG_PATH_VARIABLE: "/legacy/config.json"},
        )

    assert result == "/legacy/config.json"
    assert len(caplog.records) == 1
    assert LEGACY_CONFIG_PATH_VARIABLE in caplog.text
    assert CONFIG_PATH_VARIABLE in caplog.text


def test_identical_variables_use_canonical_value_without_warning(caplog) -> None:
    """Avoid noise when both migration variables already agree."""

    shared_path = "/shared/database.db"
    result = resolve_environment_variable(
        DATABASE_PATH_VARIABLE,
        LEGACY_DATABASE_PATH_VARIABLE,
        environ={
            DATABASE_PATH_VARIABLE: shared_path,
            LEGACY_DATABASE_PATH_VARIABLE: shared_path,
        },
    )

    assert result == shared_path
    assert not caplog.records


def test_conflicting_variables_prefer_canonical_with_one_warning(caplog) -> None:
    """Resolve a conflict deterministically without logging either value."""

    canonical_value = "/new/private/database.db"
    legacy_value = "/old/private/database.db"

    with caplog.at_level(logging.WARNING):
        result = resolve_environment_variable(
            DATABASE_PATH_VARIABLE,
            LEGACY_DATABASE_PATH_VARIABLE,
            environ={
                DATABASE_PATH_VARIABLE: canonical_value,
                LEGACY_DATABASE_PATH_VARIABLE: legacy_value,
            },
        )

    assert result == canonical_value
    assert len(caplog.records) == 1
    assert canonical_value not in caplog.text
    assert legacy_value not in caplog.text


def test_missing_variables_return_documented_default(caplog) -> None:
    """Return the caller's default without logging a migration warning."""

    result = resolve_environment_variable(
        CONFIG_PATH_VARIABLE,
        LEGACY_CONFIG_PATH_VARIABLE,
        "/default/config.json",
        environ={},
    )

    assert result == "/default/config.json"
    assert not caplog.records


@pytest.mark.parametrize(
    "environ, expected",
    [
        ({SECRET_VARIABLE: "new-secret"}, "new-secret"),
        ({LEGACY_SECRET_VARIABLE: "legacy-secret"}, "legacy-secret"),
        (
            {
                SECRET_VARIABLE: "new-secret",
                LEGACY_SECRET_VARIABLE: "legacy-secret",
            },
            "new-secret",
        ),
    ],
)
def test_secret_values_are_never_logged(caplog, environ, expected) -> None:
    """Keep canonical and legacy secret values out of all warnings."""

    with caplog.at_level(logging.WARNING):
        result = resolve_known_environment_variable(
            SECRET_VARIABLE,
            environ=environ,
        )

    assert result == expected
    assert "new-secret" not in caplog.text
    assert "legacy-secret" not in caplog.text


def test_unknown_canonical_variable_is_rejected() -> None:
    """Prevent silent resolution of undocumented migration variables."""

    with pytest.raises(ValueError, match="Unsupported environment variable"):
        resolve_known_environment_variable(
            "ZRZAVY_ENERGY_MONITOR_UNKNOWN",
            environ={},
        )
