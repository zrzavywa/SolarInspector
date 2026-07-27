# Zrzavy Energy Monitor 4.5.1

## Überblick

Zrzavy Energy Monitor 4.5.1 ist ein Patch-Release für bestehende 4.5.0-
Installationen. Es bündelt die seit 4.5.0 gemergten Dokumentations-,
Docstring- und Dokumentationsqualitätsarbeiten.

## Dokumentationsverbesserungen

- Architektur-, API-, Betriebs- und Entwicklungsdokumentation wurden
  kontextsensitiv auf den aktuellen Produktstand 4.5.1 aktualisiert.
- Die aktive Dokumentation verwendet konsistent den kanonischen Produktnamen
  und Namespace.
- Der Docstring-Qualitätsstand ist mit 84/84 Modulen und 425/425 öffentlichen
  Symbolen dokumentiert.

## Entwicklungs- und Qualitätsverträge

- Versions-, Release-, API- und Dokumentationsverträge prüfen den kanonischen
  VERSION-Wert und die daraus abgeleiteten Assetnamen.
- Das Releasearchiv wird mit Manifest und SHA-256-Prüfsumme reproduzierbar
  erzeugt.
- Das Konfigurationsschema bleibt 5.

## Kompatibilität

Es gibt keine beabsichtigte Änderung von Mess-, Validierungs-, Persistenz-,
Quellenauswahl- oder Energiebilanzsemantik. Das Datenbankschema und das
Konfigurationsschema bleiben unverändert. Die Legacy-Kompatibilität bleibt
während der 4.5-Reihe erhalten.

Die direkte Migration von SolarInspector 4.1.3 bleibt ein 4.5.0-
Migrationsvertrag. Historische Migrations-IDs, Backups und Nachweise werden
nicht auf 4.5.1 umgeschrieben.

Die HTTP-API bleibt lokal, unversioniert und ohne Authentifizierung,
Autorisierung oder CSRF-Prüfung. Sie darf nicht ungeschützt aus dem Internet
erreichbar gemacht werden.

## Installation und Update

Bestehende Installationen verwenden den vorhandenen geprüften Updateweg mit
Backup, Prüfsumme, Healthcheck und Rollback. Die konkrete Updateentscheidung
ist vor der Aktivierung anhand der lokalen Installationsdokumentation zu
prüfen.

## Prüfsummen und Assets

Der Releasevertrag erwartet genau diese drei Assets:

- `zrzavy-energy-monitor-4.5.1.tar.gz`
- `zrzavy-energy-monitor-4.5.1.tar.gz.sha256`
- `release-manifest.json`

Die veröffentlichte SHA-256-Prüfsumme muss gegen das Archiv neu berechnet und
geprüft werden.

## Bekannte Einschränkungen

- Ein Tasmota-Hardwaretest ist ohne bereitgestellten realen Host nicht als
  bestanden zu melden; er bleibt in diesem Lauf übersprungen.
- Dieses Patch-Release enthält keine Hardware-Kompatibilitätszusage.
- Die lokale HTTP-API hat weiterhin keine Zugriffsschutzmechanismen.
