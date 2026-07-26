"""Guard against SQLite connection leaks in the test suite."""

from __future__ import annotations

from pathlib import Path


def test_tests_do_not_use_sqlite_connection_as_closing_context() -> None:
    """Require explicit closing around direct sqlite3 test connections."""

    unsafe_token = "with " + "sqlite3.connect("
    offenders = []

    for path in sorted(Path("tests").rglob("*.py")):
        if path.name == Path(__file__).name:
            continue
        if unsafe_token in path.read_text(encoding="utf-8"):
            offenders.append(path.as_posix())

    assert offenders == [], (
        "sqlite3.Connection commits or rolls back in a with-block, "
        "but it does not close itself. Wrap direct test connections "
        f"with contextlib.closing: {offenders}"
    )
