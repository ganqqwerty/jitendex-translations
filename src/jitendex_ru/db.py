from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Mapping


SCHEMA_VERSION = 7

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
CREATE TABLE IF NOT EXISTS jitendex_tag(
  id INTEGER PRIMARY KEY,
  snapshot_id INTEGER NOT NULL REFERENCES source_snapshot(id),
  source_kind TEXT NOT NULL CHECK(source_kind IN ('embedded_tooltip','tag_bank')),
  source_key TEXT NOT NULL,
  code TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL,
  label_en TEXT NOT NULL,
  description_en TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  occurrence_count INTEGER NOT NULL CHECK(occurrence_count >= 0),
  source_metadata_json TEXT NOT NULL DEFAULT '{}',
  label_ru TEXT,
  description_ru TEXT,
  confidence TEXT CHECK(confidence IS NULL OR confidence IN ('high','medium','low')),
  review_reason TEXT,
  translation_model TEXT,
  reasoning_effort TEXT,
  prompt_sha256 TEXT,
  translation_source TEXT,
  translation_source_sha256 TEXT,
  translation_source_path TEXT,
  approved_at TEXT,
  translated_at TEXT,
  UNIQUE(snapshot_id,source_kind,source_key)
);
CREATE INDEX IF NOT EXISTS jitendex_tag_category ON jitendex_tag(snapshot_id,category,code);
CREATE TABLE IF NOT EXISTS jitendex_tag_translation_history(
  id INTEGER PRIMARY KEY,
  tag_id INTEGER NOT NULL REFERENCES jitendex_tag(id),
  label_ru TEXT,
  description_ru TEXT,
  confidence TEXT,
  review_reason TEXT,
  translation_model TEXT,
  reasoning_effort TEXT,
  prompt_sha256 TEXT,
  translation_source TEXT,
  translation_source_sha256 TEXT,
  translation_source_path TEXT,
  translated_at TEXT,
  archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  replacement_source_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS frequency_source(
  source TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, rank_limit INTEGER NOT NULL CHECK(rank_limit > 0),
  local_path TEXT NOT NULL, title TEXT, revision TEXT, parser_version TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS frequency_term(
  source TEXT NOT NULL, source_sha256 TEXT NOT NULL, rank INTEGER NOT NULL,
  term TEXT NOT NULL, matched INTEGER NOT NULL DEFAULT 0 CHECK(matched IN (0,1)),
  PRIMARY KEY(source, source_sha256, term)
);
CREATE INDEX IF NOT EXISTS frequency_term_rank ON frequency_term(source,source_sha256,rank);
CREATE TABLE IF NOT EXISTS frequency_article(
  source TEXT NOT NULL, source_sha256 TEXT NOT NULL, rank INTEGER NOT NULL, term TEXT NOT NULL,
  article_id INTEGER NOT NULL REFERENCES article(id),
  match_kind TEXT NOT NULL CHECK(match_kind IN ('expression','reading')),
  PRIMARY KEY(source, source_sha256, term, article_id),
  FOREIGN KEY(source, source_sha256, term) REFERENCES frequency_term(source, source_sha256, term)
);
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
  completed_at TEXT, effective_model_id TEXT, reasoning_effort TEXT,
  transport TEXT CHECK(transport IS NULL OR transport IN ('responses-sync','batch-api','codex-agent')),
  api_request_id TEXT, api_custom_id TEXT, api_job_id TEXT,
  input_tokens INTEGER CHECK(input_tokens IS NULL OR input_tokens >= 0),
  cached_input_tokens INTEGER CHECK(cached_input_tokens IS NULL OR cached_input_tokens >= 0),
  output_tokens INTEGER CHECK(output_tokens IS NULL OR output_tokens >= 0),
  total_tokens INTEGER CHECK(total_tokens IS NULL OR total_tokens >= 0),
  finish_reason TEXT, status_reason TEXT,
  latency_ms INTEGER CHECK(latency_ms IS NULL OR latency_ms >= 0)
);
CREATE TABLE IF NOT EXISTS attempt_cost_report(
  id INTEGER PRIMARY KEY, attempt_id TEXT NOT NULL UNIQUE REFERENCES attempt(id),
  price_snapshot_date TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'USD',
  input_price_per_million TEXT NOT NULL, cached_input_price_per_million TEXT NOT NULL,
  output_price_per_million TEXT NOT NULL, price_multiplier TEXT NOT NULL DEFAULT '1',
  input_tokens INTEGER NOT NULL, cached_input_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL, computed_cost TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER IF NOT EXISTS attempt_cost_report_no_update
BEFORE UPDATE ON attempt_cost_report BEGIN
  SELECT RAISE(ABORT, 'attempt cost reports are immutable');
END;
CREATE TRIGGER IF NOT EXISTS attempt_cost_report_no_delete
BEFORE DELETE ON attempt_cost_report BEGIN
  SELECT RAISE(ABORT, 'attempt cost reports are immutable');
END;
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
        frequency_article_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(frequency_article)")
        }
        if "term" not in frequency_article_columns:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.executescript(
                """
                BEGIN IMMEDIATE;
                DROP INDEX IF EXISTS frequency_term_rank;
                ALTER TABLE frequency_article RENAME TO frequency_article_v6;
                ALTER TABLE frequency_term RENAME TO frequency_term_v6;
                CREATE TABLE frequency_term(
                  source TEXT NOT NULL, source_sha256 TEXT NOT NULL, rank INTEGER NOT NULL,
                  term TEXT NOT NULL, matched INTEGER NOT NULL DEFAULT 0 CHECK(matched IN (0,1)),
                  PRIMARY KEY(source, source_sha256, term)
                );
                CREATE INDEX frequency_term_rank ON frequency_term(source,source_sha256,rank);
                CREATE TABLE frequency_article(
                  source TEXT NOT NULL, source_sha256 TEXT NOT NULL, rank INTEGER NOT NULL, term TEXT NOT NULL,
                  article_id INTEGER NOT NULL REFERENCES article(id),
                  match_kind TEXT NOT NULL CHECK(match_kind IN ('expression','reading')),
                  PRIMARY KEY(source, source_sha256, term, article_id),
                  FOREIGN KEY(source, source_sha256, term)
                    REFERENCES frequency_term(source, source_sha256, term)
                );
                INSERT INTO frequency_term(source,source_sha256,rank,term,matched)
                SELECT source,source_sha256,rank,term,matched FROM frequency_term_v6;
                INSERT INTO frequency_article(source,source_sha256,rank,term,article_id,match_kind)
                SELECT fa.source,fa.source_sha256,fa.rank,ft.term,fa.article_id,fa.match_kind
                FROM frequency_article_v6 fa
                JOIN frequency_term_v6 ft
                  ON ft.source=fa.source AND ft.source_sha256=fa.source_sha256 AND ft.rank=fa.rank;
                DROP TABLE frequency_article_v6;
                DROP TABLE frequency_term_v6;
                COMMIT;
                """
            )
            connection.execute("PRAGMA foreign_keys = ON")
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"frequency table migration produced foreign-key violations: {violations}")
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(run)")}
        if "pipeline_version" not in columns:
            connection.execute(
                "ALTER TABLE run ADD COLUMN pipeline_version TEXT NOT NULL DEFAULT 'scalar-v1'"
            )
        attempt_columns = {row["name"] for row in connection.execute("PRAGMA table_info(attempt)")}
        audit_columns = {
            "effective_model_id": "TEXT",
            "reasoning_effort": "TEXT",
            "transport": "TEXT CHECK(transport IS NULL OR transport IN ('responses-sync','batch-api','codex-agent'))",
            "api_request_id": "TEXT",
            "api_custom_id": "TEXT",
            "api_job_id": "TEXT",
            "input_tokens": "INTEGER CHECK(input_tokens IS NULL OR input_tokens >= 0)",
            "cached_input_tokens": "INTEGER CHECK(cached_input_tokens IS NULL OR cached_input_tokens >= 0)",
            "output_tokens": "INTEGER CHECK(output_tokens IS NULL OR output_tokens >= 0)",
            "total_tokens": "INTEGER CHECK(total_tokens IS NULL OR total_tokens >= 0)",
            "finish_reason": "TEXT",
            "status_reason": "TEXT",
            "latency_ms": "INTEGER CHECK(latency_ms IS NULL OR latency_ms >= 0)",
        }
        for name, declaration in audit_columns.items():
            if name not in attempt_columns:
                connection.execute(f"ALTER TABLE attempt ADD COLUMN {name} {declaration}")
        tag_columns = {row["name"] for row in connection.execute("PRAGMA table_info(jitendex_tag)")}
        tag_provenance_columns = {
            "translation_source": "TEXT",
            "translation_source_sha256": "TEXT",
            "translation_source_path": "TEXT",
            "approved_at": "TEXT",
        }
        for name, declaration in tag_provenance_columns.items():
            if name not in tag_columns:
                connection.execute(f"ALTER TABLE jitendex_tag ADD COLUMN {name} {declaration}")
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


