# Phase 10A – Hardware-Evidence

Die reale Hardwarecharakterisierung wird in diesem Durchlauf ausdrücklich
übersprungen, weil sie von der verwendeten Maschine aus nicht möglich ist.
Es liegen daher keine realen Hardwarecaptures vor. Vorzeichen,
Rückspeisungsverhalten, `ret_aenergy`, stabiles Nullwertverhalten und Recovery
nach Neustart/Netzunterbrechung bleiben ungeprüft.

Vor Releasefreigabe sind `Shelly.GetDeviceInfo`, `Shelly.GetStatus` und
`Switch.GetStatus?id=0` über mindestens 30 Minuten unter Nacht-, Einspeise- und
`output=false`-Bedingungen zu vergleichen. Rohcaptures dürfen nicht committed
werden; nur anonymisierte Minimalfixtures sind zulässig.
