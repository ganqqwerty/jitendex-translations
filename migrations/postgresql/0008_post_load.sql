SET maintenance_work_mem = '1GB';

ALTER TABLE schema_meta ADD CONSTRAINT schema_meta_pkey PRIMARY KEY (version);
ALTER TABLE source_snapshot ADD CONSTRAINT source_snapshot_pkey PRIMARY KEY (id);
ALTER TABLE source_snapshot ADD CONSTRAINT source_snapshot_kind_sha256_key UNIQUE (kind, sha256);
ALTER TABLE kaishi_note ADD CONSTRAINT kaishi_note_pkey PRIMARY KEY (id);
ALTER TABLE kaishi_note ADD CONSTRAINT kaishi_note_snapshot_note_key UNIQUE (snapshot_id, note_id);
ALTER TABLE article ADD CONSTRAINT article_pkey PRIMARY KEY (id);
ALTER TABLE article ADD CONSTRAINT article_snapshot_bank_ordinal_key UNIQUE (snapshot_id, bank_number, entry_ordinal);
ALTER TABLE selection_candidate ADD CONSTRAINT selection_candidate_pkey PRIMARY KEY (id);
ALTER TABLE selection_candidate ADD CONSTRAINT selection_candidate_note_article_key UNIQUE (note_id, article_id);
ALTER TABLE selection_decision ADD CONSTRAINT selection_decision_pkey PRIMARY KEY (id);
ALTER TABLE selection_decision ADD CONSTRAINT selection_decision_note_sequence_actor_key UNIQUE (note_id, sequence, actor);
ALTER TABLE run ADD CONSTRAINT run_pkey PRIMARY KEY (id);
ALTER TABLE run ADD CONSTRAINT run_identity_key UNIQUE (
  jitendex_snapshot_id, kaishi_snapshot_id, selection_sha256, extractor_version,
  prompt_sha256, review_prompt_sha256, terminology_sha256, limits_json
);
ALTER TABLE translation_unit ADD CONSTRAINT translation_unit_pkey PRIMARY KEY (id);
ALTER TABLE translation_unit ADD CONSTRAINT translation_unit_run_article_pointer_key UNIQUE (run_id, article_id, json_pointer);
ALTER TABLE batch ADD CONSTRAINT batch_pkey PRIMARY KEY (id);
ALTER TABLE batch ADD CONSTRAINT batch_manifest_sha256_key UNIQUE (manifest_sha256);
ALTER TABLE batch_item ADD CONSTRAINT batch_item_pkey PRIMARY KEY (batch_id, unit_id);
ALTER TABLE batch_item ADD CONSTRAINT batch_item_batch_ordinal_key UNIQUE (batch_id, ordinal);
ALTER TABLE attempt ADD CONSTRAINT attempt_pkey PRIMARY KEY (id);
ALTER TABLE translation ADD CONSTRAINT translation_pkey PRIMARY KEY (id);
ALTER TABLE translation ADD CONSTRAINT translation_unit_attempt_key UNIQUE (unit_id, attempt_id);
ALTER TABLE review ADD CONSTRAINT review_pkey PRIMARY KEY (id);
ALTER TABLE review ADD CONSTRAINT review_translation_attempt_key UNIQUE (translation_id, attempt_id);
ALTER TABLE validation_issue ADD CONSTRAINT validation_issue_pkey PRIMARY KEY (id);
ALTER TABLE audit_event ADD CONSTRAINT audit_event_pkey PRIMARY KEY (id);
ALTER TABLE export ADD CONSTRAINT export_pkey PRIMARY KEY (id);
ALTER TABLE export_file ADD CONSTRAINT export_file_pkey PRIMARY KEY (export_id, path);
ALTER TABLE run_article ADD CONSTRAINT run_article_pkey PRIMARY KEY (run_id, article_id);
ALTER TABLE attempt_cost_report ADD CONSTRAINT attempt_cost_report_pkey PRIMARY KEY (id);
ALTER TABLE attempt_cost_report ADD CONSTRAINT attempt_cost_report_attempt_key UNIQUE (attempt_id);
ALTER TABLE jitendex_tag ADD CONSTRAINT jitendex_tag_pkey PRIMARY KEY (id);
ALTER TABLE jitendex_tag ADD CONSTRAINT jitendex_tag_snapshot_kind_key UNIQUE (snapshot_id, source_kind, source_key);
ALTER TABLE jitendex_tag_translation_history ADD CONSTRAINT jitendex_tag_translation_history_pkey PRIMARY KEY (id);
ALTER TABLE frequency_source ADD CONSTRAINT frequency_source_pkey PRIMARY KEY (source);
ALTER TABLE frequency_term ADD CONSTRAINT frequency_term_pkey PRIMARY KEY (source, source_sha256, term);
ALTER TABLE frequency_article ADD CONSTRAINT frequency_article_pkey PRIMARY KEY (source, source_sha256, term, article_id);
ALTER TABLE translation_canonicalization_history ADD CONSTRAINT translation_canonicalization_history_pkey PRIMARY KEY (id);
ALTER TABLE translation_canonicalization_history ADD CONSTRAINT translation_canonicalization_identity_key UNIQUE (run_id, unit_id, canonical_target_sha256, canonicalizer_version);