def record_attempt_usage(
    connection: sqlite3.Connection,
    attempt_id: str,
    *,
    effective_model_id: str,
    reasoning_effort: str,
    transport: str,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    api_request_id: str | None = None,
    api_custom_id: str | None = None,
    api_job_id: str | None = None,
    finish_reason: str | None = None,
    status_reason: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Persist the effective request identity and raw API usage for an attempt."""
    if transport not in {"responses-sync", "batch-api", "codex-agent"}:
        raise ValueError(f"unsupported attempt transport: {transport}")
    counts = (input_tokens, cached_input_tokens, output_tokens, total_tokens)
    if any(value < 0 for value in counts):
        raise ValueError("token counts cannot be negative")
    if cached_input_tokens > input_tokens:
        raise ValueError("cached input tokens cannot exceed input tokens")
    if total_tokens != input_tokens + output_tokens:
        raise ValueError("total tokens must equal input plus output tokens")
    if latency_ms is not None and latency_ms < 0:
        raise ValueError("latency cannot be negative")
    cursor = connection.execute(
        """UPDATE attempt SET effective_model_id=?,reasoning_effort=?,transport=?,
        api_request_id=?,api_custom_id=?,api_job_id=?,input_tokens=?,cached_input_tokens=?,
        output_tokens=?,total_tokens=?,finish_reason=?,status_reason=?,latency_ms=? WHERE id=?""",
        (
            effective_model_id, reasoning_effort, transport, api_request_id, api_custom_id,
            api_job_id, input_tokens, cached_input_tokens, output_tokens, total_tokens,
            finish_reason, status_reason, latency_ms, attempt_id,
        ),
    )
    if cursor.rowcount != 1:
        raise ValueError(f"unknown attempt: {attempt_id}")
    audit(connection, "record_usage", "attempt", attempt_id, {
        "effective_model_id": effective_model_id,
        "reasoning_effort": reasoning_effort,
        "transport": transport,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    })


def record_attempt_cost(
    connection: sqlite3.Connection,
    attempt_id: str,
    *,
    price_snapshot_date: str,
    input_price_per_million: Decimal | str,
    cached_input_price_per_million: Decimal | str,
    output_price_per_million: Decimal | str,
    price_multiplier: Decimal | str = "1",
) -> Decimal:
    """Create the immutable price snapshot and exact computed cost for an attempt."""
    usage = connection.execute(
        """SELECT input_tokens,cached_input_tokens,output_tokens FROM attempt WHERE id=?""",
        (attempt_id,),
    ).fetchone()
    if usage is None:
        raise ValueError(f"unknown attempt: {attempt_id}")
    if any(usage[name] is None for name in ("input_tokens", "cached_input_tokens", "output_tokens")):
        raise ValueError("attempt usage must be recorded before cost")
    prices: Mapping[str, Decimal] = {
        "input": Decimal(input_price_per_million),
        "cached": Decimal(cached_input_price_per_million),
        "output": Decimal(output_price_per_million),
        "multiplier": Decimal(price_multiplier),
    }
    if any(value < 0 for value in prices.values()):
        raise ValueError("prices and price multiplier cannot be negative")
    uncached_tokens = usage["input_tokens"] - usage["cached_input_tokens"]
    cost = (
        Decimal(uncached_tokens) * prices["input"]
        + Decimal(usage["cached_input_tokens"]) * prices["cached"]
        + Decimal(usage["output_tokens"]) * prices["output"]
    ) * prices["multiplier"] / Decimal(1_000_000)
    connection.execute(
        """INSERT INTO attempt_cost_report(
        attempt_id,price_snapshot_date,input_price_per_million,cached_input_price_per_million,
        output_price_per_million,price_multiplier,input_tokens,cached_input_tokens,
        output_tokens,computed_cost) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            attempt_id, price_snapshot_date, str(prices["input"]), str(prices["cached"]),
            str(prices["output"]), str(prices["multiplier"]), usage["input_tokens"],
            usage["cached_input_tokens"], usage["output_tokens"], str(cost),
        ),
    )
    audit(connection, "record_cost", "attempt", attempt_id, {
        "price_snapshot_date": price_snapshot_date,
        "computed_cost": str(cost),
        "currency": "USD",
    })
    return cost
