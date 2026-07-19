from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from release_installer import (
    ReleaseInstallError,
    activate_with_healthcheck,
    prepare_release_environment,
)
from update_status import write_update_status


DEFAULT_REQUEST_PATH = Path(
    "/var/lib/solarinspector/update-request.json"
)
DEFAULT_STATUS_PATH = Path(
    "/var/lib/solarinspector/update-status.json"
)
DEFAULT_RELEASES_DIR = Path(
    "/opt/solarinspector/releases"
)
DEFAULT_CURRENT_LINK = Path(
    "/opt/solarinspector/current"
)
DEFAULT_HEALTHCHECK_URL = (
    "http://127.0.0.1:8787/api/health"
)
DEFAULT_SERVICE_NAME = "solarinspector.service"


def read_request(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReleaseInstallError(
            f"Update-Anforderung fehlt: {path}"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseInstallError(
            "Update-Anforderung ist ungültig."
        ) from exc

    required = {
        "version",
        "archive_path",
    }

    missing = required - payload.keys()

    if missing:
        raise ReleaseInstallError(
            "Pflichtfelder fehlen: "
            + ", ".join(sorted(missing))
        )

    return payload


def restart_systemd_service(
    service_name: str,
) -> None:
    try:
        subprocess.run(
            [
                "/usr/bin/systemctl",
                "restart",
                service_name,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ReleaseInstallError(
            "SolarInspector-Service konnte nicht neu gestartet werden: "
            + (exc.stderr or exc.stdout or str(exc))
        ) from exc


def run_update(
    request_path: Path,
    status_path: Path,
    releases_directory: Path,
    current_link: Path,
    healthcheck_url: str,
    service_name: str,
) -> None:
    request = read_request(request_path)

    version = str(request["version"])
    archive_path = Path(request["archive_path"])

    write_update_status(
        status_path,
        state="preparing",
        progress=10,
        message="Release-Umgebung wird vorbereitet.",
        available_version=version,
    )

    release_directory = prepare_release_environment(
        archive_path=archive_path,
        version=version,
        releases_directory=releases_directory,
    )

    write_update_status(
        status_path,
        state="activating",
        progress=75,
        message="Neue Version wird aktiviert.",
        available_version=version,
    )

    activate_with_healthcheck(
        release_directory=release_directory,
        current_link=current_link,
        healthcheck_url=healthcheck_url,
        expected_version=version,
        restart_service=lambda: restart_systemd_service(
            service_name
        ),
    )

    write_update_status(
        status_path,
        state="success",
        progress=100,
        message="Update erfolgreich installiert.",
        available_version=version,
        archive_path=str(archive_path),
    )

    request_path.unlink(missing_ok=True)

def main() -> int:
    parser = argparse.ArgumentParser(
        description="SolarInspector privileged updater"
    )

    parser.add_argument(
        "--request",
        type=Path,
        default=DEFAULT_REQUEST_PATH,
    )
    parser.add_argument(
        "--status",
        type=Path,
        default=DEFAULT_STATUS_PATH,
    )
    parser.add_argument(
        "--releases",
        type=Path,
        default=DEFAULT_RELEASES_DIR,
    )
    parser.add_argument(
        "--current",
        type=Path,
        default=DEFAULT_CURRENT_LINK,
    )
    parser.add_argument(
        "--healthcheck-url",
        default=DEFAULT_HEALTHCHECK_URL,
    )
    parser.add_argument(
        "--service",
        default=DEFAULT_SERVICE_NAME,
    )

    args = parser.parse_args()

    try:
        run_update(
            request_path=args.request,
            status_path=args.status,
            releases_directory=args.releases,
            current_link=args.current,
            healthcheck_url=args.healthcheck_url,
            service_name=args.service,
        )
    except Exception as exc:
        write_update_status(
            args.status,
            state="failed",
            progress=0,
            message=str(exc),
        )

        args.request.unlink(missing_ok=True)

        print(str(exc), file=sys.stderr)
        return 1

    return 0




if __name__ == "__main__":
    raise SystemExit(main())
