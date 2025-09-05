-- ==========================================
-- Online DB bootstrap (PostgreSQL)
-- ==========================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- --- Users (come nel tuo file) ---
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    role TEXT NOT NULL CHECK (role IN ('admin', 'moderator', 'technician', 'seg'))
);

-- Admin di default (idempotente)
INSERT INTO users (username, hashed_password, first_name, last_name, role)
SELECT 'admin', '$argon2d$v=19$m=16,t=2,p=1$anUycEd2c3NqREQwZ05YdA$D1hwGTwOTQGISAV+qukA8g', 'ELSON', 'META', 'admin'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username='admin');

-- --- 1) Customers ---
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    uuid TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    address TEXT,
    phone TEXT,
    email TEXT,
    last_modified TIMESTAMPTZ NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    is_synced BOOLEAN NOT NULL DEFAULT TRUE
);

-- --- 2) Destinations (dipende da customers) ---
CREATE TABLE IF NOT EXISTS destinations (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(255) NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    address TEXT,
    last_modified TIMESTAMPTZ NOT NULL,
    is_synced BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

-- --- 3) Devices (dipende da destinations) ---
CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(255) NOT NULL UNIQUE,
    destination_id INTEGER REFERENCES destinations(id) ON DELETE SET NULL,
    serial_number VARCHAR(255),                    -- FACOLTATIVO
    description TEXT,
    manufacturer VARCHAR(255),
    model VARCHAR(255),
    department VARCHAR(255),
    applied_parts_json TEXT,
    customer_inventory VARCHAR(255),
    ams_inventory VARCHAR(255),
    verification_interval INTEGER,
    default_profile_key TEXT,
    next_verification_date DATE,
    status TEXT NOT NULL DEFAULT 'active',         -- Nuovo campo stato
    last_modified TIMESTAMPTZ NOT NULL,
    is_synced BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

-- --- 4) Verifications (dipende da devices) ---
CREATE TABLE IF NOT EXISTS verifications (
    id SERIAL PRIMARY KEY,
    uuid TEXT NOT NULL UNIQUE,
    device_id INTEGER REFERENCES devices(id) ON DELETE CASCADE,
    verification_date DATE NOT NULL,
    profile_name TEXT NOT NULL,
    results_json TEXT NOT NULL,
    overall_status TEXT NOT NULL,
    visual_inspection_json TEXT,
    mti_instrument TEXT,
    mti_serial TEXT,
    mti_version TEXT,
    mti_cal_date TEXT,
    technician_name TEXT,
    technician_username TEXT,
    last_modified TIMESTAMPTZ NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    is_synced BOOLEAN NOT NULL DEFAULT TRUE
);

-- --- 5) MTI instruments (indipendente) ---
CREATE TABLE IF NOT EXISTS mti_instruments (
    id SERIAL PRIMARY KEY,
    uuid TEXT NOT NULL UNIQUE,
    instrument_name TEXT NOT NULL,
    serial_number TEXT NOT NULL,
    fw_version TEXT,
    calibration_date TEXT,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    last_modified TIMESTAMPTZ NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    is_synced BOOLEAN NOT NULL DEFAULT TRUE
);

-- --- 6) Profiles & Profile Tests ---
CREATE TABLE IF NOT EXISTS profiles (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(255) NOT NULL UNIQUE,
    profile_key VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    last_modified TIMESTAMPTZ NOT NULL,
    is_synced BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS profile_tests (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(255) NOT NULL UNIQUE,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    parameter VARCHAR(255),
    limits_json TEXT,
    is_applied_part_test BOOLEAN NOT NULL DEFAULT FALSE,
    last_modified TIMESTAMPTZ NOT NULL,
    is_synced BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

-- --- 7) Signatures ---
CREATE TABLE IF NOT EXISTS signatures (
    username VARCHAR(255) PRIMARY KEY NOT NULL,
    signature_data BYTEA,
    last_modified TIMESTAMPTZ NOT NULL,
    is_synced BOOLEAN NOT NULL DEFAULT FALSE
);

-- --- Indici utili (UUID + FK + vincolo serial unico quando valorizzato) ---
CREATE INDEX IF NOT EXISTS idx_customers_uuid ON customers(uuid);
CREATE INDEX IF NOT EXISTS idx_destinations_uuid ON destinations(uuid);
CREATE INDEX IF NOT EXISTS idx_devices_uuid ON devices(uuid);
CREATE INDEX IF NOT EXISTS idx_verifications_uuid ON verifications(uuid);
CREATE INDEX IF NOT EXISTS idx_mti_instruments_uuid ON mti_instruments(uuid);
CREATE INDEX IF NOT EXISTS idx_profiles_uuid ON profiles(uuid);
CREATE INDEX IF NOT EXISTS idx_profile_tests_uuid ON profile_tests(uuid);

-- FK indexes
CREATE INDEX IF NOT EXISTS idx_destinations_customer_id ON destinations(customer_id);
CREATE INDEX IF NOT EXISTS idx_devices_destination_id ON devices(destination_id);
CREATE INDEX IF NOT EXISTS idx_verifications_device_id ON verifications(device_id);
CREATE INDEX IF NOT EXISTS idx_profile_tests_profile_id ON profile_tests(profile_id);

-- Unicità del seriale SOLO quando valorizzato
CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_serial_unique
    ON devices(serial_number)
    WHERE serial_number IS NOT NULL AND serial_number <> '';
