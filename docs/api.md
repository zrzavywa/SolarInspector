# API-Referenz

## Status

Die REST-Endpunkte der 4.1-Reihe dienen primär der SolarInspector-Weboberfläche und dem lokalen Betrieb. Sie sind noch nicht als dauerhaft stabile öffentliche Integrations-API garantiert.

- Basis-URL lokal: `http://127.0.0.1:8787`
- Format: JSON
- Transport im Heimnetz: HTTP
- Empfohlener Zugriff: nur lokal oder über VPN

## Healthcheck

### `GET /api/health`

Prüft, ob der Anwendungskern erfolgreich gestartet wurde.

```bash
curl --fail http://127.0.0.1:8787/api/health
```

Beispiel:

```json
{
  "status": "ok",
  "version": "4.1.3",
  "database": "ok",
  "web": "ok"
}
```

Externe Messgeräte sind nicht zwingend Teil des harten Rollback-Kriteriums.

## Systemversion

### `GET /api/system/version`

Liefert Produkt- und Versionsinformationen.

```bash
curl --silent \
  http://127.0.0.1:8787/api/system/version
```

Beispiel:

```json
{
  "product": "SolarInspector",
  "version": "4.1.3"
}
```

Je nach Version können zusätzliche Schema- oder Buildinformationen enthalten sein.

## Laufzeitstatus

### `GET /api/status`

Liefert den aktuellen Zustand der Datenerfassung und verfügbare Livewerte.

```bash
curl --silent http://127.0.0.1:8787/api/status
```

Das konkrete Antwortschema kann sich innerhalb der 4.x-Reihe ändern.

## Updateprüfung

### `GET /api/update/check`

Prüft das konfigurierte öffentliche GitHub-Repository auf eine neuere stabile Version.

```bash
curl --silent \
  http://127.0.0.1:8787/api/update/check
```

Typische Antwortfelder:

```json
{
  "installed_version": "4.1.2",
  "available_version": "4.1.3",
  "update_available": true,
  "channel": "stable",
  "published_at": "2026-07-20T00:00:00Z",
  "release_notes": "Release notes",
  "asset_name": "SolarInspector-4.1.3.tar.gz"
}
```

## Update herunterladen

### `POST /api/update/download`

Lädt das zuvor geprüfte Release und kontrolliert Integrität und Manifest.

```bash
curl --request POST \
  http://127.0.0.1:8787/api/update/download
```

Die genaue Anforderung kann Schutzmechanismen wie Session- oder CSRF-Prüfungen enthalten. Für Automatisierung nicht ungeprüft von Browserbeispielen ableiten.

## Update-Status

### `GET /api/update/status`

Liefert den persistenten Fortschritt des letzten oder laufenden Updatevorgangs.

```bash
curl --silent \
  http://127.0.0.1:8787/api/update/status
```

Beispiel:

```json
{
  "state": "completed",
  "progress": 100,
  "message": "Update erfolgreich installiert.",
  "installed_version": "4.1.3",
  "available_version": "4.1.3",
  "updated_at": "2026-07-20T10:00:00+00:00"
}
```

## Update installieren

### `POST /api/update/install`

Erstellt eine kontrollierte lokale Installationsanforderung für das bereits geprüfte und heruntergeladene Release.

```bash
curl --request POST \
  http://127.0.0.1:8787/api/update/install
```

Der eigentliche privilegierte Vorgang wird nicht im Webprozess ausgeführt, sondern durch den getrennten systemd-Updater.

## Fehlerantworten

Typische HTTP-Kategorien:

| Status | Bedeutung |
|---:|---|
| `200` | Anfrage erfolgreich |
| `400` | ungültige oder unvollständige Anforderung |
| `403` | Sicherheitsprüfung oder Berechtigung fehlgeschlagen |
| `404` | Endpunkt oder Release nicht vorhanden |
| `409` | Zustand erlaubt die Aktion nicht |
| `500` | interner Fehler |
| `503` | Dienst oder Abhängigkeit vorübergehend nicht verfügbar |

Beispiel:

```json
{
  "status": "error",
  "message": "Kein geprüftes Release zur Installation vorhanden."
}
```

## Stabilitätsregeln für Integrationen

Externe Integrationen sollten:

- unbekannte JSON-Felder tolerieren,
- fehlende optionale Felder behandeln,
- Einheiten nicht erraten,
- Zeitstempel mit Zeitzone verwenden,
- Timeouts und Wiederholungen begrenzen,
- die API nicht häufiger als das Messintervall abfragen,
- Versionswechsel vor produktiver Nutzung testen.

## Sicherheit

Die Update-Endpunkte dürfen nicht über eine ungeschützte Internetverbindung erreichbar sein. Eine spätere stabile öffentliche API sollte Authentifizierung, Autorisierung, CSRF-Schutz, klare Versionierung und ein dokumentiertes Schema erhalten.
