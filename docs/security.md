# Sicherheitsmodell

## Einsatzgrenze

SolarInspector ist für ein vertrauenswürdiges lokales Netzwerk vorgesehen. Die Anwendung ist kein fertig gehärteter, öffentlich erreichbarer Internetdienst.

Nicht empfohlen:

- direkte Portweiterleitung aus dem Internet auf Port `8787`,
- öffentliche Bereitstellung ohne TLS und Authentifizierung,
- gemeinsame Verwendung von Administrator- oder Gerätekennwörtern,
- Veröffentlichung vollständiger Konfigurationen oder Diagnosearchive.

Für externen Zugriff sollte ein VPN verwendet werden.

## Sicherheitsziele

- keine Steuerung der Solakon-Anlage,
- geringstmögliche Rechte des Webprozesses,
- klare Trennung zwischen Anwendung und Updateinstallation,
- reproduzierbare Release-Artefakte,
- Integritätsprüfung vor Installation,
- Erhalt von Konfiguration und Messdaten,
- automatisches Rollback bei fehlgeschlagenem Start,
- keine Geheimnisse in Releases oder Logs.

## Solakon-Zugriff

SolarInspector nutzt ausschließlich lesende Modbus-Zugriffe. Nicht vorgesehen sind:

- Änderung der Ladeleistung,
- Änderung der Betriebsart,
- Änderung von SoC-Grenzen,
- Änderung von Netz- oder Einspeiseparametern,
- Schreiben beliebiger Register.

## Berechtigungsmodell

### Webprozess

Soll als eigener unprivilegierter Benutzer laufen und nur erhalten:

- Leserechte auf Programmdateien,
- Leserechte auf Konfiguration,
- Schreibrechte auf Datenbank und notwendige Laufzeitdateien,
- Netzwerkzugriff auf konfigurierte lokale Geräte und GitHub.

### Updater

Der Updater benötigt erhöhte Rechte für:

- versionierte Releases unter `/opt`,
- Aktivierung des `current`-Symlinks,
- Service-Neustart,
- Backup und Wiederherstellung.

Diese Rechte werden in einem festen systemd-OneShot-Service gekapselt. Der Browser darf keine freien Shell-Parameter, Service-Namen oder Dateipfade übergeben.

## Release-Vertrauen

Ein Release sollte mindestens enthalten:

- eindeutige Versionsnummer,
- versioniertes Archiv,
- SHA-256-Prüfsumme,
- maschinenlesbares Manifest,
- Release Notes,
- erfolgreiche automatisierte Tests.

Vor Aktivierung werden Archiv und Metadaten geprüft. Ein fehlerhafter Hash muss das Update stoppen.

## Schutz gegen Archivangriffe

Archive dürfen keine Dateien außerhalb des vorgesehenen Release-Verzeichnisses schreiben.

Zu prüfen sind insbesondere:

- absolute Pfade,
- `..`-Pfadsegmente,
- symbolische Links auf externe Ziele,
- verschachtelte oder zyklische Links,
- unerwartete Gerätedateien,
- übermäßig große oder komprimierte Inhalte.

## Konfiguration und Geheimnisse

Empfohlene Rechte:

```bash
sudo chown solarinspector:solarinspector \
  /etc/solarinspector/config.json

sudo chmod 600 /etc/solarinspector/config.json
```

Kennwörter:

- nicht in Git speichern,
- nicht in Screenshots zeigen,
- in Diagnoseexporten maskieren,
- nicht als Kommandozeilenargument übergeben,
- regelmäßig ändern, falls ein Export versehentlich veröffentlicht wurde.

## Netzwerksicherheit

- feste Geräteadressen per DHCP-Reservierung,
- IoT-Geräte möglichst in einem kontrollierten VLAN,
- nur notwendige Verbindungen zwischen VLANs erlauben,
- Port `502` nur lokal freigeben,
- eine künftige MQTT-Anbindung mit Authentifizierung und bei Netzgrenzen mit TLS betreiben,
- Raspberry Pi regelmäßig aktualisieren,
- unnötige Dienste deaktivieren.

## Backup-Sicherheit

Backups enthalten möglicherweise:

- lokale IP-Adressen,
- Gerätekennwörter,
- Standortinformationen,
- vollständige Energiedaten.

Daher:

- Backups verschlüsselt oder physisch geschützt speichern,
- Zugriffe beschränken,
- Aufbewahrungsfrist festlegen,
- alte Backups sicher löschen,
- Wiederherstellung regelmäßig testen.

## Protokollierung

Logs sollen enthalten:

- Komponente,
- Zeitstempel,
- Schweregrad,
- technische Fehlerursache,
- Updateversion und Ergebnis.

Logs sollen nicht enthalten:

- Kennwörter,
- Session-Secrets,
- Tokens,
- vollständige Authentifizierungsheader,
- unnötige personenbezogene Daten.

## Melden einer Sicherheitslücke

Sicherheitsrelevante Probleme nicht mit vollständigen Exploitdetails und realen Geheimnissen in einem öffentlichen Issue veröffentlichen. Zunächst nur Auswirkung, betroffene Version und sichere Reproduktionsbedingungen melden und einen vertraulichen Kontaktweg mit dem Repository-Betreiber abstimmen.
