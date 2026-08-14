SET timezone = 'UTC';
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

ALTER TABLE schema_meta ALTER COLUMN applied_at DROP DEFAULT;
ALTER TABLE schema_meta ALTER COLUMN applied_at TYPE TIMESTAMPTZ USING applied_at::timestamptz;
ALTER TABLE schema_meta ALTER COLUMN applied_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE source_snapshot ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE source_snapshot ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at::timestamptz;
ALTER TABLE source_snapshot ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE selection_decision ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE selection_decision ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at::timestamptz;
ALTER TABLE selection_decision ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE run ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE run ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at::timestamptz;
ALTER TABLE run ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE batch ALTER COLUMN lease_expires_at TYPE TIMESTAMPTZ USING lease_expires_at::timestamptz;
ALTER TABLE batch ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE batch ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at::timestamptz;
ALTER TABLE batch ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE attempt ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE attempt ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at::timestamptz;
ALTER TABLE attempt ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE attempt ALTER COLUMN completed_at TYPE TIMESTAMPTZ USING completed_at::timestamptz;
ALTER TABLE translation ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE translation ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at::timestamptz;
ALTER TABLE translation ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE review ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE review ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at::timestamptz;
ALTER TABLE review ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE validation_issue ALTER COLUMN resolved_at TYPE TIMESTAMPTZ USING resolved_at::timestamptz;
ALTER TABLE validation_issue ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE validation_issue ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at::timestamptz;
ALTER TABLE validation_issue ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE audit_event ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE audit_event ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at::timestamptz;
ALTER TABLE audit_event ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE export ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE export ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at::timestamptz;
ALTER TABLE export ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE attempt_cost_report ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE attempt_cost_report ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at::timestamptz;
ALTER TABLE attempt_cost_report ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE jitendex_tag ALTER COLUMN translated_at TYPE TIMESTAMPTZ USING translated_at::timestamptz;
ALTER TABLE jitendex_tag ALTER COLUMN approved_at TYPE TIMESTAMPTZ USING approved_at::timestamptz;
ALTER TABLE jitendex_tag_translation_history ALTER COLUMN translated_at TYPE TIMESTAMPTZ USING translated_at::timestamptz;
ALTER TABLE jitendex_tag_translation_history ALTER COLUMN archived_at DROP DEFAULT;
ALTER TABLE jitendex_tag_translation_history ALTER COLUMN archived_at TYPE TIMESTAMPTZ USING archived_at::timestamptz;
ALTER TABLE jitendex_tag_translation_history ALTER COLUMN archived_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE translation_canonicalization_history ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE translation_canonicalization_history ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at::timestamptz;
ALTER TABLE translation_canonicalization_history ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS benchmark_marker(
  stage_id TEXT PRIMARY KEY,
  corpus_sha256 TEXT NOT NULL CHECK(length(corpus_sha256) = 64),
  run_id BIGINT NOT NULL UNIQUE REFERENCES run(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS batch_claim_order ON batch(run_id,kind,state,created_at,id);
CREATE INDEX IF NOT EXISTS attempt_claim_state ON attempt(outcome,batch_id,lease_token);
CREATE INDEX IF NOT EXISTS translation_progress ON translation(run_id,unit_id,accepted);
CREATE INDEX IF NOT EXISTS validation_blocking ON validation_issue(run_id,severity,resolved_at);
