#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
MIGRATION_PYTHON="${MIGRATION_PYTHON:-python3}"

export PYTHONPATH="$PROJECT_ROOT/app${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1

ORCHESTRATE_SYSTEMD=false
KEEP_LEGACY_PATHS=false
DATA_MIGRATION_APPLIED=false
MIGRATION_ARGUMENTS=()
MODE=""

for argument in "$@"; do
    case "$argument" in
        --orchestrate-systemd)
            ORCHESTRATE_SYSTEMD=true
            ;;
        --keep-legacy-paths)
            KEEP_LEGACY_PATHS=true
            ;;
        --dry-run|--apply|--rollback)
            MODE="$argument"
            MIGRATION_ARGUMENTS+=("$argument")
            ;;
        *)
            MIGRATION_ARGUMENTS+=("$argument")
            ;;
    esac
done

if [[ "$ORCHESTRATE_SYSTEMD" != true ]]; then
    exec "$MIGRATION_PYTHON" \
        -m zrzavy_energy_monitor_core.direct_migration \
        "${MIGRATION_ARGUMENTS[@]}"
fi

if [[ "$EUID" -ne 0 ]]; then
    echo "Migration refused: --orchestrate-systemd requires root." >&2
    exit 2
fi

if [[ -z "$MODE" ]]; then
    echo "Migration refused: select --dry-run, --apply, or --rollback." >&2
    exit 2
fi

OLD_SERVICE="solarinspector.service"
OLD_UPDATER_PATH="solarinspector-updater.path"
NEW_SERVICE="zrzavy-energy-monitor.service"
NEW_UPDATER_PATH="zrzavy-energy-monitor-updater.path"
UNIT_SOURCE="$PROJECT_ROOT/systemd"
UNIT_TARGET="/etc/systemd/system"
HEALTHCHECK_URL="${ZRZAVY_ENERGY_MONITOR_HEALTHCHECK_URL:-http://127.0.0.1:8787/api/health}"

systemctl_is_active() {
    systemctl is-active --quiet "$1"
}

run_data_migration() {
    "$MIGRATION_PYTHON" \
        -m zrzavy_energy_monitor_core.direct_migration \
        "${MIGRATION_ARGUMENTS[@]}" \
        --services-stopped
}

restore_legacy_service() {
    local rollback_arguments=()
    local rollback_mode_added=false
    local argument

    for argument in "${MIGRATION_ARGUMENTS[@]}"; do
        case "$argument" in
            --dry-run|--apply|--rollback)
                if [[ "$rollback_mode_added" == false ]]; then
                    rollback_arguments+=("--rollback")
                    rollback_mode_added=true
                fi
                ;;
            --services-stopped)
                ;;
            *)
                rollback_arguments+=("$argument")
                ;;
        esac
    done

    systemctl stop "$NEW_SERVICE" >/dev/null 2>&1 || true
    systemctl disable "$NEW_SERVICE" "$NEW_UPDATER_PATH" >/dev/null 2>&1 || true
    if [[ "$DATA_MIGRATION_APPLIED" == true ]]; then
        "$MIGRATION_PYTHON" \
            -m zrzavy_energy_monitor_core.direct_migration \
            "${rollback_arguments[@]}" \
            --services-stopped || true
    fi
    systemctl daemon-reload || true
    systemctl enable --now "$OLD_SERVICE" || true
    systemctl enable --now "$OLD_UPDATER_PATH" || true
}

if [[ "$MODE" == "--dry-run" ]]; then
    if systemctl_is_active "$NEW_SERVICE"; then
        echo "Migration refused: $NEW_SERVICE is already active." >&2
        exit 2
    fi
    exec "$MIGRATION_PYTHON" \
        -m zrzavy_energy_monitor_core.direct_migration \
        "${MIGRATION_ARGUMENTS[@]}"
fi

if [[ "$MODE" == "--rollback" ]]; then
    systemctl stop "$NEW_SERVICE" "$NEW_UPDATER_PATH" || true
    systemctl stop "$OLD_SERVICE" "$OLD_UPDATER_PATH" || true
    if systemctl_is_active "$OLD_SERVICE" || systemctl_is_active "$NEW_SERVICE"; then
        echo "Rollback refused: a collector is still active." >&2
        exit 2
    fi
    run_data_migration
    systemctl disable "$NEW_SERVICE" "$NEW_UPDATER_PATH" || true
    systemctl daemon-reload
    systemctl enable --now "$OLD_SERVICE"
    systemctl enable --now "$OLD_UPDATER_PATH"
    exit 0
fi

if systemctl_is_active "$NEW_SERVICE"; then
    echo "Migration refused: $NEW_SERVICE is already active." >&2
    exit 2
fi

for required_file in \
    "$UNIT_SOURCE/zrzavy-energy-monitor.service" \
    "$UNIT_SOURCE/zrzavy-energy-monitor-updater.service" \
    "$UNIT_SOURCE/zrzavy-energy-monitor-updater.path" \
    "/opt/zrzavy-energy-monitor/current/app/zrzavy_energy_monitor.py"; do
    if [[ ! -f "$required_file" ]]; then
        echo "Migration refused: required file is missing: $required_file" >&2
        exit 2
    fi
done

systemctl stop "$OLD_UPDATER_PATH"
systemctl stop "$OLD_SERVICE"

if systemctl_is_active "$OLD_SERVICE" || systemctl_is_active "$NEW_SERVICE"; then
    echo "Migration refused: a collector is still active." >&2
    exit 2
fi

trap restore_legacy_service ERR
run_data_migration
DATA_MIGRATION_APPLIED=true

install -m 0644 \
    "$UNIT_SOURCE/zrzavy-energy-monitor.service" \
    "$UNIT_TARGET/zrzavy-energy-monitor.service"
install -m 0644 \
    "$UNIT_SOURCE/zrzavy-energy-monitor-updater.service" \
    "$UNIT_TARGET/zrzavy-energy-monitor-updater.service"
install -m 0644 \
    "$UNIT_SOURCE/zrzavy-energy-monitor-updater.path" \
    "$UNIT_TARGET/zrzavy-energy-monitor-updater.path"

systemctl daemon-reload
systemctl enable --now "$NEW_SERVICE"

"$MIGRATION_PYTHON" -c \
    "from release_installer import wait_for_healthcheck; wait_for_healthcheck('$HEALTHCHECK_URL', '4.5.0')"

systemctl enable --now "$NEW_UPDATER_PATH"
systemctl disable "$OLD_SERVICE" "$OLD_UPDATER_PATH"

if [[ "$KEEP_LEGACY_PATHS" == true ]]; then
    echo "Legacy paths and units were retained for rollback."
else
    echo "Legacy files were retained; removal requires the final migration gate."
fi

trap - ERR
echo "Zrzavy Energy Monitor 4.5.0 migration completed."
