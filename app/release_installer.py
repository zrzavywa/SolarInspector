from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import requests


class ReleaseInstallError(RuntimeError):
    """Raised when a release archive cannot be prepared safely."""


def create_release_venv(
    release_directory: Path,
    python_executable: str | None = None,
) -> Path:
    python_executable = os.path.realpath(
    python_executable or sys.executable
)
    venv_directory = release_directory / ".venv"

    if venv_directory.exists():
        shutil.rmtree(venv_directory)

    try:
        subprocess.run(
            [
                python_executable,
                "-m",
                "venv",
                str(venv_directory),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ReleaseInstallError(
            "Die virtuelle Python-Umgebung konnte nicht erstellt werden: "
            + (exc.stderr or exc.stdout or str(exc))
        ) from exc

    return venv_directory

def get_venv_python(venv_directory: Path) -> Path:
    if os.name == "nt":
        return venv_directory / "Scripts" / "python.exe"

    return venv_directory / "bin" / "python"


def install_release_dependencies(
    release_directory: Path,
    venv_directory: Path,
) -> None:
    requirements_file = (
        release_directory / "app" / "requirements.txt"
    )

    if not requirements_file.is_file():
        raise ReleaseInstallError(
            "requirements.txt fehlt im vorbereiteten Release."
        )

    venv_python = get_venv_python(venv_directory)

    try:
        subprocess.run(
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                "--upgrade",
                "pip",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        subprocess.run(
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                "-r",
                str(requirements_file),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ReleaseInstallError(
            "Python-Abhängigkeiten konnten nicht installiert werden: "
            + (exc.stderr or exc.stdout or str(exc))
        ) from exc



def _is_safe_member(member: tarfile.TarInfo, target_directory: Path) -> bool:
    member_path = target_directory / member.name
    resolved_target = target_directory.resolve()
    resolved_member = member_path.resolve()

    try:
        resolved_member.relative_to(resolved_target)
    except ValueError:
        return False

    if member.issym() or member.islnk():
        return False

    return True

def run_release_smoke_test(
    release_directory: Path,
    venv_directory: Path,
) -> None:
    venv_python = get_venv_python(venv_directory)

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(release_directory / "app")
    environment.setdefault(
        "SOLARINSPECTOR_SECRET",
        "solarinspector-release-smoke-test",
    )

    command = [
        str(venv_python),
        "-c",
        (
            "import solarinspector; "
            "print(solarinspector.get_installed_version())"
        ),
    ]

    try:
        result = subprocess.run(
            command,
            cwd=release_directory,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        raise ReleaseInstallError(
            "Der Release-Smoke-Test hat das Zeitlimit überschritten."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise ReleaseInstallError(
            "Der Release-Smoke-Test ist fehlgeschlagen: "
            + (exc.stderr or exc.stdout or str(exc))
        ) from exc

    expected_version = (
        release_directory / "VERSION"
    ).read_text(encoding="utf-8").strip()

    actual_version = result.stdout.strip()

    if actual_version != expected_version:
        raise ReleaseInstallError(
            f"Versionsprüfung fehlgeschlagen: "
            f"erwartet {expected_version}, erhalten {actual_version}"
        )


def prepare_release_environment(
    archive_path: Path,
    version: str,
    releases_directory: Path,
    python_executable: str | None = None,
) -> Path:
    release_directory = prepare_release(
        archive_path=archive_path,
        version=version,
        releases_directory=releases_directory,
    )

    try:
        venv_directory = create_release_venv(
            release_directory,
            python_executable=python_executable,
        )

        install_release_dependencies(
            release_directory,
            venv_directory,
        )

        run_release_smoke_test(
            release_directory,
            venv_directory,
        )
    except Exception:
        shutil.rmtree(release_directory, ignore_errors=True)
        raise

    return release_directory


def validate_release_archive(
    archive_path: Path,
    expected_top_level: str,
) -> list[tarfile.TarInfo]:
    if not archive_path.is_file():
        raise ReleaseInstallError(
            f"Release-Archiv nicht gefunden: {archive_path}"
        )

    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
    except (tarfile.TarError, OSError) as exc:
        raise ReleaseInstallError(
            "Das Release-Archiv ist beschädigt oder ungültig."
        ) from exc

    if not members:
        raise ReleaseInstallError(
            "Das Release-Archiv ist leer."
        )

    target_directory = Path("/validation-root")

    for member in members:
        if not _is_safe_member(member, target_directory):
            raise ReleaseInstallError(
                f"Unsicherer Archiveintrag: {member.name}"
            )

        first_component = Path(member.name).parts[0]

        if first_component != expected_top_level:
            raise ReleaseInstallError(
                f"Unerwartete Verzeichnisstruktur: {member.name}"
            )

    required_files = {
        f"{expected_top_level}/VERSION",
        f"{expected_top_level}/release-manifest.json",
        f"{expected_top_level}/app/solarinspector.py",
        f"{expected_top_level}/app/requirements.txt",
    }

    available_files = {
        member.name.rstrip("/")
        for member in members
        if member.isfile()
    }

    missing = required_files - available_files

    if missing:
        raise ReleaseInstallError(
            "Pflichtdateien fehlen im Release: "
            + ", ".join(sorted(missing))
        )

    forbidden_names = {
        "config.json",
        "solarinspector.db",
        ".env",
    }

    for member in members:
        if Path(member.name).name in forbidden_names:
            raise ReleaseInstallError(
                f"Unzulässige Laufzeitdatei im Release: {member.name}"
            )

    return members


def prepare_release(
    archive_path: Path,
    version: str,
    releases_directory: Path,
) -> Path:
    expected_top_level = f"SolarInspector-{version}"
    target_directory = releases_directory / version
    temporary_directory = releases_directory / f".{version}.tmp"

    validate_release_archive(
        archive_path=archive_path,
        expected_top_level=expected_top_level,
    )

    releases_directory.mkdir(parents=True, exist_ok=True)

    if temporary_directory.exists():
        shutil.rmtree(temporary_directory)

    temporary_directory.mkdir(parents=True)

    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                if not _is_safe_member(member, temporary_directory):
                    raise ReleaseInstallError(
                        f"Unsicherer Archiveintrag: {member.name}"
                    )

            archive.extractall(temporary_directory)

        extracted_root = temporary_directory / expected_top_level

        if not extracted_root.is_dir():
            raise ReleaseInstallError(
                "Das erwartete Release-Verzeichnis wurde nicht entpackt."
            )

        if target_directory.exists():
            shutil.rmtree(target_directory)

        extracted_root.replace(target_directory)
        shutil.rmtree(temporary_directory, ignore_errors=True)

    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise

    return target_directory


def read_current_release(current_link: Path) -> Path | None:
    if not current_link.exists() and not current_link.is_symlink():
        return None

    if not current_link.is_symlink():
        raise ReleaseInstallError(
            f"{current_link} ist kein symbolischer Link."
        )

    try:
        return current_link.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ReleaseInstallError(
            "Der current-Link verweist auf kein gültiges Release."
        ) from exc

def activate_release(
    release_directory: Path,
    current_link: Path,
) -> Path | None:
    if not release_directory.is_dir():
        raise ReleaseInstallError(
            f"Release-Verzeichnis fehlt: {release_directory}"
        )

    previous_release = read_current_release(current_link)

    current_link.parent.mkdir(parents=True, exist_ok=True)

    temporary_link = current_link.with_name(
        f".{current_link.name}.tmp"
    )

    temporary_link.unlink(missing_ok=True)

    temporary_link.symlink_to(
        release_directory.resolve(),
        target_is_directory=True,
    )

    temporary_link.replace(current_link)

    active_release = read_current_release(current_link)

    if active_release != release_directory.resolve():
        raise ReleaseInstallError(
            "Das Release konnte nicht aktiviert werden."
        )

    return previous_release


def wait_for_healthcheck(
    url: str,
    expected_version: str,
    timeout_seconds: int = 60,
    interval_seconds: float = 2.0,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            response = requests.get(
                url,
                timeout=5,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "SolarInspector-Updater",
                },
            )
            response.raise_for_status()
            payload = response.json()

            if payload.get("status") != "ok":
                raise ReleaseInstallError(
                    f"Healthcheck meldet Status {payload.get('status')!r}."
                )

            if payload.get("version") != expected_version:
                raise ReleaseInstallError(
                    "Healthcheck meldet eine unerwartete Version: "
                    f"{payload.get('version')!r}"
                )

            return payload

        except (
            requests.RequestException,
            ValueError,
            ReleaseInstallError,
        ) as exc:
            last_error = exc
            time.sleep(interval_seconds)

    raise ReleaseInstallError(
        "Healthcheck ist innerhalb des Zeitlimits fehlgeschlagen: "
        + str(last_error or "unbekannter Fehler")
    )


def activate_with_healthcheck(
    release_directory: Path,
    current_link: Path,
    healthcheck_url: str,
    expected_version: str,
    restart_service,
    timeout_seconds: int = 60,
) -> Path | None:
    previous_release = activate_release(
        release_directory=release_directory,
        current_link=current_link,
    )

    try:
        restart_service()

        wait_for_healthcheck(
            url=healthcheck_url,
            expected_version=expected_version,
            timeout_seconds=timeout_seconds,
        )

        return previous_release

    except Exception as exc:
        if previous_release is not None:
            rollback_release(
                previous_release=previous_release,
                current_link=current_link,
            )

            try:
                restart_service()
            except Exception:
                pass

        raise ReleaseInstallError(
            f"Aktivierung fehlgeschlagen; Rollback durchgeführt: {exc}"
        ) from exc


def rollback_release(
    previous_release: Path,
    current_link: Path,
) -> Path:
    if not previous_release.is_dir():
        raise ReleaseInstallError(
            f"Vorheriges Release fehlt: {previous_release}"
        )

    activate_release(
        release_directory=previous_release,
        current_link=current_link,
    )

    return previous_release.resolve()