CREATE INDEX article_lookup ON article (expression, reading);
CREATE INDEX article_sequence ON article (sequence);
CREATE INDEX batch_item_unit ON batch_item (unit_id);
CREATE INDEX jitendex_tag_category ON jitendex_tag (snapshot_id, category, code);
CREATE INDEX frequency_term_rank ON frequency_term (source, source_sha256, rank);
CREATE UNIQUE INDEX one_accepted_translation ON translation (run_id, unit_id) WHERE accepted = 1;

ALTER TABLE kaishi_note ADD CONSTRAINT kaishi_note_snapshot_fk FOREIGN KEY (snapshot_id) REFERENCES source_snapshot (id);
ALTER TABLE article ADD CONSTRAINT article_snapshot_fk FOREIGN KEY (snapshot_id) REFERENCES source_snapshot (id);
ALTER TABLE selection_candidate ADD CONSTRAINT selection_candidate_note_fk FOREIGN KEY (note_id) REFERENCES kaishi_note (id);
ALTER TABLE selection_candidate ADD CONSTRAINT selection_candidate_article_fk FOREIGN KEY (article_id) REFERENCES article (id);
ALTER TABLE selection_decision ADD CONSTRAINT selection_decision_note_fk FOREIGN KEY (note_id) REFERENCES kaishi_note (id);
ALTER TABLE run ADD CONSTRAINT run_jitendex_snapshot_fk FOREIGN KEY (jitendex_snapshot_id) REFERENCES source_snapshot (id);
ALTER TABLE run ADD CONSTRAINT run_kaishi_snapshot_fk FOREIGN KEY (kaishi_snapshot_id) REFERENCES source_snapshot (id);
ALTER TABLE translation_unit ADD CONSTRAINT translation_unit_run_fk FOREIGN KEY (run_id) REFERENCES run (id);
ALTER TABLE translation_unit ADD CONSTRAINT translation_unit_article_fk FOREIGN KEY (article_id) REFERENCES article (id);
ALTER TABLE batch ADD CONSTRAINT batch_run_fk FOREIGN KEY (run_id) REFERENCES run (id);
ALTER TABLE batch_item ADD CONSTRAINT batch_item_batch_fk FOREIGN KEY (batch_id) REFERENCES batch (id);
ALTER TABLE batch_item ADD CONSTRAINT batch_item_unit_fk FOREIGN KEY (unit_id) REFERENCES translation_unit (id);
ALTER TABLE attempt ADD CONSTRAINT attempt_batch_fk FOREIGN KEY (batch_id) REFERENCES batch (id);
ALTER TABLE translation ADD CONSTRAINT translation_run_fk FOREIGN KEY (run_id) REFERENCES run (id);
ALTER TABLE translation ADD CONSTRAINT translation_unit_fk FOREIGN KEY (unit_id) REFERENCES translation_unit (id);
ALTER TABLE translation ADD CONSTRAINT translation_attempt_fk FOREIGN KEY (attempt_id) REFERENCES attempt (id);
ALTER TABLE review ADD CONSTRAINT review_translation_fk FOREIGN KEY (translation_id) REFERENCES translation (id);
ALTER TABLE review ADD CONSTRAINT review_attempt_fk FOREIGN KEY (attempt_id) REFERENCES attempt (id);
ALTER TABLE validation_issue ADD CONSTRAINT validation_issue_run_fk FOREIGN KEY (run_id) REFERENCES run (id);
ALTER TABLE validation_issue ADD CONSTRAINT validation_issue_unit_fk FOREIGN KEY (unit_id) REFERENCES translation_unit (id);
ALTER TABLE validation_issue ADD CONSTRAINT validation_issue_attempt_fk FOREIGN KEY (attempt_id) REFERENCES attempt (id);
ALTER TABLE export ADD CONSTRAINT export_run_fk FOREIGN KEY (run_id) REFERENCES run (id);
ALTER TABLE export_file ADD CONSTRAINT export_file_export_fk FOREIGN KEY (export_id) REFERENCES export (id);
ALTER TABLE run_article ADD CONSTRAINT run_article_run_fk FOREIGN KEY (run_id) REFERENCES run (id);
ALTER TABLE run_article ADD CONSTRAINT run_article_article_fk FOREIGN KEY (article_id) REFERENCES article (id);
ALTER TABLE attempt_cost_report ADD CONSTRAINT attempt_cost_report_attempt_fk FOREIGN KEY (attempt_id) REFERENCES attempt (id);
ALTER TABLE jitendex_tag ADD CONSTRAINT jitendex_tag_snapshot_fk FOREIGN KEY (snapshot_id) REFERENCES source_snapshot (id);
ALTER TABLE jitendex_tag_translation_history ADD CONSTRAINT jitendex_tag_history_tag_fk FOREIGN KEY (tag_id) REFERENCES jitendex_tag (id);
ALTER TABLE frequency_article ADD CONSTRAINT frequency_article_article_fk FOREIGN KEY (article_id) REFERENCES article (id);
ALTER TABLE frequency_article ADD CONSTRAINT frequency_article_term_fk FOREIGN KEY (source, source_sha256, term) REFERENCES frequency_term (source, source_sha256, term);
ALTER TABLE translation_canonicalization_history ADD CONSTRAINT canonicalization_run_fk FOREIGN KEY (run_id) REFERENCES run (id);
ALTER TABLE translation_canonicalization_history ADD CONSTRAINT canonicalization_unit_fk FOREIGN KEY (unit_id) REFERENCES translation_unit (id);
ALTER TABLE translation_canonicalization_history ADD CONSTRAINT canonicalization_translation_fk FOREIGN KEY (translation_id) REFERENCES translation (id);

