"""Render the simple SolarInspector HTML pages.

Flask route registration and application-global dependency lookup remain in
the compatible entry module. This module contains only the page rendering
implementations.
"""

from __future__ import annotations

from typing import Any, Callable

TemplateRenderer = Callable[..., Any]


def render_dashboard_page(
    renderer: TemplateRenderer,
) -> Any:
    """Render the existing dashboard page."""
    return renderer(
        "dashboard.html",
        active_page="dashboard",
    )


def render_acquisition_page(
    renderer: TemplateRenderer,
    status: dict[str, Any],
    config: dict[str, Any],
) -> Any:
    """Render the existing acquisition page."""
    return renderer(
        "acquisition.html",
        active_page="acquisition",
        status=status,
        config=config,
    )


def render_data_page(
    renderer: TemplateRenderer,
    stats: dict[str, Any],
    db_path: str,
) -> Any:
    """Render the existing data page."""
    return renderer(
        "data.html",
        active_page="data",
        stats=stats,
        db_path=db_path,
    )
