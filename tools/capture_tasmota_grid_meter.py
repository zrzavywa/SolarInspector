#!/usr/bin/env python3
"""Capture and sanitize real Tasmota smart-meter HTTP responses.

The tool records ``Status 2`` and repeated ``Status 10`` responses. Raw files
remain in a local, git-ignored directory. Sanitized responses are written to
the Tasmota fixture directory for manual review before they are committed.
"""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
import os
import re
import stat
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import requests

EXAMPLE_IPV4 = "192.0.2.10"
EXAMPLE_IPV6 = "2001:db8::10"
EXAMPLE_MAC = "00:00:5E:00:53:00"

SENSITIVE_KEY_FRAGMENTS = (
    "bssid",
    "clientid",
    "deviceid",
    "friendlyname",
    "hostname",
    "ipaddress",
    "mac",
    "meterid",
    "meternumber",
    "mqttclient",
    "password",
    "passwd",
    "serial",
    "serverid",
    "ssid",
    "topic",
    "username",
)

MAC_PATTERN = re.compile(
    r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])"
)
IP_CANDIDATE_PATTERN = re.compile(
    r"(?<![0-9a-fA-F:.])(?:[0-9a-fA-F:.]{3,45})(?![0-9a-fA-F:.])"
)


def parse_args() -> argparse.Namespace:
    """Parse command-line options without accepting a password argument."""

    parser = argparse.ArgumentParser(
        description=(
            "Capture Tasmota Status 2 and Status 10 responses and create "
            "reviewable sanitized fixtures."
        )
    )
    parser.add_argument("--host", required=True, help="Local Tasmota host or IP")
    parser.add_argument(
        "--scheme",
        choices=("http", "https"),
        default="http",
        help="HTTP scheme, default: http",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=80,
        help="Tasmota web port, default: 80",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="HTTP timeout in seconds, default: 5",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=3,
        help="Number of Status 10 captures, default: 3",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Seconds between Status 10 captures, default: 5",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("SOLARINSPECTOR_TEST_TASMOTA_USERNAME", ""),
        help=("Tasmota web username; defaults to SOLARINSPECTOR_TEST_TASMOTA_USERNAME"),
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path(".phase06-capture"),
        help="Local raw-response directory",
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=Path("tests/fixtures/tasmota"),
        help="Sanitized fixture directory",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable HTTPS certificate verification for a local test device",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    """Reject unsafe or nonsensical capture settings."""

    if not args.host.strip():
        raise ValueError("host must not be empty")
    if not 1 <= args.port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if not 0.1 <= args.timeout <= 60:
        raise ValueError("timeout must be between 0.1 and 60 seconds")
    if not 1 <= args.samples <= 20:
        raise ValueError("samples must be between 1 and 20")
    if not 0 <= args.interval <= 3600:
        raise ValueError("interval must be between 0 and 3600 seconds")


def read_password(username: str) -> str:
    """Read the password from the environment or an interactive prompt."""

    password = os.getenv("SOLARINSPECTOR_TEST_TASMOTA_PASSWORD")
    if password is not None:
        return password
    if username:
        return getpass.getpass("Tasmota password: ")
    return ""


def request_json(
    *,
    base_url: str,
    command: str,
    username: str,
    password: str,
    timeout: float,
    verify_tls: bool,
) -> dict[str, Any]:
    """Execute one Tasmota command and require a JSON object response."""

    params: dict[str, str] = {"cmnd": command}
    if username:
        params["user"] = username
        params["password"] = password

    response = requests.get(
        f"{base_url}/cm",
        params=params,
        timeout=timeout,
        verify=verify_tls,
    )
    response.raise_for_status()

    if not response.content:
        raise RuntimeError(f"{command}: empty HTTP response")

    try:
        payload = response.json()
    except requests.JSONDecodeError as exc:
        raise RuntimeError(f"{command}: response is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"{command}: JSON root is not an object")

    return payload


def normalized_key(value: object) -> str:
    """Normalize a JSON key for conservative sensitivity matching."""

    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def is_sensitive_key(key: object) -> bool:
    """Return whether a key likely contains identifying or secret data."""

    candidate = normalized_key(key)
    return any(fragment in candidate for fragment in SENSITIVE_KEY_FRAGMENTS)


def sanitize_string(value: str) -> str:
    """Replace MAC and IP addresses embedded in arbitrary strings."""

    value = MAC_PATTERN.sub(EXAMPLE_MAC, value)

    def replace_ip_candidate(match: re.Match[str]) -> str:
        candidate = match.group(0).strip(".")
        if not candidate:
            return match.group(0)
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            return match.group(0)
        return EXAMPLE_IPV4 if address.version == 4 else EXAMPLE_IPV6

    return IP_CANDIDATE_PATTERN.sub(replace_ip_candidate, value)


def sanitize(value: Any, key: object = "") -> Any:
    """Recursively redact secrets and stable device identifiers."""

    if is_sensitive_key(key):
        return "<redacted>"

    if isinstance(value, Mapping):
        return {
            str(child_key): sanitize(child_value, child_key)
            for child_key, child_value in value.items()
        }

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize(item) for item in value]

    if isinstance(value, str):
        return sanitize_string(value)

    return value


def write_json(path: Path, payload: Mapping[str, Any], *, private: bool) -> None:
    """Write formatted JSON and restrict raw-file permissions."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if private:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def scalar_paths(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Flatten scalar JSON values to simple dotted diagnostic paths."""

    result: list[tuple[str, Any]] = []

    if isinstance(value, Mapping):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            result.extend(scalar_paths(child, child_prefix))
        return result

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            result.extend(scalar_paths(child, f"{prefix}[{index}]"))
        return result

    result.append((prefix, value))
    return result


def write_paths(path: Path, payload: Mapping[str, Any]) -> None:
    """Write all scalar field paths without guessing semantic mappings."""

    lines = [
        f"{field_path} = {json.dumps(value, ensure_ascii=False)}"
        for field_path, value in scalar_paths(payload)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_sensor_areas(payload: Mapping[str, Any]) -> None:
    """Print detected StatusSNS child areas for manual mapping review."""

    status_sns = payload.get("StatusSNS")
    if not isinstance(status_sns, Mapping):
        print("WARNING: StatusSNS is missing from Status 10.", file=sys.stderr)
        return

    print("Detected StatusSNS areas:")
    for key in status_sns:
        print(f"- StatusSNS.{key}")


def main() -> int:
    """Capture raw responses and create sanitized review fixtures."""

    args = parse_args()
    try:
        validate_args(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    password = read_password(args.username)
    base_url = f"{args.scheme}://{args.host.strip()}:{args.port}"
    verify_tls = not args.insecure

    args.raw_dir.mkdir(parents=True, exist_ok=True)
    args.raw_dir.chmod(stat.S_IRWXU)
    args.fixture_dir.mkdir(parents=True, exist_ok=True)

    try:
        status2 = request_json(
            base_url=base_url,
            command="Status 2",
            username=args.username,
            password=password,
            timeout=args.timeout,
            verify_tls=verify_tls,
        )
        write_json(args.raw_dir / "status2.raw.json", status2, private=True)
        write_json(
            args.fixture_dir / "grid_meter_status2.json",
            sanitize(status2),
            private=False,
        )

        sanitized_samples: list[dict[str, Any]] = []
        for index in range(1, args.samples + 1):
            payload = request_json(
                base_url=base_url,
                command="Status 10",
                username=args.username,
                password=password,
                timeout=args.timeout,
                verify_tls=verify_tls,
            )
            write_json(
                args.raw_dir / f"status10-{index:02d}.raw.json",
                payload,
                private=True,
            )
            sanitized = sanitize(payload)
            if not isinstance(sanitized, dict):
                raise RuntimeError("sanitized response root is not an object")
            sanitized_samples.append(sanitized)
            write_json(
                args.fixture_dir / f"grid_meter_status10_sample_{index:02d}.json",
                sanitized,
                private=False,
            )
            if index < args.samples and args.interval:
                time.sleep(args.interval)

        write_paths(
            args.fixture_dir / "detected-field-paths.txt",
            sanitized_samples[0],
        )
        print_sensor_areas(sanitized_samples[0])
    except requests.RequestException as exc:
        print(f"ERROR: Tasmota request failed: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        password = ""

    print(f"Raw private captures: {args.raw_dir}")
    print(f"Sanitized fixtures: {args.fixture_dir}")
    print("Review every sanitized file before adding it to Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
