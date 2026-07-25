#!/usr/bin/env python3
"""Observe a running SolarInspector validation API without changing settings."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    """Parse a bounded 15-to-60-minute observation run."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8787",
    )
    parser.add_argument("--duration-minutes", type=float, default=15.0)
    parser.add_argument("--interval-seconds", type=float, default=10.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("validation-hardware-soak.json"),
    )
    return parser.parse_args()


def _read_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    """Read one local JSON endpoint with a bounded timeout."""

    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(
        request,
        timeout=timeout_seconds,
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("API response must be a JSON object")
    return payload


def main() -> int:
    """Collect an observation report without modifying configuration."""

    args = parse_args()
    if not 15.0 <= args.duration_minutes <= 60.0:
        raise SystemExit("--duration-minutes must be between 15 and 60")
    if args.interval_seconds < 2.0:
        raise SystemExit("--interval-seconds must be at least 2")

    base_url = args.base_url.rstrip("/")
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit("--base-url must be an HTTP or HTTPS URL")

    started_at = datetime.now().astimezone()
    deadline = time.monotonic() + args.duration_minutes * 60.0
    poll_count = 0
    successful_polls = 0
    validation_statuses: Counter[str] = Counter()
    collector_statuses: Counter[str] = Counter()
    warning_occurrences: list[int] = []
    rejection_occurrences: list[int] = []
    response_seconds: list[float] = []
    errors: Counter[str] = Counter()
    latest_events: dict[int, dict[str, Any]] = {}

    while time.monotonic() < deadline:
        poll_count += 1
        poll_started = time.perf_counter()
        try:
            live = _read_json(
                f"{base_url}/api/live",
                timeout_seconds=min(10.0, args.interval_seconds),
            )
            summary = _read_json(
                f"{base_url}/api/validation/summary?hours=24&limit=50",
                timeout_seconds=min(10.0, args.interval_seconds),
            )
            successful_polls += 1
            validation_statuses[str(summary.get("status", "unknown"))] += 1

            collector = live.get("collector", {})
            running = collector.get("running") if isinstance(collector, dict) else None
            collector_statuses[str(running)] += 1

            aggregate = summary.get("summary", {})
            if isinstance(aggregate, dict):
                warning_occurrences.append(
                    int(aggregate.get("warning_occurrence_count", 0))
                )
                rejection_occurrences.append(
                    int(aggregate.get("rejection_occurrence_count", 0))
                )

            recent_events = summary.get("recent_events", [])
            if isinstance(recent_events, list):
                for event in recent_events:
                    if isinstance(event, dict) and isinstance(
                        event.get("id"),
                        int,
                    ):
                        latest_events[event["id"]] = event
        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
            urllib.error.URLError,
        ) as exc:
            errors[type(exc).__name__] += 1
        finally:
            response_seconds.append(time.perf_counter() - poll_started)

        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(args.interval_seconds, remaining))

    finished_at = datetime.now().astimezone()
    report = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "base_url": base_url,
        "duration_minutes": args.duration_minutes,
        "interval_seconds": args.interval_seconds,
        "poll_count": poll_count,
        "successful_poll_count": successful_polls,
        "validation_status_counts": dict(validation_statuses),
        "collector_running_counts": dict(collector_statuses),
        "warning_occurrence_range": {
            "minimum": min(warning_occurrences) if warning_occurrences else None,
            "maximum": max(warning_occurrences) if warning_occurrences else None,
        },
        "rejection_occurrence_range": {
            "minimum": min(rejection_occurrences) if rejection_occurrences else None,
            "maximum": max(rejection_occurrences) if rejection_occurrences else None,
        },
        "response_seconds": {
            "minimum": min(response_seconds) if response_seconds else None,
            "maximum": max(response_seconds) if response_seconds else None,
            "average": (
                sum(response_seconds) / len(response_seconds)
                if response_seconds
                else None
            ),
        },
        "distinct_api_errors": dict(errors),
        "recent_validation_events": list(latest_events.values()),
        "passed_transport_observation": (successful_polls > 0 and not errors),
        "manual_review_required": True,
        "manual_review_note": (
            "Review warnings and rejections against the physical "
            "installation. This script never changes validation limits."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0 if successful_polls else 1


if __name__ == "__main__":
    raise SystemExit(main())
