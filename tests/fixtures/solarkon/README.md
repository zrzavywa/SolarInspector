# Solakon ONE test fixtures

Die JSON-Dateien in diesem Verzeichnis sind synthetische Registerdaten.

Sie wurden aus den von SolarInspector 4.1.3 gelesenen Registern und
Skalierungsregeln abgeleitet. Sie stammen nicht aus einer realen Anlage.

Die Fixtures bilden folgende Zustände ab:

- Normalbetrieb
- Batterieladung
- Batterieentladung
- Nullerzeugung beziehungsweise Standby
- partieller Kommunikationsausfall

Jede Datei enthält:

- `synthetic`: Kennzeichnung als synthetische Testdaten
- `description`: Beschreibung des simulierten Betriebszustands
- `fail_blocks`: Startadressen von Registerblöcken, die einen Modbus-Fehler
  simulieren
- `registers`: rohe 16-Bit-Registerwerte mit dezimaler Adresse

Vorzeichen und Skalierung werden nicht in den Fixtures vorweggenommen.
Die JSON-Dateien enthalten die Rohwerte, wie sie über Modbus gelesen würden.

Es sind keine echten Seriennummern, IP-Adressen, Passwörter, Tokens oder
personenbezogenen Daten enthalten.
