-- Synthetic SolarInspector 4.1.3 schema delta.
-- Apply after legacy_v3.sql to obtain the characterized 48-column schema.
-- Contains no production, device-identity, network, or personal data.

ALTER TABLE samples ADD COLUMN shelly_solar_power_w REAL;
ALTER TABLE samples ADD COLUMN solakon_pv_power_w REAL;
ALTER TABLE samples ADD COLUMN solakon_ac_power_w REAL;
ALTER TABLE samples ADD COLUMN solakon_battery_power_w REAL;
ALTER TABLE samples ADD COLUMN solakon_battery_soc_pct REAL;
ALTER TABLE samples ADD COLUMN solakon_load_power_w REAL;
ALTER TABLE samples ADD COLUMN solakon_meter_power_w REAL;
ALTER TABLE samples ADD COLUMN solakon_temperature_c REAL;
ALTER TABLE samples ADD COLUMN solakon_daily_pv_kwh REAL;
ALTER TABLE samples ADD COLUMN solakon_total_pv_kwh REAL;
ALTER TABLE samples ADD COLUMN solakon_pv1_power_w REAL;
ALTER TABLE samples ADD COLUMN solakon_pv2_power_w REAL;
ALTER TABLE samples ADD COLUMN solakon_pv3_power_w REAL;
ALTER TABLE samples ADD COLUMN solakon_pv4_power_w REAL;
ALTER TABLE samples ADD COLUMN solar_difference_w REAL;
ALTER TABLE samples ADD COLUMN solar_difference_pct REAL;
ALTER TABLE samples ADD COLUMN solar_source TEXT;
ALTER TABLE samples ADD COLUMN grid_source TEXT;
ALTER TABLE samples ADD COLUMN solakon_model TEXT;
ALTER TABLE samples ADD COLUMN solakon_serial TEXT;
ALTER TABLE samples ADD COLUMN solakon_status TEXT;
ALTER TABLE samples ADD COLUMN solakon_ok INTEGER NOT NULL DEFAULT 0;
ALTER TABLE samples ADD COLUMN shelly_solar_wh REAL NOT NULL DEFAULT 0;
ALTER TABLE samples ADD COLUMN solakon_pv_wh REAL NOT NULL DEFAULT 0;
ALTER TABLE samples ADD COLUMN solakon_ac_wh REAL NOT NULL DEFAULT 0;
ALTER TABLE samples ADD COLUMN battery_charge_wh REAL NOT NULL DEFAULT 0;
ALTER TABLE samples ADD COLUMN battery_discharge_wh REAL NOT NULL DEFAULT 0;
