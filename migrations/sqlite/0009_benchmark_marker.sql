CREATE TABLE IF NOT EXISTS benchmark_marker(
  stage_id TEXT PRIMARY KEY,
  corpus_sha256 TEXT NOT NULL,
  run_id INTEGER NOT NULL UNIQUE REFERENCES run(id),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK(length(corpus_sha256) = 64)
);
CREATE INDEX IF NOT EXISTS batch_claim_order ON batch(run_id,kind,state,created_at,id);
CREATE INDEX IF NOT EXISTS attempt_claim_state ON attempt(outcome,batch_id,lease_token);
CREATE INDEX IF NOT EXISTS translation_progress ON translation(run_id,unit_id,accepted);
CREATE INDEX IF NOT EXISTS validation_blocking ON validation_issue(run_id,severity,resolved_at);

