"""Provide an isolated application database for import-time startup tests."""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_TEST_APPLICATION_DIRECTORY = Path(tempfile.mkdtemp(prefix="solarinspector-pytest-"))
os.environ.setdefault(
    "SOLARINSPECTOR_DATABASE_PATH",
    str(_TEST_APPLICATION_DIRECTORY / "solarinspector.db"),
)
os.environ.setdefault(
    "SOLARINSPECTOR_SECRET",
    "solarinspector-test-secret",
)
atexit.register(shutil.rmtree, _TEST_APPLICATION_DIRECTORY, True)
