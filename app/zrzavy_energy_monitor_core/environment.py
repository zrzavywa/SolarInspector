"""Resolve canonical environment variables with legacy compatibility.

The resolver reads environment values without changing process state. Legacy
aliases remain available for the 4.5 stabilization period and emit one
actionable warning per resolution. Values are deliberately excluded from
messages so the same implementation is safe for secrets.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping

LOGGER = logging.getLogger(__name__)

SECRET_VARIABLE = "ZRZAVY_ENERGY_MONITOR_SECRET"
CONFIG_PATH_VARIABLE = "ZRZAVY_ENERGY_MONITOR_CONFIG_PATH"
DATABASE_PATH_VARIABLE = "ZRZAVY_ENERGY_MONITOR_DATABASE_PATH"
UPDATE_STATUS_PATH_VARIABLE = "ZRZAVY_ENERGY_MONITOR_UPDATE_STATUS_PATH"
UPDATE_REQUEST_PATH_VARIABLE = "ZRZAVY_ENERGY_MONITOR_UPDATE_REQUEST_PATH"
UPDATE_CACHE_DIR_VARIABLE = "ZRZAVY_ENERGY_MONITOR_UPDATE_CACHE_DIR"

LEGACY_SECRET_VARIABLE = "SOLARINSPECTOR_SECRET"
LEGACY_CONFIG_PATH_VARIABLE = "SOLARINSPECTOR_CONFIG_PATH"
LEGACY_DATABASE_PATH_VARIABLE = "SOLARINSPECTOR_DATABASE_PATH"
LEGACY_UPDATE_STATUS_PATH_VARIABLE = "SOLARINSPECTOR_UPDATE_STATUS_PATH"
LEGACY_UPDATE_REQUEST_PATH_VARIABLE = "SOLARINSPECTOR_UPDATE_REQUEST_PATH"
LEGACY_UPDATE_CACHE_DIR_VARIABLE = "SOLARINSPECTOR_UPDATE_CACHE_DIR"

ENVIRONMENT_VARIABLE_ALIASES = {
    SECRET_VARIABLE: LEGACY_SECRET_VARIABLE,
    CONFIG_PATH_VARIABLE: LEGACY_CONFIG_PATH_VARIABLE,
    DATABASE_PATH_VARIABLE: LEGACY_DATABASE_PATH_VARIABLE,
    UPDATE_STATUS_PATH_VARIABLE: LEGACY_UPDATE_STATUS_PATH_VARIABLE,
    UPDATE_REQUEST_PATH_VARIABLE: LEGACY_UPDATE_REQUEST_PATH_VARIABLE,
    UPDATE_CACHE_DIR_VARIABLE: LEGACY_UPDATE_CACHE_DIR_VARIABLE,
}


def resolve_environment_variable(
    canonical_name: str,
    legacy_name: str,
    default: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve a canonical variable and its temporary legacy alias.

    Args:
        canonical_name: Preferred ``ZRZAVY_ENERGY_MONITOR_*`` variable.
        legacy_name: Deprecated ``SOLARINSPECTOR_*`` fallback variable.
        default: Value returned when neither variable is set.
        environ: Optional environment mapping, primarily for isolated tests.

    Returns:
        The canonical value, legacy fallback, or supplied default.

    Notes:
        When both variables differ, the canonical value wins and one warning
        is logged. Values are never included in log output.
    """

    return resolve_environment_variable_aliases(
        canonical_name,
        (legacy_name,),
        default,
        environ=environ,
    )


def resolve_environment_variable_aliases(
    canonical_name: str,
    legacy_names: tuple[str, ...],
    default: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve a canonical variable with ordered compatibility aliases.

    Args:
        canonical_name: Preferred ``ZRZAVY_ENERGY_MONITOR_*`` variable.
        legacy_names: Deprecated aliases in descending precedence order.
        default: Value returned when no documented variable is set.
        environ: Optional environment mapping.

    Returns:
        The canonical value, highest-priority legacy value, or default.

    Raises:
        ValueError: If no legacy alias is provided.

    Notes:
        At most one warning is emitted. Messages contain variable names but
        never their potentially sensitive values.
    """

    if not legacy_names:
        raise ValueError("At least one legacy environment variable is required.")

    source = os.environ if environ is None else environ
    canonical_is_set = canonical_name in source
    configured_legacy_names = tuple(
        legacy_name for legacy_name in legacy_names if legacy_name in source
    )

    if canonical_is_set:
        if any(
            source[canonical_name] != source[legacy_name]
            for legacy_name in configured_legacy_names
        ):
            LOGGER.warning(
                "Conflicting canonical and deprecated environment variables "
                "are set; %s takes precedence. Remove deprecated aliases: %s.",
                canonical_name,
                ", ".join(configured_legacy_names),
            )
        return source[canonical_name]

    if configured_legacy_names:
        selected_legacy_name = configured_legacy_names[0]
        LOGGER.warning(
            "Environment variable %s is deprecated; use %s instead. "
            "Legacy support remains available during the 4.5 stabilization.",
            selected_legacy_name,
            canonical_name,
        )
        return source[selected_legacy_name]

    return default


def resolve_known_environment_variable(
    canonical_name: str,
    default: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve one of the documented canonical environment variables.

    Args:
        canonical_name: A key from :data:`ENVIRONMENT_VARIABLE_ALIASES`.
        default: Value returned when neither canonical nor legacy key is set.
        environ: Optional environment mapping.

    Returns:
        The resolved value or supplied default.

    Raises:
        ValueError: If ``canonical_name`` is not a documented variable.
    """

    try:
        legacy_name = ENVIRONMENT_VARIABLE_ALIASES[canonical_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported environment variable: {canonical_name}") from exc

    return resolve_environment_variable(
        canonical_name,
        legacy_name,
        default,
        environ=environ,
    )
