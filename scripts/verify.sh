#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

PYTHON="${REPO_ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
    echo "ERROR: .venv is missing." >&2
    echo "Create it with Python 3.11-3.13 and install requirements-dev.txt." >&2
    exit 1
fi

PYTHON_VERSION="$("${PYTHON}" -c \
    'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

case "${PYTHON_VERSION}" in
    3.11|3.12|3.13)
        ;;
    *)
        echo "ERROR: unsupported local Python ${PYTHON_VERSION}." >&2
        echo "Use one of the CI versions: 3.11, 3.12, or 3.13." >&2
        exit 1
        ;;
esac

echo "==> Python ${PYTHON_VERSION}"
echo "==> Format check"
"${PYTHON}" -m ruff format --check app tests

echo "==> Lint"
"${PYTHON}" -m ruff check app tests

echo "==> Type check"
"${PYTHON}" -m mypy

echo "==> Compile check"
"${PYTHON}" -m compileall -q app tests updater

echo "==> Test suite"
SOLARINSPECTOR_SECRET="solarinspector-test-secret" \
    "${PYTHON}" -m pytest -v tests

echo "==> Diff whitespace check"
git diff --check

echo "==> Working tree summary"
git status --short

echo "==> Verification completed successfully"
