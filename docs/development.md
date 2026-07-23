# Entwicklungsstandards

Dieses Dokument beschreibt die verbindlichen Entwicklungsstandards für neue
oder wesentlich überarbeitete Python-Komponenten von SolarInspector 4.5.

Die bestehende Codebasis wird schrittweise angepasst. Eine vollständige
Neuformatierung oder Modularisierung des Altbestands ist nicht Bestandteil
der Phase 01.

## Unterstützte Python-Versionen

Die automatisierten Tests laufen mit:

- Python 3.11
- Python 3.12
- Python 3.13

Python 3.11 ist die minimale unterstützte Version und das konfigurierte Ziel
für Ruff und mypy.

## Entwicklungsumgebung

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

## Verbindliche Prüfungen

Vor einem Commit mit Python-Änderungen sind mindestens folgende Befehle
auszuführen:

```bash
python -m ruff format --check app tests
python -m ruff check app tests
python -m mypy
SOLARINSPECTOR_SECRET="solarinspector-test-secret" python -m pytest -v tests
git diff --check
```

Diese Prüfungen werden auch in den GitHub-Actions-Workflows für Tests und
Releases ausgeführt.

## Stil und Struktur

Für neuen und wesentlich überarbeiteten Python-Code gelten:

- PEP 8 für Stil, Benennung und Struktur,
- PEP 257 für Docstrings,
- Google-Style-Docstrings,
- verständliche Typannotationen,
- klar abgegrenzte Verantwortlichkeiten,
- pragmatische Clean-Code- und SOLID-Grundsätze.

Abstraktionen sollen ein konkretes Wartbarkeits- oder Testproblem lösen.
Zusätzliche Schichten ohne erkennbaren Nutzen sind zu vermeiden.

## Namen und Einheiten

Namen sollen Zweck und fachliche Bedeutung verständlich ausdrücken.
Unklare Abkürzungen sind zu vermeiden.

Physikalische Einheiten werden nach Möglichkeit im Namen angegeben:

- `power_w`
- `energy_kwh`
- `voltage_v`
- `current_a`
- `duration_s`
- `timestamp_utc`

Vorzeichen sowie Ein- und Ausgaberichtungen müssen in Docstrings oder an der
fachlichen Schnittstelle eindeutig beschrieben werden.

## Funktionen und Fehlerbehandlung

Funktionen sollen klein und fachlich zusammenhängend bleiben.

Bevorzugt werden:

- frühe Rückgaben statt tiefer Verschachtelung,
- gezielte Exception-Typen,
- Konstanten statt Magic Numbers,
- explizite Fehlerbehandlung,
- verständliche und strukturierte Logmeldungen.

Fehler dürfen nicht stillschweigend ignoriert werden. Wird ein Fehler bewusst
toleriert, müssen Grund, Auswirkung und Ersatzverhalten nachvollziehbar sein.

## Docstrings

Jedes neue oder wesentlich überarbeitete Modul erhält einen Modul-Docstring.

Öffentliche Klassen, Methoden und Funktionen dokumentieren abhängig von ihrer
Komplexität:

- Zweck,
- Parameter,
- Einheiten,
- Rückgabewerte,
- mögliche Fehler,
- Seiteneffekte,
- relevante Grenz- und Vorzeichenfälle.

Kommentare erklären hauptsächlich, warum eine Entscheidung getroffen wurde.
Sie sollen nicht wiederholen, was der Code bereits sichtbar tut.

## Tests

Tests sollen:

- reproduzierbar und unabhängig sein,
- keine realen Geräte oder externen Dienste benötigen,
- temporäre Dateien und Datenbanken isolieren,
- keine Kennwörter oder privaten Netzwerkdaten enthalten,
- fachliches Verhalten statt Implementierungsdetails prüfen.

Neue fachliche Funktionen benötigen Tests für Normalfälle, Grenzfälle und
relevante Fehlerfälle.

## Schrittweise Ruff-Migration

Der Ruff-Formatter nimmt derzeit folgende historische Dateien aus:

- `app/github_updater.py`
- `app/modbus_solakon.py`
- `app/release_installer.py`
- `app/solarinspector.py`
- `app/updater_service.py`
- `tests/test_core.py`
- `tests/test_release_installer.py`
- `tests/test_update_api.py`
- `tests/test_update_download_api.py`
- `tests/test_updater_service.py`

Diese Dateien werden weiterhin durch Ruff gelintet.

Wird eine ausgenommene Datei wesentlich überarbeitet, soll sie vollständig
formatiert und anschließend aus der Ausnahmeliste entfernt werden. Eine reine
Neuformatierung soll möglichst in einem getrennten Commit erfolgen.

## Schrittweise mypy-Migration

Mypy prüft derzeit:

- `app/github_updater.py`
- `app/update_status.py`
- `app/modbus_solakon.py`
- `app/release_installer.py`

Neue Module und wesentlich überarbeitete Funktionen sollen vollständig
typisiert werden. Weitere geeignete Module werden schrittweise in die
mypy-Konfiguration aufgenommen.

Eine strikte Typprüfung der gesamten bestehenden Anwendung ist derzeit
bewusst nicht aktiviert.

## Verbleibende technische Schulden

Nach Phase 01 bleiben insbesondere folgende Punkte offen:

1. Zehn historische Dateien sind noch nicht Ruff-formatiert.
2. Mypy deckt noch nicht die gesamte Anwendung und die Tests ab.
3. Docstring-Regeln werden für Altcode noch nicht global geprüft.
4. Modul- und API-Docstrings sind im Altcode nicht vollständig.
5. `app/solarinspector.py` bündelt weiterhin mehrere Verantwortlichkeiten.
6. Die vollständige Modularisierung erfolgt in einer späteren Phase.

Diese Punkte sind bekannte Migrationsaufgaben und keine Aufforderung zu einer
ungeprüften Gesamtüberarbeitung.
