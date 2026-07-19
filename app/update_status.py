from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_STATUS = {
    "state": "idle",
    "progress": 0,
    "message": "",
    "installed_version": None,
    "available_version": None,
    "archive_path": None,
    "updated_at": None,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_update_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return dict(DEFAULT_STATUS)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_STATUS)

    result = dict(DEFAULT_STATUS)
    result.update(payload)
    return result


def write_update_status(
    path: Path,
    **values: Any,
) -> dict[str, Any]:
    current = read_update_status(path)
    current.update(values)
    current["updated_at"] = utc_now_iso()

    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(current, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_path.replace(path)

    return current
