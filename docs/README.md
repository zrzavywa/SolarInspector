# SolarInspector-Dokumentation

Diese Dokumentation beschreibt Installation, Konfiguration und Betrieb von SolarInspector. Sie orientiert sich am Produktstand **4.1.3**.

## Für Betreiber

1. [Installation auf Raspberry Pi](installation-raspberry-pi.md)
2. [Konfiguration](configuration.md)
3. [Unterstützte Geräte](devices.md)
4. [SHRDZM-Netzstromzähler](shrdzm-grid-meter.md)
5. [Betrieb, Backup und Wiederherstellung](operation.md)
6. [Updates und Rollback](updates.md)
7. [Troubleshooting](troubleshooting.md)
8. [Sicherheit](security.md)

## Für Entwicklung und Integration

- [Architektur](architecture.md)
- [Entwicklungsstandards](development.md)
- [API-Referenz](api.md)
- [Mitwirken](../CONTRIBUTING.md)
- [Änderungshistorie](../CHANGELOG.md)
- [Markenhinweise](../TRADEMARKS.md)

## Dokumentationsprinzipien

- **Aktueller Stand:** Aussagen zur 4.1-Reihe beschreiben implementierte Funktionen.
- **Zielbild:** Die geplante 5.0-Architektur wird ausdrücklich als Planung markiert.
- **Lokal zuerst:** SolarInspector ist für einen lokalen, selbst betriebenen Einsatz ausgelegt.
- **Keine geheimen Daten:** Beispiele verwenden ausschließlich Platzhalter.
- **Sichere Updates:** Konfiguration und Messdaten werden unabhängig vom Programmrelease behandelt.

## Begriffe

| Begriff | Bedeutung |
|---|---|
| Solakon ONE | Wechselrichter beziehungsweise Energiesystem, das lokal über Modbus TCP gelesen wird |
| Solaranlagenmessung | Leistung oder Energie der PV-Anlage |
| Hausanschlussmessung | Netzbezug oder Einspeisung am Übergabepunkt |
| Collector | Komponente zur zyklischen Abfrage und Normalisierung von Messwerten |
| Release | veröffentlichte, versionierte SolarInspector-Ausgabe |
| Updater | separater Prozess für Prüfung, Backup, Aktivierung und Rollback |
| Healthcheck | lokale Prüfung, ob die aktivierte Anwendung erfolgreich gestartet wurde |

## Markenhinweise

SolarInspector ist ein unabhängiges Projekt. **Raspberry Pi is a trademark of Raspberry Pi Ltd.** Weitere Hinweise zu Solakon, Shelly, Raspberry Pi und anderen Produktbezeichnungen stehen in [TRADEMARKS.md](../TRADEMARKS.md).
