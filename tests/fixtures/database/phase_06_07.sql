-- Synthetic Phase 06/07 schema delta; apply after phase_05.sql.

CREATE TABLE grid_meter_samples (
    sample_id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    adapter TEXT NOT NULL,
    active_source_id TEXT,
    device_status TEXT NOT NULL,
    quality TEXT,
    error_text TEXT,
    measured_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    grid_power_w REAL,
    grid_power_quality TEXT,
    grid_import_power_w REAL,
    grid_import_power_quality TEXT,
    grid_export_power_w REAL,
    grid_export_power_quality TEXT,
    grid_import_total_kwh REAL,
    grid_import_total_quality TEXT,
    grid_export_total_kwh REAL,
    grid_export_total_quality TEXT,
    FOREIGN KEY (sample_id) REFERENCES samples(id) ON DELETE CASCADE
);
CREATE INDEX idx_grid_meter_samples_source_sample
ON grid_meter_samples(source_id, sample_id);

INSERT INTO grid_meter_samples (
    sample_id,
    source_id,
    source_name,
    adapter,
    active_source_id,
    device_status,
    quality,
    measured_at,
    received_at,
    grid_power_w,
    grid_power_quality,
    grid_import_power_w,
    grid_import_power_quality,
    grid_export_power_w,
    grid_export_power_quality,
    grid_import_total_kwh,
    grid_import_total_quality,
    grid_export_total_kwh,
    grid_export_total_quality
)
VALUES (
    1,
    'grid_meter_primary',
    'Synthetic official meter',
    'tasmota',
    'grid_meter_primary',
    'online',
    'validated',
    '2024-05-01T12:00:00+02:00',
    '2024-05-01T12:00:00+02:00',
    250.0,
    'validated',
    250.0,
    'validated',
    0.0,
    'validated',
    1000.0,
    'validated',
    25.0,
    'validated'
);
