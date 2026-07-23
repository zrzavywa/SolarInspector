"""Command-line parsing and process runtime orchestration."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable, Protocol


class RuntimeConfigManager(Protocol):
    """Configuration access required during startup."""

    def get(self) -> dict[str, Any]:
        """Return the current application configuration."""


class RuntimeCollector(Protocol):
    """Collector operations required during startup."""

    def start(self) -> bool:
        """Start measurement collection."""


TimerFactory = Callable[
    [float, Callable[[], Any]],
    Any,
]


def parse_runtime_args(
    version: str,
    argv: list[str] | None = None,
) -> argparse.Namespace:
    """Parse the existing SolarInspector command-line options."""
    parser = argparse.ArgumentParser(
        description=f"SolarInspector {version}",
    )
    parser.add_argument(
        "--host",
        help=("Webserver-Bind-Adresse; überschreibt config.json"),
    )
    parser.add_argument(
        "--port",
        type=int,
        help=("Webserver-Port; überschreibt config.json"),
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Browser nicht automatisch öffnen",
    )
    parser.add_argument(
        "--configuration",
        action="store_true",
        help=("Beim Start direkt die Konfiguration öffnen"),
    )
    parser.add_argument(
        "--demo-data",
        action="store_true",
        help="Demodaten erzeugen und beenden",
    )
    parser.add_argument(
        "--demo-days",
        type=int,
        default=400,
        help="Anzahl Tage für Demodaten",
    )
    return parser.parse_args(argv)


def run_application(
    args: argparse.Namespace,
    *,
    application: Any,
    config_manager: RuntimeConfigManager,
    collector: RuntimeCollector,
    generate_demo_data: Callable[..., None],
    log_message: Callable[[str], None],
    pid_path: Path,
    process_id: int,
    version: str,
    timer_factory: TimerFactory,
    browser_open: Callable[[str], Any],
    serve_application: Callable[..., Any],
) -> None:
    """Run the existing SolarInspector startup sequence."""
    if args.demo_data:
        generate_demo_data(
            days=max(
                1,
                args.demo_days,
            )
        )
        return

    config = config_manager.get()
    general = config["general"]

    host = args.host or general["bind_host"]
    port = args.port or int(general["port"])

    if general.get("auto_start_collection"):
        collector.start()

    should_open = (
        general.get(
            "open_browser",
            True,
        )
        and not args.no_browser
    )

    browse_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host

    page_path = "/configuration" if args.configuration else "/"

    url = f"http://{browse_host}:{port}{page_path}"

    pid_path.write_text(
        str(process_id),
        encoding="ascii",
    )

    if should_open:
        timer_factory(
            1.2,
            lambda: browser_open(url),
        ).start()

    log_message(f"SolarInspector {version} läuft unter {url} (Bind: {host}:{port}).")

    serve_application(
        application,
        host=host,
        port=port,
        threads=8,
    )


def cleanup_runtime_pid_file(
    pid_path: Path,
    process_id: int,
) -> None:
    """Remove only the PID file owned by this process."""
    try:
        if pid_path.exists() and pid_path.read_text(encoding="ascii").strip() == str(
            process_id
        ):
            pid_path.unlink()
    except OSError:
        pass
