-- Synthetic Phase 08 schema delta; apply after phase_06_07.sql.

CREATE TABLE validation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_seen_epoch REAL NOT NULL,
    first_seen_local TEXT NOT NULL,
    last_seen_epoch REAL NOT NULL,
    last_seen_local TEXT NOT NULL,
    source_id TEXT NOT NULL,
    role TEXT NOT NULL,
    metric TEXT NOT NULL,
    unit TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    finding_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    decision TEXT NOT NULL,
    quality TEXT NOT NULL,
    reason TEXT NOT NULL,
    raw_value_json TEXT NOT NULL DEFAULT 'null',
    accepted_value REAL,
    details_json TEXT NOT NULL DEFAULT '{}',
    occurrence_count INTEGER NOT NULL DEFAULT 1
        CHECK (occurrence_count >= 1),
    minimum_value REAL,
    maximum_value REAL,
    first_sample_id INTEGER,
    last_sample_id INTEGER
);
CREATE INDEX idx_validation_events_last_seen
ON validation_events(last_seen_epoch DESC);

CREATE INDEX idx_validation_events_identity
ON validation_events(
    source_id,
    role,
    metric,
    rule_id,
    finding_code,
    decision,
    last_seen_epoch
);

INSERT INTO validation_events (
    id,
    first_seen_epoch,
    first_seen_local,
    last_seen_epoch,
    last_seen_local,
    source_id,
    role,
    metric,
    unit,
    rule_id,
    finding_code,
    severity,
    decision,
    quality,
    reason,
    raw_value_json,
    accepted_value,
    details_json,
    occurrence_count,
    minimum_value,
    maximum_value,
    first_sample_id,
    last_sample_id
)
VALUES (
    1,
    1714557600.0,
    '2024-05-01T12:00:00+02:00',
    1714557600.0,
    '2024-05-01T12:00:00+02:00',
    'house_meter',
    'grid_meter',
    'grid_power',
    'W',
    'VAL-RANGE-001',
    'synthetic_warning',
    'warning',
    'accept_with_warning',
    'suspect',
    'Synthetic threshold warning.',
    '250.0',
    250.0,
    '{"warning_max":200.0}',
    1,
    250.0,
    250.0,
    1,
    1
);