CREATE FUNCTION reject_immutable_history_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% rows are immutable', TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER attempt_cost_report_no_update
BEFORE UPDATE ON attempt_cost_report
FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER attempt_cost_report_no_delete
BEFORE DELETE ON attempt_cost_report
FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER translation_canonicalization_history_no_update
BEFORE UPDATE ON translation_canonicalization_history
FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER translation_canonicalization_history_no_delete
BEFORE DELETE ON translation_canonicalization_history
FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

SELECT setval(pg_get_serial_sequence('source_snapshot', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM source_snapshot;
SELECT setval(pg_get_serial_sequence('kaishi_note', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM kaishi_note;
SELECT setval(pg_get_serial_sequence('article', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM article;
SELECT setval(pg_get_serial_sequence('selection_candidate', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM selection_candidate;
SELECT setval(pg_get_serial_sequence('selection_decision', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM selection_decision;
SELECT setval(pg_get_serial_sequence('run', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM run;
SELECT setval(pg_get_serial_sequence('translation', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM translation;
SELECT setval(pg_get_serial_sequence('review', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM review;
SELECT setval(pg_get_serial_sequence('validation_issue', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM validation_issue;
SELECT setval(pg_get_serial_sequence('audit_event', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM audit_event;
SELECT setval(pg_get_serial_sequence('export', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM export;
SELECT setval(pg_get_serial_sequence('attempt_cost_report', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM attempt_cost_report;
SELECT setval(pg_get_serial_sequence('jitendex_tag', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM jitendex_tag;
SELECT setval(pg_get_serial_sequence('jitendex_tag_translation_history', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM jitendex_tag_translation_history;
SELECT setval(pg_get_serial_sequence('translation_canonicalization_history', 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM translation_canonicalization_history;

ANALYZE;
