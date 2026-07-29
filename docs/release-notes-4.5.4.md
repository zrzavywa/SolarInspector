# Zrzavy Energy Monitor 4.5.4 – Phase 10B

## SHRDZM als offizieller Netzstromzähler

ZEM 4.5.4 ergänzt und härtet die lokale SHRDZM-HTTP-Anbindung über
`GET /getLastData`.

### Enthalten

- getrennte Übernahme von Netzbezug (`1.7.0`) und Einspeisung (`2.7.0`),
- Nettoleistung nach der bestehenden Konvention `Import - Export`,
- bestätigte Import-, Nullpunkt- und Einspeisefälle mit UTC-Messzeit,
- Wh-Normalisierung der bestätigten Energiezähler `1.8.0` und `2.8.0`,
- optionale Phasenspannungen und Phasenströme,
- Behandlung von HTTP-200-Fehlerobjekten, ungültigem JSON, Timeouts und
  Teilantworten,
- Secret-Redaction in Diagnose- und Testartefakten.

### Nicht enthalten

- Modbus TCP oder MQTT für SHRDZM; dies ist für eine spätere 4.6-Phase
  vorgemerkt.
- Produktive Interpretation von `13.7.0`; der Wert ist für die Anlage nicht
  relevant.
- Änderungen an bestehenden Tasmota-, Shelly- oder sonstigen Gerätepfaden.

### Validierungshinweis

Die automatisierte lokale Prüfung ist erfolgreich. Der bestehende lokale
Modbus-Socket-Test kann in eingeschränkten Umgebungen wegen fehlender
TCP-Bind-Berechtigung nicht ausgeführt werden. Hardwarebetrieb und die ersten
Echtbetriebswochen bleiben manuelle Betriebsnachweise.
