# Entwicklungsstandards

Dieses Dokument beschreibt die verbindlichen Entwicklungsstandards für neue
oder wesentlich überarbeitete Python-Komponenten von Zrzavy Energy Monitor 4.5.

Die bestehende Codebasis wird schrittweise angepasst. Auch mit Stand 4.5.1
sind eine vollständige Neuformatierung, Typisierung oder Modularisierung des
Altbestands nicht abgeschlossen.

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

Der Dokumentationsqualitätsvertrag prüft lokal und ohne Netzwerkzugriff
relative Links aktiver Dokumente, Dokumentations- und Archivindex,
Versionsstand, Konfigurationsschlüssel, aktuelle Architekturpfade sowie die
Struktur von Mermaid-Blöcken. Historische Entwicklungsnachweise werden dabei
getrennt vom aktiven Dokumentationsbestand behandelt.

Vor einem Commit ist der kanonische lokale Prüflauf auszuführen:

```bash
./scripts/verify.sh
```

Das Skript verwendet ausschließlich `.venv`, prüft eine der unterstützten
Python-Versionen 3.11 bis 3.13 und führt Formatierung, Linting, Typprüfung,
Kompilierung, Tests und `git diff --check` aus. Die wesentlichen Prüfungen
werden auch in den GitHub-Actions-Workflows für Tests und Releases ausgeführt.

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
- `app/zrzavy_energy_monitor.py`
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

Die verbindliche und aktuelle Auswahl der durch mypy geprüften Module steht
ausschließlich unter `[tool.mypy].files` in `pyproject.toml`. Sie umfasst mit
Stand 4.5.0 bereits zentrale Module für Branding, Migration, Konfiguration,
Adapter, Modelle, Validierung, Persistenz, Dienste und Webdarstellung. Diese
Liste wird hier bewusst nicht dupliziert, damit Dokumentation und
Toolkonfiguration nicht auseinanderlaufen.

Neue Module und wesentlich überarbeitete Funktionen sollen vollständig
typisiert und, soweit geeignet, in diese Konfiguration aufgenommen werden.

Eine strikte Typprüfung der gesamten bestehenden Anwendung ist derzeit
bewusst nicht aktiviert.

## Verbleibende technische Schulden in 4.5.1

Mit Stand 4.5.1 bleiben insbesondere folgende Punkte offen:

1. Zehn historische Dateien sind noch nicht Ruff-formatiert.
2. Mypy deckt noch nicht die gesamte Anwendung und die Tests ab.
3. Docstring-Regeln werden für Altcode weiterhin nicht global geprüft; der
   aktuelle Vollmessungsvertrag weist 84/84 Module und 425/425 öffentliche
   Symbole mit den geprüften Docstrings nach.
4. Die vollständige Docstring-Messung ist ein Qualitätsvertrag und ersetzt
   keine fachliche Laufzeitprüfung.
5. Der kanonische Einstiegspunkt `app/zrzavy_energy_monitor.py` bündelt
   weiterhin mehrere Web- und Laufzeitverantwortlichkeiten.
6. Die weitere Modularisierung ist geplant, aber keiner veröffentlichten
   Version nach 4.5.1 verbindlich zugeordnet.

Diese Punkte sind bekannte Migrationsaufgaben und keine Aufforderung zu einer
ungeprüften Gesamtüberarbeitung.
