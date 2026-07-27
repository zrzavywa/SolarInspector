"""AST checks for the operational docstring contract."""

import ast
from pathlib import Path

SCOPE_FILES = (
    "app/github_updater.py",
    "app/release_installer.py",
    "app/update_status.py",
    "app/updater_service.py",
    "app/zrzavy_energy_monitor_core/persistence/database.py",
    "app/zrzavy_energy_monitor_core/services/collector.py",
    "app/zrzavy_energy_monitor.py",
    "app/zrzavy_energy_monitor_core/web/context.py",
    "app/zrzavy_energy_monitor_core/adapters/solakon.py",
    "app/zrzavy_energy_monitor_core/adapters/shelly.py",
    "app/zrzavy_energy_monitor_core/services/periods.py",
    "app/zrzavy_energy_monitor_core/services/dashboard.py",
    "app/zrzavy_energy_monitor_core/services/demo.py",
)


def _public_definitions(nodes: list[ast.stmt]):
    """Yield public classes and functions, including public class methods."""
    for node in nodes:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                yield node
            if isinstance(node, ast.ClassDef):
                yield from _public_definitions(node.body)


def test_operational_modules_and_public_symbols_have_docstrings() -> None:
    """Require non-empty docstrings without prescribing exact wording."""
    missing: list[str] = []
    for filename in SCOPE_FILES:
        tree = ast.parse(Path(filename).read_text(encoding="utf-8"))
        if not ast.get_docstring(tree):
            missing.append(f"{filename}:<module>")
        for node in _public_definitions(tree.body):
            if not ast.get_docstring(node):
                missing.append(f"{filename}:{node.name}:{node.lineno}")
    assert not missing, "Missing operational docstrings:\n" + "\n".join(missing)
