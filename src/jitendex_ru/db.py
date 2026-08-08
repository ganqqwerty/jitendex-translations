from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA_VERSION = 2

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS schema_meta(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS source_snapshot(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('jitendex','kaishi')),
  version TEXT NOT NULL, url TEXT NOT NULL, sha256 TEXT NOT NULL, local_path TEXT NOT NULL,
  extractor_version TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(kind, sha256)
);
CREATE TABLE IF NOT EXISTS kaishi_note(
  id INTEGER PRIMARY KEY, snapshot_id INTEGER NOT NULL REFERENCES source_snapshot(id),
  note_id INTEGER NOT NULL, word TEXT NOT NULL, reading TEXT NOT NULL, meaning_en TEXT NOT NULL,
  sentence_ja TEXT NOT NULL, sentence_en TEXT NOT NULL, source_sha256 TEXT NOT NULL,
  UNIQUE(snapshot_id, note_id)
);
CREATE TABLE IF NOT EXISTS article(
  id INTEGER PRIMARY KEY, snapshot_id INTEGER NOT NULL REFERENCES source_snapshot(id),
  bank_number INTEGER NOT NULL, entry_ordinal INTEGER NOT NULL, expression TEXT NOT NULL,
  reading TEXT NOT NULL, sequence INTEGER NOT NULL, raw_json TEXT NOT NULL, source_sha256 TEXT NOT NULL,
  structural_fingerprint TEXT, selected INTEGER NOT NULL DEFAULT 0 CHECK(selected IN (0,1)),
  UNIQUE(snapshot_id, bank_number, entry_ordinal)
);
CREATE INDEX IF NOT EXISTS article_lookup ON article(expression, reading);
CREATE INDEX IF NOT EXISTS article_sequence ON article(sequence);
CREATE TABLE IF NOT EXISTS selection_candidate(
  id INTEGER PRIMARY KEY, note_id INTEGER NOT NULL REFERENCES kaishi_note(id),
  article_id INTEGER NOT NULL REFERENCES article(id), sequence INTEGER NOT NULL,
  match_kind TEXT NOT NULL, evidence_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(note_id, article_id)
);
CREATE TABLE IF NOT EXISTS selection_decision(
  id INTEGER PRIMARY KEY, note_id INTEGER NOT NULL REFERENCES kaishi_note(id), sequence INTEGER,
  decision TEXT NOT NULL CHECK(decision IN ('included','excluded','unresolved')),
  actor TEXT NOT NULL, reason TEXT NOT NULL, review_status TEXT NOT NULL CHECK(review_status IN ('pending','accepted','rejected')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(note_id, sequence, actor)
);
CREATE TABLE IF NOT EXISTS run(
  id INTEGER PRIMARY KEY,
  jitendex_snapshot_id INTEGER NOT NULL REFERENCES source_snapshot(id),
  kaishi_snapshot_id INTEGER NOT NULL REFERENCES source_snapshot(id),
  selection_sha256 TEXT NOT NULL, extractor_version TEXT NOT NULL,
  prompt_sha256 TEXT NOT NULL, review_prompt_sha256 TEXT NOT NULL, terminology_sha256 TEXT NOT NULL, limits_json TEXT NOT NULL,
  pipeline_version TEXT NOT NULL DEFAULT 'scalar-v1',
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(jitendex_snapshot_id, kaishi_snapshot_id, selection_sha256, extractor_version, prompt_sha256, review_prompt_sha256, terminology_sha256, limits_json)
);
CREATE TABLE IF NOT EXISTS translation_unit(
  id TEXT PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES run(id), article_id INTEGER NOT NULL REFERENCES article(id),
  json_pointer TEXT NOT NULL, role TEXT NOT NULL, source_text TEXT NOT NULL, source_sha256 TEXT NOT NULL,
  protected_tokens_json TEXT NOT NULL DEFAULT '[]', byte_count INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'ready',
  UNIQUE(run_id, article_id, json_pointer)
);
CREATE TABLE IF NOT EXISTS run_article(
  run_id INTEGER NOT NULL REFERENCES run(id), article_id INTEGER NOT NULL REFERENCES article(id),
  structural_fingerprint TEXT NOT NULL, PRIMARY KEY(run_id, article_id)
);
CREATE TABLE IF NOT EXISTS batch(
  id TEXT PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES run(id), kind TEXT NOT NULL DEFAULT 'translation',
  manifest_sha256 TEXT NOT NULL UNIQUE, serialized_bytes INTEGER NOT NULL, article_count INTEGER NOT NULL,
  unit_count INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'ready', lease_token TEXT, lease_expires_at TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0, manifest_path TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS batch_item(
  batch_id TEXT NOT NULL REFERENCES batch(id), unit_id TEXT NOT NULL REFERENCES translation_unit(id), ordinal INTEGER NOT NULL,
  PRIMARY KEY(batch_id, unit_id), UNIQUE(batch_id, ordinal)
);
CREATE INDEX IF NOT EXISTS batch_item_unit ON batch_item(unit_id);
CREATE TABLE IF NOT EXISTS attempt(
  id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batch(id), worker_id TEXT NOT NULL, model TEXT NOT NULL,
  prompt_sha256 TEXT NOT NULL, lease_token TEXT, request_path TEXT NOT NULL, response_path TEXT,
  outcome TEXT NOT NULL DEFAULT 'claimed', error_json TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT
);
CREATE TABLE IF NOT EXISTS translation(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES run(id), unit_id TEXT NOT NULL REFERENCES translation_unit(id),
  attempt_id TEXT NOT NULL REFERENCES attempt(id), target_text TEXT NOT NULL, confidence TEXT NOT NULL,
  review_reason TEXT, target_sha256 TEXT NOT NULL, accepted INTEGER NOT NULL DEFAULT 0 CHECK(accepted IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(unit_id, attempt_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_accepted_translation ON translation(run_id, unit_id) WHERE accepted=1;
CREATE TABLE IF NOT EXISTS review(
  id INTEGER PRIMARY KEY, translation_id INTEGER NOT NULL REFERENCES translation(id), attempt_id TEXT REFERENCES attempt(id),
  decision TEXT NOT NULL CHECK(decision IN ('accept','replace','needs_adjudication')),
  replacement_target TEXT, reason TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(translation_id, attempt_id)
);
CREATE TABLE IF NOT EXISTS validation_issue(
  id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES run(id), unit_id TEXT REFERENCES translation_unit(id),
  attempt_id TEXT REFERENCES attempt(id), validator TEXT NOT NULL, severity TEXT NOT NULL,
  code TEXT NOT NULL, details_json TEXT NOT NULL, resolved_at TEXT, waiver_reason TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_event(
  id INTEGER PRIMARY KEY, event_type TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS export(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES run(id), output_path TEXT NOT NULL,
  manifest_sha256 TEXT NOT NULL, zip_sha256 TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS export_file(
  export_id INTEGER NOT NULL REFERENCES export(id), path TEXT NOT NULL, sha256 TEXT NOT NULL, byte_count INTEGER NOT NULL,
  PRIMARY KEY(export_id, path)
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def initialize(path: Path) -> None:
    with connect(path) as connection:
        connection.executescript(SCHEMA)
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(run)")}
        if "pipeline_version" not in columns:
            connection.execute(
                "ALTER TABLE run ADD COLUMN pipeline_version TEXT NOT NULL DEFAULT 'scalar-v1'"
            )
        connection.execute(
            """INSERT OR IGNORE INTO run_article(run_id,article_id,structural_fingerprint)
            SELECT DISTINCT tu.run_id,tu.article_id,a.structural_fingerprint
            FROM translation_unit tu JOIN article a ON a.id=tu.article_id
            WHERE a.structural_fingerprint IS NOT NULL"""
        )
        connection.execute("INSERT OR IGNORE INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))


@contextmanager
def transaction(connection: sqlite3.Connection, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()


def audit(connection: sqlite3.Connection, event: str, entity: str, entity_id: object, details: object = None) -> None:
    connection.execute(
        "INSERT INTO audit_event(event_type,entity_type,entity_id,details_json) VALUES (?,?,?,?)",
        (event, entity, str(entity_id), json.dumps(details or {}, ensure_ascii=False, sort_keys=True)),
    )
