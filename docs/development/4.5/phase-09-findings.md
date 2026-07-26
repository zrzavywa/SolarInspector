# Phase 09 – Findings und Folgethemen

## Technische Schulden

| ID | Finding | Folge |
|---|---|---|
| BAL-001 | Grid Meter und Anlagenzähler können unterschiedliche Aktualisierungsintervalle besitzen. | Der Zeitabgleich verhindert unmarkierte Berechnung; weitergehende Synchronisierung frühestens in Phase 12/13 prüfen. |
| BAL-002 | Kurzzeitmittelwerte liegen nur im Arbeitsspeicher. | Ein Neustart verwirft das Auswahlfenster; persistente Fenster optional in Phase 13 prüfen. |
| BAL-003 | Weitere Erzeugungsanlagen neben Solakon sind nicht als eigene Quellenrolle modelliert. | Erweiterbares Mehranlagenmodell nach Version 4.5 entwerfen. |
| BAL-004 | Batterieverluste sind ohne vollständige DC-seitige Messung nicht belegbar. | Keine Wirkungsgrad- oder Verlustwerte aus Differenzen erfinden. |
| BAL-005 | Die Legacy-Netzquelle Solakon ONE besitzt historisch keine durchgehend eindeutige Messstellenrolle. | Nur bei expliziter Legacy-Priorität zulassen und später deprecaten. |
| BAL-006 | Historische Legacy-Bilanzwerte werden nicht rückwirkend neu berechnet. | Optionales Reprocessing erst mit versionierter Berechnungssemantik erwägen. |

## Messstellenunterschiede

- Der offizielle Grid Meter misst am öffentlichen Netzanschlusspunkt.
- Ein Shelly 3EM/Pro 3EM ist nur mit expliziter Position `grid_fallback` als
  Netzfallback zulässig. Eine Unterverteilung ist nicht gleichwertig.
- Der Shelly PM Mini am Anlagenausgang misst Anlagen-AC-Leistung.
- Solakon-PV-Leistung ist ein DC-/Systemwert und ersetzt keine
  Anlagen-AC-Messung.
- Gerätezeit, Empfangszeit und Collector-Zeit können voneinander abweichen.
  Alter und Quellenversatz werden deshalb getrennt geprüft.

Die reale Verdrahtung und korrekte Messposition können durch Software und
Fixtures nicht abschließend bewiesen werden.

## Nicht unterstützte Sonderfälle

- mehrere unabhängige PV- oder Erzeugungsanlagen;
- automatische Kalibrierung oder Vorzeichenkorrektur;
- Rekonstruktion fehlender PV- oder Batteriewerte;
- vollständige Batterie-Verlustrechnung;
- rückwirkende Neuberechnung bestehender historischer Samples;
- dauerhafte Weiterverwendung des letzten gültigen Werts über das Alterslimit;
- destructive oder irreversible Datenbankmigrationen.

## Vorschläge für spätere Phasen

1. Mehranlagen- und weitere Erzeugerrollen fachlich modellieren.
2. Historische Bilanzabfragen mit versionierter Rechenregel entwerfen.
3. Optional persistente Zeitfenster für Mittelwertbildung untersuchen.
4. Legacy-Netzquellen mit uneindeutiger Messposition deprecaten.
5. Hardware-Abnahmeleitfaden für Messposition, Vorzeichen und Gerätezeiten
   ergänzen.
