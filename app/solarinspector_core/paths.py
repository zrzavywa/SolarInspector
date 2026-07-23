"""Define filesystem paths used by the SolarInspector application.

This module derives paths only. Importing it does not create directories,
read configuration files, open databases, or write application data.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "solarinspector.db"
LOG_PATH = DATA_DIR / "solarinspector.log"
PID_PATH = DATA_DIR / "solarinspector.pid"

UPDATE_STATUS_PATH = Path(
    os.environ.get(
        "SOLARINSPECTOR_UPDATE_STATUS",
        BASE_DIR / "data" / "update-status.json",
    )
)

UPDATE_CACHE_DIR = Path(
    os.environ.get(
        "SOLARINSPECTOR_UPDATE_CACHE",
        BASE_DIR / "data" / "updates",
    )
)

UPDATE_REQUEST_PATH = Path(
    os.environ.get(
        "SOLARINSPECTOR_UPDATE_REQUEST",
        BASE_DIR / "data" / "update-request.json",
    )
)
