# Unterstützte Geräte und Messquellen

## Übersicht

| Gerät beziehungsweise Quelle | Protokoll | Typische Rolle |
|---|---|---|
| Solakon ONE | Modbus TCP | PV-, AC-, Batterie-, Last- und Gerätewerte |
| Shelly PM Mini Gen 3 | lokale RPC-API | unabhängige AC-Messung der Solakon-Anlage |
| Shelly 3EM Gen 1 | lokale HTTP-API | dreiphasige Hausanschlussmessung |
| Shelly Pro 3EM | lokale RPC-API | dreiphasige Hausanschlussmessung |
| SHRDZM-Kundenschnittstellen-Modul | lokale REST API | offizielle Referenz für Netzbezug und Einspeisung |
| Simulation | intern | Funktionstest ohne reale Hardware |

## Solakon ONE

### Voraussetzungen

- Solakon ONE und Raspberry Pi befinden sich in erreichbaren lokalen Netzen.
- Modbus TCP ist am Gerät aktiviert.
- TCP-Port `502` ist nicht durch Firewall oder Client-Isolation blockiert.
- Geräte-ID ist üblicherweise `1`.
- Die lokale IP-Adresse bleibt möglichst stabil.

### Zugriffssicherheit

SolarInspector verwendet den Solakon-Zugriff ausschließlich zum Lesen von Mess- und Gerätewerten. Es werden keine Lade-, Entlade- oder Betriebsparameter geschrieben.

### Mögliche Werte

Je nach Geräteversion und Firmware können unter anderem verfügbar sein:

- Modell und Seriennummer
- PV-Eingangsleistung
- AC-Wirkleistung
- Batterieladezustand
- Batterieleistung
- Hauslast
- Temperatur
- Energiezähler

Nicht jeder Wert ist in jeder Konfiguration vorhanden. Fehlende externe Gerätewerte dürfen den Kernservice und den lokalen Healthcheck nicht zum Absturz bringen.

### Verbindungstest

```bash
nc -vz <SOLAKON-IP> 502
```

Alternativ:

```bash
timeout 5 bash -c '</dev/tcp/<SOLAKON-IP>/502'
```

Eine erfolgreiche TCP-Verbindung bestätigt nur die Erreichbarkeit, nicht die korrekte Registerbelegung.

## Shelly PM Mini Gen 3

SolarInspector verwendet die lokale Gen3-RPC-Schnittstelle, typischerweise:

```text
/rpc/PM1.GetStatus?id=0
```

Typische Rolle:

- unabhängige Messung der AC-Ausgangsleistung,
- Vergleich mit dem von Solakon ONE gemeldeten AC-Wert,
- Erkennen größerer Messabweichungen.

Prüfung im Browser oder mit `curl`:

```bash
curl --fail "http://<SHELLY-IP>/rpc/PM1.GetStatus?id=0"
```

## Shelly 3EM Gen 1

SolarInspector verwendet die lokale Gen1-Statusschnittstelle:

```text
/status
```

Prüfung:

```bash
curl --fail "http://<SHELLY-IP>/status"
```

Für die Hausanschlussmessung werden die Leistungen der Phasen zusammengeführt. Die Richtung muss anhand eines realen Bezugs- und Einspeisefalls geprüft werden.

## Shelly Pro 3EM

SolarInspector verwendet die lokale RPC-Schnittstelle des EM-Komponents, typischerweise:

```text
/rpc/EM.GetStatus?id=0
```

Prüfung:

```bash
curl --fail "http://<SHELLY-IP>/rpc/EM.GetStatus?id=0"
```

## SHRDZM-Kundenschnittstellen-Modul

SolarInspector liest das Modul lokal und ausschließlich lesend über:

```text
/getLastData
```

Unterstützt werden direkte OBIS-Schlüssel, numerische JSON-Werte und
numerische Strings. Der Adapter bevorzugt getrennt gemeldeten Bezug und
Einspeisung und berechnet daraus die saldierte Netzleistung. `16.7.0`
bleibt als konfigurierbarer Nettowert beziehungsweise Fallback nutzbar.

Typische Standardwerte sind `1.7.0`, `2.7.0`, `1.8.0`, `2.8.0` sowie
optionale Spannungs- und Stromwerte der drei Phasen. Welche Felder real
verfügbar sind, hängt vom offiziellen Zähler und der Freischaltung der
Kundenschnittstelle ab.

Einrichtung, Authentifizierung, Mapping und Hardwarecheck stehen in
[SHRDZM als offizieller Netzstromzähler](shrdzm-grid-meter.md).

## Lokale Authentifizierung

Wenn am Shelly eine Authentifizierung aktiviert ist, müssen Benutzername und Kennwort in der lokalen SolarInspector-Konfiguration hinterlegt werden.

Empfehlungen:

- eigenes Gerätekennwort verwenden,
- Kennwort nicht in Git oder Issues veröffentlichen,
- Konfigurationsdatei mit restriktiven Dateirechten schützen,
- keine unverschlüsselte Weiterleitung der Shelly-API über das Internet einrichten.

## Netzwerkanforderungen

| Verbindung | Standard |
|---|---|
| Browser → SolarInspector | TCP `8787` |
| SolarInspector → Solakon ONE | TCP `502` |
| SolarInspector → Shelly | TCP `80`, abhängig von Geräteoptionen |
| SolarInspector → SHRDZM | TCP `80` beziehungsweise konfigurierter HTTPS-Port |
| SolarInspector → GitHub | HTTPS `443` für Releaseprüfung und Download |

## Messabweichungen richtig einordnen

Abweichungen zwischen Solakon ONE, Shelly und Netzbetreiberzähler können entstehen durch:

- Vergleich unterschiedlicher Messpunkte,
- PV-Eingangsleistung versus AC-Ausgangsleistung,
- unterschiedliche Zeitintervalle und Aggregationen,
- Eigenverbrauch des Wechselrichters oder Speichers,
- Phasen- oder Vorzeichenfehler,
- Rundung und Messgenauigkeit,
- Zeitversatz zwischen Datenquellen,
- fehlende oder unvollständige Messwerte.

Vor einer Kalibrierung immer sicherstellen, dass dieselbe physikalische Größe im selben Zeitraum verglichen wird.

## Neue Geräte integrieren

Eine neue Geräteintegration sollte mindestens dokumentieren:

- Hersteller und Modell,
- API- oder Protokollversion,
- lokale Endpunkte,
- Authentifizierung,
- Einheiten und Vorzeichen,
- Fehler- und Timeoutverhalten,
- Beispielantwort ohne sensible Daten,
- Testfälle,
- Verhalten bei Geräteausfall.
