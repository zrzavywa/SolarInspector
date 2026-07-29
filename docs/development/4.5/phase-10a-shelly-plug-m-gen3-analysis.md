# Phase 10A – Analyse

Der Shelly Plug M Gen3 wird als optionale, lokale Anlagen-AC-Messquelle hinter
dem Solakon-AC-Ausgang unterstützt. Der Adapter liest ausschließlich
`Switch.GetStatus?id=<component_id>` und normalisiert `apower` als
`PLANT_AC_POWER`. Die bestehende `solakon_meter`-Quelle und Solakon ONE bleiben
kompatibel; `plant_meter` ist standardmäßig deaktiviert.

`apower = 0` ist ein gültiger Messwert. Fehlende, boolesche, nicht numerische,
NaN- oder unendliche Werte sind nicht verfügbar und werden nicht als Null
interpretiert. `direction_factor` bleibt konfigurierbar; ein technischer
Standard für Rückspeisung ist ohne reale Hardwareevidence nicht bestätigt.

Die 3.000-W-Gerätegrenze wird nicht als Anlagen-Plausibilitätsgrenze verwendet.
Die bestehende Validierungs- und Quellenwahlpipeline bleibt maßgeblich.
