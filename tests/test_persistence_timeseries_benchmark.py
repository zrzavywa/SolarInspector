"""Exercise the reproducible Phase 10 persistence benchmark."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_small_benchmark_validates_rows_growth_queries_and_locking(
    tmp_path: Path,
) -> None:
    output = tmp_path / "benchmark.json"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "app"

    result = subprocess.run(
        [
            str(Path(".venv/bin/python").resolve()),
            "scripts/persistence_timeseries_benchmark.py",
            "--cycles",
            "100",
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["poll_interval_seconds"] == 5
    assert report["row_counts"] == {
        "energy_balance_samples": 100,
        "grid_meter_samples": 100,
        "measurements": 2_500,
        "phase_samples": 100,
        "samples": 100,
        "source_selection_events": 600,
    }
    assert report["database_size_bytes"] > 0
    assert report["queries"]["one_day"]["rows"] == 100
    assert report["queries"]["thirty_days"]["rows"] == 100
    assert report["concurrent_reader_queries"] > 0
    assert report["locking_errors"] == []
    assert report["integrity_check"] == "ok"
    assert report["write_ms"]["average"] < 5_000
