import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS raw_events (
    event_id INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    workflow_id TEXT,
    campaign_id TEXT,
    payload_json TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_event_id INTEGER NOT NULL DEFAULT -1,
    last_chunk INTEGER NOT NULL DEFAULT -1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_metrics (
    workflow_id TEXT NOT NULL,
    bucket_start TEXT NOT NULL,
    dials INTEGER NOT NULL DEFAULT 0,
    connected INTEGER NOT NULL DEFAULT 0,
    engaged INTEGER NOT NULL DEFAULT 0,
    hallucination_flags INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workflow_id, bucket_start)
);

CREATE TABLE IF NOT EXISTS variant_metrics (
    workflow_id TEXT NOT NULL,
    variant_key TEXT NOT NULL,
    bucket_start TEXT NOT NULL,
    dials INTEGER NOT NULL DEFAULT 0,
    connected INTEGER NOT NULL DEFAULT 0,
    engaged INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workflow_id, variant_key, bucket_start)
);

CREATE TABLE IF NOT EXISTS caller_id_metrics (
    workflow_id TEXT NOT NULL,
    caller_id TEXT NOT NULL,
    bucket_start TEXT NOT NULL,
    dials INTEGER NOT NULL DEFAULT 0,
    connected INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workflow_id, caller_id, bucket_start)
);

CREATE TABLE IF NOT EXISTS cohort_metrics (
    workflow_id TEXT NOT NULL,
    cohort_id TEXT NOT NULL,
    bucket_start TEXT NOT NULL,
    dials INTEGER NOT NULL DEFAULT 0,
    connected INTEGER NOT NULL DEFAULT 0,
    engaged INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workflow_id, cohort_id, bucket_start)
);

CREATE TABLE IF NOT EXISTS audit_events (
    audit_id TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    workflow_id TEXT,
    subject_type TEXT,
    subject_id TEXT,
    reason TEXT,
    evidence_json TEXT
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)

    return connection