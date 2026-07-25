# Validation event persistence

SolarInspector persists only actionable validation findings: warnings and
rejections. Successful informational checks are not written as events.

## Aggregation

Repeated findings are aggregated by source, role, metric, rule, finding code,
and measurement-level decision.

The default aggregation window is 300 seconds. A repeated finding updates the
existing row with its latest occurrence, count, latest safe details, and
minimum/maximum observed numeric value.

A change from warning to rejection is stored separately because the
measurement-level decision changed.

## Retention

The default retention period is 90 days. Cleanup is rate-limited to once per
hour and occurs during validation-event persistence. The store also exposes an
explicit pruning operation for maintenance and deterministic tests.

These defaults can be overridden below `validation.persistence`:

```json
{
  "dedup_window_seconds": 300,
  "retention_days": 90,
  "prune_interval_seconds": 3600,
  "max_reason_chars": 512,
  "max_details_chars": 4096,
  "max_raw_value_chars": 512
}
```

## Data safety

The table stores normalized identifiers, decision, quality, unit, accepted
value, a bounded raw scalar, bounded rule details, occurrence count, and first
and last occurrence.

It does not store complete device responses. Complex raw values are replaced
by a type marker. URL-like strings, credentials, tokens, passwords, payloads,
and other sensitive detail fields are redacted before serialization.

A rejected event stores `NULL` as `accepted_value`.

## Collector behavior

The aggregate sample is persisted before its validation events. Therefore an
event-persistence failure does not discard the measurement sample. The
collector reports a sanitized persistence warning and continues running.
