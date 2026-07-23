"""Write timestamped SolarInspector application log messages.

This module preserves the existing stdout and file logging behavior.
Importing it does not create directories or write log entries.
"""

from __future__ import annotations

from datetime import datetime

from solarinspector_core.paths import DATA_DIR, LOG_PATH


def log(message: str) -> None:
    """Write a timestamped message to stdout and the application log."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"{stamp} {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
