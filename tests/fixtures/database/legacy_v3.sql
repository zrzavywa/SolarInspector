-- Synthetic pre-4.1 legacy fixture ("v3-style").
-- Source: characterized 21-column samples DDL in Database.initialize().
-- Contains no production, device-identity, network, or personal data.

PRAGMA foreign_keys = ON;

CREATE TABLE samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_epoch REAL NOT NULL,
    ts_local TEXT NOT NULL,
    grid_power_w REAL,
    solar_power_w REAL,
    house_power_w REAL,
    grid_import_w REAL,
    feed_in_w REAL,
    self_consumption_w REAL,
    voltage_v REAL,
    current_a REAL,
    power_factor REAL,
    frequency_hz REAL,
    grid_import_wh REAL NOT NULL DEFAULT 0,
    feed_in_wh REAL NOT NULL DEFAULT 0,
    solar_wh REAL NOT NULL DEFAULT 0,
    house_wh REAL NOT NULL DEFAULT 0,
    self_consumption_wh REAL NOT NULL DEFAULT 0,
    house_ok INTEGER NOT NULL DEFAULT 0,
    solar_ok INTEGER NOT NULL DEFAULT 0,
    error_text TEXT
);

CREATE INDEX idx_samples_ts_epoch ON samples(ts_epoch);

INSERT INTO samples (
    id,
    ts_epoch,
    ts_local,
    grid_power_w,
    solar_power_w,
    house_power_w,
    grid_import_w,
    feed_in_w,
    self_consumption_w,
    voltage_v,
    current_a,
    power_factor,
    frequency_hz,
    grid_import_wh,
    feed_in_wh,
    solar_wh,
    house_wh,
    self_consumption_wh,
    house_ok,
    solar_ok,
    error_text
)
VALUES
    (
        1,
        1714557600.0,
        '2024-05-01T12:00:00+02:00',
        250.0,
        750.0,
        1000.0,
        250.0,
        0.0,
        750.0,
        230.0,
        4.35,
        0.98,
        50.0,
        0.35,
        0.0,
        1.04,
        1.39,
        1.04,
        1,
        1,
        NULL
    ),
    (
        2,
        1714557605.0,
        '2024-05-01T12:00:05+02:00',
        -100.0,
        600.0,
        500.0,
        0.0,
        100.0,
        500.0,
        NULL,
        NULL,
        NULL,
        NULL,
        0.0,
        0.14,
        0.83,
        0.69,
        0.69,
        0,
        1,
        'Synthetic partial meter sample'
    );
