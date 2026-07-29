# Zrzavy Energy Monitor 4.5.5

Phase 10C ist ein korrigierendes Release für Installation, Update und direkte
SolarInspector-4.1.3-Migration. Der Preflight importiert die Anwendung nicht,
verwendet einen erkannten Python-3.11+-Interpreter und prüft portable SHA-256-
Dateien. Vor der Aktivierung werden Backups und SQLite-Integrität geprüft;
fehlgeschlagene Healthchecks lösen den vorhandenen Rollback aus.

Auf Raspberry Pi OS Bullseye ist der Interpreter `/opt/python-3.11.15/bin/python3.11`
zu verwenden, falls vorhanden. Das System-Python bleibt unverändert.

## Reproduzierbarer Bullseye-Test

Auf einem Testgerät mit Raspberry Pi OS Bullseye werden vor der Migration
`python3 --version`, `/opt/python-3.11.15/bin/python3.11 --version`,
`./scripts/migrate-to-zrzavy-energy-monitor.sh --dry-run` und die SQLite-
Integritätsprüfung ausgeführt. Anschließend wird mit `--apply` migriert und
`curl -fsS http://127.0.0.1:8787/api/health` muss exakt `status=ok` sowie
`version=4.5.5` melden. Erst danach werden die Legacy-Units deaktiviert.

Dieser Hardware-/systemd-Test ist im Repository nicht ausführbar und muss auf
einem isolierten Bullseye-Testgerät protokolliert werden.
