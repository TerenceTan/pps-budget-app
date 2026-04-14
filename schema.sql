-- schema.sql — PostgreSQL schema for APAC Marketing Budget Tracker
-- Run: psql $DATABASE_URL -f schema.sql

CREATE TABLE IF NOT EXISTS budgets (
    id          TEXT PRIMARY KEY,
    country     TEXT NOT NULL,
    quarter     TEXT NOT NULL,
    total_budget NUMERIC(14,2) DEFAULT 0,
    updated_at  TEXT,
    UNIQUE(country, quarter)
);
CREATE INDEX IF NOT EXISTS idx_budgets_cq ON budgets(country, quarter);

CREATE TABLE IF NOT EXISTS channels (
    id          TEXT PRIMARY KEY,
    country     TEXT NOT NULL,
    quarter     TEXT NOT NULL,
    name        TEXT NOT NULL,
    budget      NUMERIC(14,2) DEFAULT 0,
    sort_order  INTEGER DEFAULT 0,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_channels_cq ON channels(country, quarter);

CREATE TABLE IF NOT EXISTS activities (
    id          TEXT PRIMARY KEY,
    channel_id  TEXT NOT NULL,
    country     TEXT NOT NULL,
    quarter     TEXT NOT NULL,
    name        TEXT NOT NULL,
    sort_order  INTEGER DEFAULT 0,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_activities_cq ON activities(country, quarter);
CREATE INDEX IF NOT EXISTS idx_activities_ch ON activities(channel_id);

CREATE TABLE IF NOT EXISTS entries (
    id              TEXT PRIMARY KEY,
    country         TEXT NOT NULL,
    quarter         TEXT NOT NULL,
    month           TEXT,
    channel_id      TEXT,
    channel_name    TEXT,
    activity_id     TEXT,
    activity_name   TEXT,
    bu              TEXT,
    finance_cat     TEXT,
    marketing_cat   TEXT,
    description     TEXT,
    planned         NUMERIC(14,2) DEFAULT 0,
    confirmed       NUMERIC(14,2) DEFAULT 0,
    actual          NUMERIC(14,2) DEFAULT 0,
    jira            TEXT DEFAULT '',
    vendor          TEXT DEFAULT '',
    notes           TEXT DEFAULT '',
    approved        TEXT DEFAULT 'False',
    invoice_names   TEXT DEFAULT '[]',
    invoice_data    TEXT DEFAULT '[]',
    entered_by      TEXT DEFAULT '',
    created_at      TEXT,
    updated_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_entries_cq ON entries(country, quarter);
CREATE INDEX IF NOT EXISTS idx_entries_ch ON entries(channel_id);

CREATE TABLE IF NOT EXISTS channel_mapping (
    channel_keyword TEXT PRIMARY KEY,
    bu              TEXT,
    finance_cat     TEXT,
    marketing_cat   TEXT,
    updated_by      TEXT,
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS vendors (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    country     TEXT DEFAULT 'GLOBAL',
    added_by    TEXT,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS users (
    username        TEXT PRIMARY KEY,
    password_hash   TEXT NOT NULL,
    display_name    TEXT,
    role            TEXT DEFAULT 'country',
    markets         TEXT DEFAULT 'ALL',
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    value       TEXT NOT NULL,
    sort_order  INTEGER DEFAULT 0,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_categories_type ON categories(type);
