# Shelly test fixtures

Die JSON-Dateien in diesem Verzeichnis sind synthetische Testdaten.

Sie wurden aus den in SolarInspector 4.1.3 ausgewerteten Shelly-Feldern und
den bekannten Antwortformaten der unterstützten Gerätetypen abgeleitet. Sie
stammen nicht direkt aus einem realen Haushalt oder einer realen Installation.

Abgedeckte Gerätetypen:

- Shelly PM Mini Gen 3 über `PM1.GetStatus`
- Shelly 3EM Gen 1 über `/status`
- Shelly Pro 3EM über `EM.GetStatus`

Die Fixtures enthalten:

- normale Leistungswerte
- Nullleistung
- negative Leistung beziehungsweise negative Phasenleistung
- unvollständige Antworten
- ungültige Phasenwerte
- zusätzliche, vom aktuellen Parser nicht ausgewertete Felder

Es sind keine Passwörter, Tokens, Seriennummern, personenbezogenen Daten oder
realen IP-Adressen enthalten.

Einheiten:

- Leistung: Watt
- Spannung: Volt
- Strom: Ampere
- Frequenz: Hertz
- Energiezähler: Wattstunden
