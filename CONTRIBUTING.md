# Mitwirken an SolarInspector

Beiträge zu Dokumentation, Fehleranalyse, Gerätekompatibilität und Softwareverbesserungen sind willkommen.

## Vor einem Beitrag

- Bestehende Issues und Pull Requests prüfen.
- Bei größeren Änderungen zunächst Ziel, Umfang und betroffene Plattform beschreiben.
- Keine realen Kennwörter, Tokens, Seriennummern, Kundendaten oder privaten Netzwerkdaten veröffentlichen.
- Aktuellen Produktstand und geplante Zielarchitektur nicht vermischen.

## Dokumentationsänderungen

Dokumentation liegt überwiegend im Verzeichnis `docs/`. Die zentrale Einstiegseite ist `README.md` im Repository-Stamm.

Bitte bei Änderungen beachten:

- kurze, vollständige Sätze verwenden,
- Befehle in Codeblöcken darstellen,
- relative Links innerhalb des Repositorys verwenden,
- Beispiele klar als Beispiele kennzeichnen,
- versionsabhängige Aussagen mit einer Versionsangabe versehen,
- geplante Funktionen ausdrücklich als **geplant** markieren,
- sicherheitsrelevante Auswirkungen nennen,
- bei neuen Konfigurationsfeldern auch `docs/configuration.md` aktualisieren,
- bei neuen Endpunkten auch `docs/api.md` aktualisieren,
- bei sichtbaren Änderungen `CHANGELOG.md` ergänzen.

## Softwareänderungen

Für Python-Code gelten die verbindlichen
[Entwicklungsstandards](docs/development.md). Sie beschreiben insbesondere
Formatierung, Typannotationen, Docstrings, Tests und die schrittweise Migration
des bestehenden Codes.

Vor einem Commit mit Python-Änderungen mindestens ausführen:

```bash
python -m ruff format --check app tests
python -m ruff check app tests
python -m mypy
SOLARINSPECTOR_SECRET="solarinspector-test-secret" python -m pytest -v tests
git diff --check
```

## Branch- und Pull-Request-Ablauf

```bash
git switch main
git pull
git switch -c docs/<kurze-beschreibung>
```

Nach den Änderungen:

```bash
git status
git diff --check
git diff
git add README.md CHANGELOG.md CONTRIBUTING.md docs/
git commit -m "docs: update SolarInspector documentation"
git push -u origin docs/<kurze-beschreibung>
```

Anschließend einen Pull Request gegen `main` erstellen.

## Pull-Request-Checkliste

- [ ] Inhalt entspricht dem aktuellen Verhalten der Software.
- [ ] Geplante Funktionen sind als geplant gekennzeichnet.
- [ ] Interne Links wurden geprüft.
- [ ] Befehle enthalten keine persönlichen Pfade oder Zugangsdaten.
- [ ] Screenshots enthalten keine sensiblen Informationen.
- [ ] `CHANGELOG.md` wurde bei relevanten Änderungen ergänzt.
- [ ] Rechtschreibung und Formatierung wurden geprüft.

## Fehlerberichte

Ein guter Fehlerbericht enthält:

- SolarInspector-Version,
- Raspberry-Pi-Modell und Betriebssystem,
- Python-Version,
- Installationsart,
- betroffene Messquelle,
- erwartetes und tatsächliches Verhalten,
- reproduzierbare Schritte,
- relevante, bereinigte Logauszüge.

Bitte niemals vollständige `config.json`, Datenbanken oder Diagnosearchive ungeprüft veröffentlichen.

## Commit-Konvention

Empfohlene Präfixe:

| Präfix | Zweck |
|---|---|
| `docs:` | Dokumentation |
| `fix:` | Fehlerkorrektur |
| `feat:` | neue Funktion |
| `test:` | Tests |
| `chore:` | Wartung und Releasearbeiten |
| `security:` | Sicherheitsverbesserung |
