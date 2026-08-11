# JPDB Luna Translation Orchestration Runbook

This is the exact operational procedure used to expand Russian Jitendex coverage sorted by JPDB frequency dictionary. Luna medium is used as translator and reviewer. OpenAI APIs are not used. 

## Inputs and environment

Run from:

~~~text
/Users/iuriikatkov/Documents/ChatGPT/jitendex-translations
~~~

Environment:

~~~bash
export PYTHONPATH=src
export UV_CACHE_DIR=/private/tmp/jitendex-uv-cache
~~~

Pinned inputs:

~~~text
Configuration: config.luna.clean-v1.toml
Prompt:        prompts/translate_luna_clean_v1.txt
Model:         gpt-5.6-luna
Effort:        medium
Database:      work/progress.sqlite3
JPDB ZIP:      work/downloads/Freq.JPDB_2022-05-10T03_27_02.930Z.zip
JPDB SHA-256:  5bda39a9e3b443b02199435ea723aa0555c891d1ce2c92ea7680163b72b07a0e
~~~

Verify the source:

~~~bash
shasum -a 256 work/downloads/Freq.JPDB_2022-05-10T03_27_02.930Z.zip
~~~

This workflow does not run the optional Terra review pass. translationctl validate therefore reports release_ready false and reviewed_units 0 even when Luna coverage and Yomitan validation are complete.

## State behavior

select-jpdb-scope replaces the live JPDB scope: it clears JPDB frequency mappings, clears article.selected, and selects articles for the new limit. Finish the current coverage report and export before selecting another limit.

Created runs remain frozen through run_article. Export reads run_article rather than mutable article.selected.

An identical selection and identical configuration can resolve to the existing run. Change batch.clean_run_nonce for a genuinely new clean rerun of the same scope.

## Terminology and tag policy through top 300k

Do not spend intermediate 10k batches repeatedly repairing translations solely because they differ from an approved canonical term or tag. Keep the approved catalog in the Luna manifest as strong generation guidance, but allow an otherwise valid Russian translation to enter the cumulative run. A structured tag that is not yet in the approved catalog must not stop batch creation.

Continue to reject genuine structural and content failures such as invalid response shape, wrong unit order, markup, control characters, empty output, lost protected tokens outside canonical whole-leaf fields, excessive untranslated English, and invalid glossary arrays. Canonicalization deferral is not a waiver for these failures.

After the final top-300k cumulative run is translated and accepted, but before its definitive Yomitan export, run one deterministic database-wide canonicalization job over that final run only:

1. Resolve structured Jitendex tag `content` and `title` leaves by their `(category, code)` metadata.
2. Replace those leaves with the approved catalog's exact `label_ru` and `description_ru` values.
3. Replace any other whole-leaf field carrying an exact `required_terminology.target_text` with that exact target.
4. Never perform blind substring replacement inside free-form definitions, glossary lists, examples, or explanatory prose; Russian morphology and context make that unsafe.
5. Preserve provenance by recording canonicalized values as the final run's accepted translation state rather than rewriting historical source runs.
6. Re-run deterministic validation and the exactly-one-accepted-translation audit, then build and verify the definitive top-300k Yomitan archive.

Until top 300k, a canonical wording difference by itself is not a reason for targeted singleton repair. The per-batch canonical hints remain useful because they reduce the size of the final normalization pass.

## Top-10k procedure

The completed expansion used source run 5 and created target run 6.

### 1. Select the first 10,000 JPDB rows

~~~bash
translationctl --config config.luna.clean-v1.toml \
  select-jpdb-scope \
  work/downloads/Freq.JPDB_2022-05-10T03_27_02.930Z.zip \
  --limit 10000
~~~

Observed:

~~~text
requested_rows:       10,000
unique_terms:          9,395
matched_terms:         9,350
skipped_terms:            45
selected_articles:    12,901
expression_matches:   11,271
reading_matches:       3,542
~~~

Duplicate spellings keep their earliest rank. Each spelling matches exact normalized Jitendex expressions and readings and can map to multiple articles.

Do not run resolve-scope for this step. That command is for Kaishi candidate generation; select-jpdb-scope directly establishes the JPDB selection.

### 2. Create the run and extract units

~~~bash
translationctl --config config.luna.clean-v1.toml extract-units
~~~

Observed:

~~~json
{
  "articles_without_units": 557,
  "run_id": 6,
  "units_added": 148017
}
~~~

This freezes every selected article and its structural fingerprint in run_article.

### 3. Reuse accepted top-5k translations

~~~bash
translationctl --config config.luna.clean-v1.toml \
  reuse-translations \
  --source-run-id 5 \
  --target-run-id 6
~~~

Reuse requires an exact article ID, JSON pointer, role, source SHA-256, and an accepted source-run translation.

Observed: 92,228 reused units.

Run 5 contained 92,238 accepted units. Ten old units were image rendering controls named appearance and sizeUnits. The extractor was corrected to classify them as structure, so they intentionally do not exist in run 6.

### 4. Batch only remaining ready units

~~~bash
translationctl --config config.luna.clean-v1.toml \
  make-batches \
  --run-id 6
~~~

Observed:

~~~json
{
  "articles": 5430,
  "batches_created": 988,
  "units": 55789
}
~~~

Limits from the configuration:

~~~text
soft_max_articles = 6
soft_max_bytes = 24576
soft_max_units = 100
singleton_threshold_bytes = 16384
hard_max_article_bytes = 49152
hard_max_article_units = 200
~~~

Manifests are stored in work/inbox. Batch identity is deterministic over run ID, article IDs, and ordered unit IDs.

### 5. Start four parallel Luna pools

The orchestrator used four persistent PTY sessions with concurrency 20 each, for target concurrency 80.

Pool 1:

~~~bash
python scripts/run_codex_batches.py \
  --config config.luna.clean-v1.toml \
  --run-id 6 \
  --kind translation \
  --concurrency 20 \
  --worker-prefix jpdb10k-pool1
~~~

Run the same command in three more sessions with these prefixes:

~~~text
jpdb10k-pool2
jpdb10k-pool3
jpdb10k-pool4
~~~

For each batch the runner:

1. claims and leases the batch;
2. creates an attempt row;
3. generates a strict schema for the exact ordered unit set;
4. supplies the configured prompt and one manifest;
5. invokes the bundled Codex CLI ephemerally in a read-only temporary workspace;
6. writes the model response to work/outbox;
7. records model identity, tokens, request/thread ID, and latency;
8. runs deterministic validation;
9. ingests valid output;
10. retries or recursively splits rejected output;
11. claims more work until no ready batch remains.

The subprocess runner currently has no explicit timeout.

### 6. Monitor authoritative SQLite state

~~~bash
sqlite3 -cmd '.timeout 5000' -header -column work/progress.sqlite3 "
SELECT state,COUNT(*) batches,SUM(unit_count) units
FROM batch
WHERE run_id=6
GROUP BY state
ORDER BY state;

SELECT COUNT(*) unresolved_errors
FROM validation_issue
WHERE run_id=6
  AND severity='error'
  AND resolved_at IS NULL;

SELECT COUNT(*) orphaned_unresolved
FROM validation_issue vi
WHERE vi.run_id=6
  AND vi.severity='error'
  AND vi.resolved_at IS NULL
  AND NOT EXISTS (
    SELECT 1
    FROM attempt a
    JOIN batch b ON b.id=a.batch_id
    WHERE a.id=vi.attempt_id
      AND b.state IN ('ready','leased','retryable')
  );

SELECT COUNT(*) leaf_blocked
FROM batch b
WHERE b.run_id=6
  AND b.state='blocked'
  AND NOT EXISTS (
    SELECT 1
    FROM audit_event ae
    WHERE ae.event_type='split'
      AND ae.entity_id=b.id
  );
"
~~~

Interpretation:

- ready, leased, and retryable are unfinished;
- deterministic_validated is completed work awaiting acceptance;
- blocked with a split audit event is a superseded parent, not a gap;
- leaf_blocked requires targeted repair;
- orphaned_unresolved should stay zero while retries remain active.

Normal automatic failures included no_cyrillic, too_much_english, unit_order_or_set_mismatch, and protected_token_missing. Let retry/split isolation finish before manual repair. Do not repair or requeue a batch solely for a canonical terminology or tag wording difference; defer that difference to the final top-300k normalization pass described above.

### 7. Recover a genuinely stalled worker

One 66-unit batch stayed silent for repeated bounded waits because the runner has no subprocess timeout.

The orchestrator interrupted the owning PTY with Ctrl-C, confirmed the leased attempt, marked it interrupted, requeued it, recorded an audit event, and ran one replacement worker.

Find active leases:

~~~bash
sqlite3 -header -column work/progress.sqlite3 "
SELECT b.id batch_id,b.unit_count,b.lease_expires_at,
       a.id attempt_id,a.created_at,a.outcome,
       a.request_path,a.response_path
FROM batch b
JOIN attempt a ON a.batch_id=b.id
WHERE b.run_id=6
  AND b.state='leased'
ORDER BY a.created_at DESC;
"
~~~

Only after confirming the process is stopped:

~~~sql
BEGIN IMMEDIATE;

UPDATE attempt
SET outcome='interrupted',
    error_json='{"reason":"stalled codex subprocess interrupted after repeated bounded waits"}',
    completed_at=CURRENT_TIMESTAMP
WHERE id='<ATTEMPT_ID>'
  AND outcome='claimed';

UPDATE batch
SET state='ready',
    lease_token=NULL,
    lease_expires_at=NULL
WHERE id='<BATCH_ID>'
  AND state='leased';

INSERT INTO audit_event(event_type,entity_type,entity_id,details_json)
VALUES (
  'recover_interrupted_worker',
  'batch',
  '<BATCH_ID>',
  '{"attempt_id":"<ATTEMPT_ID>"}'
);

COMMIT;
~~~

Replacement:

~~~bash
python scripts/run_codex_batches.py \
  --config config.luna.clean-v1.toml \
  --run-id 6 \
  --kind translation \
  --concurrency 1 \
  --worker-prefix jpdb10k-recovered
~~~

The replacement failed one strict order/set validation, retried automatically, then ingested all 66 units.

### 8. Repair exhausted singleton leaves through normal ingestion

Wait for all automatic workers to exit, then inspect only terminal leaves:

Repair only deterministic structural/content failures at this stage. Do not create a targeted repair merely to force a known tag or whole-leaf term into its canonical wording; that cleanup is intentionally deferred until the final cumulative run.

~~~bash
sqlite3 -header -column work/progress.sqlite3 "
SELECT b.id batch_id,
       tu.id unit_id,
       tu.article_id,
       tu.role,
       tu.json_pointer,
       tu.source_text,
       tu.source_sha256,
       tu.protected_tokens_json
FROM batch b
JOIN batch_item bi ON bi.batch_id=b.id
JOIN translation_unit tu ON tu.id=bi.unit_id
WHERE b.run_id=6
  AND b.state='blocked'
  AND NOT EXISTS (
    SELECT 1 FROM audit_event ae
    WHERE ae.event_type='split'
      AND ae.entity_id=b.id
  )
ORDER BY b.id,bi.ordinal;
"
~~~

Run 6 had five leaves representing four translations:

| Source | Accepted Russian target |
|---|---|
| Boston Dynamic's robot, RHex, is an amazing piece of work that can run over various terrains. | Робот «Рэкс» компании «Бостон Дайнэмикс» — удивительная разработка, способная передвигаться по самой разной местности. |
| kozo (Broussonetia kazinoki x papyrifera); Japanese paper mulberry tree | кодзо (гибрид бруссонетии Кадзиноки и бруссонетии бумажной); японское бумажное дерево |
| from initials of Linux, Apache, MySQL, PHP | от начальных букв названий «Линукс», «Апачи», «Май-эс-кью-эл» и «Пи-эйч-пи» |
| glossary set LAMP | ЛАМП |

The Boston example occurred in two articles.

Requeue only terminal leaves:

~~~sql
BEGIN IMMEDIATE;

UPDATE batch
SET state='ready',
    lease_token=NULL,
    lease_expires_at=NULL
WHERE run_id=6
  AND state='blocked'
  AND NOT EXISTS (
    SELECT 1 FROM audit_event ae
    WHERE ae.event_type='split'
      AND ae.entity_id=batch.id
  );

COMMIT;
~~~

Explicitly claim each batch:

~~~bash
translationctl --config config.luna.clean-v1.toml \
  claim \
  --worker-id targeted-top10k-repair \
  --run-id 6 \
  --kind translation \
  --batch-id '<BATCH_ID>' \
  --transport codex-agent
~~~

Read the returned request_path and write strict JSON to the returned response_path:

~~~json
{
  "schema_version": 2,
  "batch_id": "<BATCH_ID>",
  "manifest_sha256": "<MANIFEST_SHA256>",
  "translations": [
    {
      "unit_id": "<UNIT_ID>",
      "source_sha256": "<SOURCE_SHA256>",
      "target_text": "русский перевод",
      "confidence": "high",
      "review_reason": null
    }
  ]
}
~~~

For glossary_set, target_text must be an array:

~~~json
"target_text": ["ЛАМП"]
~~~

Requirements:

- exact unit order and set;
- exact source hashes;
- no extra fields;
- preserve protected tokens;
- Cyrillic unless explicitly allowed;
- no markup/control characters;
- at most two unprotected ASCII words after allowed scientific-taxon handling.

Ingest each file through the standard validator:

~~~bash
translationctl --config config.luna.clean-v1.toml \
  ingest-response \
  '<RESPONSE_PATH>'
~~~

A valid later response resolves earlier deterministic issues for the same batch.

### 9. Prove all translation work is drained

Required run-6 state before final acceptance:

~~~text
deterministic_validated units: 55,789
active batches:                    0
unresolved errors:                 0
leaf-blocked batches:              0
translated units:            148,017
~~~

Check with:

~~~bash
sqlite3 -header -column work/progress.sqlite3 "
SELECT state,COUNT(*) batches,SUM(unit_count) units
FROM batch WHERE run_id=6
GROUP BY state ORDER BY state;

SELECT COUNT(*) unresolved_errors
FROM validation_issue
WHERE run_id=6
  AND severity='error'
  AND resolved_at IS NULL;

SELECT COUNT(*) active_batches
FROM batch
WHERE run_id=6
  AND state IN ('ready','leased','retryable');

SELECT COUNT(*) leaf_blocked
FROM batch b
WHERE b.run_id=6
  AND b.state='blocked'
  AND NOT EXISTS (
    SELECT 1 FROM audit_event ae
    WHERE ae.event_type='split'
      AND ae.entity_id=b.id
  );

SELECT COUNT(*) translated_units
FROM translation_unit
WHERE run_id=6
  AND status='translated';
"
~~~

### 10. Accept deterministic translations

~~~bash
translationctl --config config.luna.clean-v1.toml \
  accept-translations \
  --run-id 6
~~~

Observed:

~~~json
{
  "run_id": 6,
  "translations_accepted": 55789
}
~~~

### 11. Run the coverage gate

~~~bash
translationctl --config config.luna.clean-v1.toml \
  report-jpdb-coverage \
  --run-id 6
~~~

Observed:

~~~json
{
  "complete": true,
  "covered_terms": 9350,
  "fully_accepted_articles": 12901,
  "matched_terms": 9350,
  "run_id": 6,
  "selected_articles": 12901,
  "skipped_terms": 45,
  "source_sha256": "5bda39a9e3b443b02199435ea723aa0555c891d1ce2c92ea7680163b72b07a0e",
  "unique_terms": 9395
}
~~~

complete true means every matched JPDB term reaches a frozen run article and every selected article has all units accepted.

### 12. Build the dictionary

~~~bash
translationctl --config config.luna.clean-v1.toml \
  build \
  --run-id 6 \
  --output dist/jitendex-jpdb-10k-ru-luna-clean-v1.zip
~~~

Observed:

~~~json
{
  "articles": 12901,
  "export_id": 12,
  "files": 24,
  "zip_sha256": "a13a670937df9c1ffecaab815e6fc51773bf1b276e4cc6de05c5c38fbc2aa113"
}
~~~

### 13. Verify ZIP and pinned Yomitan schemas

~~~bash
translationctl --config config.luna.clean-v1.toml \
  verify \
  dist/jitendex-jpdb-10k-ru-luna-clean-v1.zip
~~~

Observed:

~~~json
{
  "articles": 12901,
  "files": 24,
  "schema_validated_banks": 10,
  "verified": true,
  "zip_sha256": "a13a670937df9c1ffecaab815e6fc51773bf1b276e4cc6de05c5c38fbc2aa113"
}
~~~

This checks index placement, duplicate members, target language, media, frozen article count, recorded export hash, and every pinned term-bank schema.

### 14. Run tests and run validation

~~~bash
pytest -q
~~~

Observed: 49 passed.

~~~bash
translationctl --config config.luna.clean-v1.toml \
  validate \
  --run-id 6
~~~

Observed:

~~~json
{
  "accepted_units": 148017,
  "batch_membership_mismatches": 0,
  "blocking_issues": 0,
  "release_ready": false,
  "reviewed_units": 0,
  "run_id": 6,
  "units": 148017
}
~~~

release_ready false is caused by the intentionally omitted review stage.

### 15. Final database and archive audit

~~~bash
sqlite3 -header -column work/progress.sqlite3 "
SELECT COUNT(*) unique_terms,
       SUM(matched) matched_terms,
       SUM(CASE WHEN matched=0 THEN 1 ELSE 0 END) skipped_terms,
       MIN(rank) min_rank,
       MAX(rank) max_rank
FROM frequency_term
WHERE source='jpdb';

SELECT COUNT(DISTINCT fa.article_id) mapped_articles,
       COUNT(*) mappings
FROM frequency_article fa
WHERE fa.source='jpdb';

SELECT COUNT(*) missing_mapped_run_articles
FROM frequency_article fa
WHERE fa.source='jpdb'
  AND NOT EXISTS (
    SELECT 1 FROM run_article ra
    WHERE ra.run_id=6
      AND ra.article_id=fa.article_id
  );

SELECT COUNT(*) run_articles
FROM run_article WHERE run_id=6;

SELECT COUNT(*) units
FROM translation_unit WHERE run_id=6;

SELECT COUNT(*) accepted_translations,
       COUNT(DISTINCT unit_id) accepted_units
FROM translation
WHERE run_id=6 AND accepted=1;

SELECT COUNT(*) units_without_exactly_one_accept
FROM translation_unit tu
WHERE tu.run_id=6
  AND (
    SELECT COUNT(*)
    FROM translation t
    WHERE t.run_id=tu.run_id
      AND t.unit_id=tu.id
      AND t.accepted=1
  )<>1;

SELECT COUNT(*) unresolved_errors
FROM validation_issue
WHERE run_id=6
  AND severity='error'
  AND resolved_at IS NULL;

SELECT COUNT(*) active_batches
FROM batch
WHERE run_id=6
  AND state IN ('ready','leased','retryable');

SELECT COUNT(*) leaf_blocked
FROM batch b
WHERE b.run_id=6
  AND b.state='blocked'
  AND NOT EXISTS (
    SELECT 1 FROM audit_event ae
    WHERE ae.event_type='split'
      AND ae.entity_id=b.id
  );

SELECT id,run_id,output_path,zip_sha256,verified
FROM export
WHERE run_id=6
ORDER BY id DESC
LIMIT 1;
"
~~~

Required:

~~~text
unique terms:                       9,395
matched terms:                      9,350
skipped terms:                         45
rank range:                         1–10,000
mapped/frozen articles:             12,901
frequency-to-article mappings:      14,813
missing mapped run articles:             0
translation units:                148,017
accepted units:                   148,017
units without exactly one accept:       0
unresolved errors:                      0
active batches:                         0
leaf blocked:                           0
latest export verified:                 1
~~~

Archive:

~~~bash
shasum -a 256 dist/jitendex-jpdb-10k-ru-luna-clean-v1.zip
unzip -Z1 dist/jitendex-jpdb-10k-ru-luna-clean-v1.zip | wc -l

for n in 1 2 3 4 5 6 7 8 9 10; do
  unzip -p dist/jitendex-jpdb-10k-ru-luna-clean-v1.zip "term_bank_$n.json" | jq length
done | awk '{s+=$1} END {print s}'
~~~

Required:

~~~text
SHA-256:        a13a670937df9c1ffecaab815e6fc51773bf1b276e4cc6de05c5c38fbc2aa113
ZIP members:    24
term-bank rows: 12,901
~~~

## Completed run summary

| Scope | Run | Unique | Matched | Skipped | Articles | Accepted units | Reused | New | Schema banks | ZIP SHA-256 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Top 5,000 rows | 5 | 4,749 | 4,726 | 23 | 7,194 | 92,238 | 26,638 | 65,600 | 6 | 752ad0919317b75764e5117a9e24ba62e9f9ee448b0336d8692da75885cd06fa |
| Top 10,000 rows | 6 | 9,395 | 9,350 | 45 | 12,901 | 148,017 | 92,228 | 55,789 | 10 | a13a670937df9c1ffecaab815e6fc51773bf1b276e4cc6de05c5c38fbc2aa113 |
| Top 20,000 rows | 7 | 18,595 | 18,481 | 114 | 23,432 | 241,479 | 148,017 | 93,462 | 16 | cfe26fc8dd4177d4dffea667af8e27eef6df4fb5869eca4f79f4d237141a861a |
| Top 30,000 rows | 8 | 27,717 | 27,472 | 245 | 33,603 | 323,186 | 241,479 | 81,707 | 21 | f6334307b20eb69f80ecfa7932f3a8d76655c1acf389d573c91946ac741a4824 |
| Top 40,000 rows | 9 | 36,700 | 36,233 | 467 | 43,347 | 397,771 | 323,186 | 74,585 | 25 | 97b0414caf834589cf2750c05a83a9ada70b152671e1261d35ed8801ad228489 |
| Top 50,000 rows | 10 | 45,581 | 44,791 | 790 | 52,631 | 465,525 | 397,771 | 67,754 | 29 | 562b3f628c7fcbab03cb7701bfe8f127ef0a64629b26c1c15983ec7bfa3ee673 |
| Top 60,000 rows | 11 | 54,442 | 53,264 | 1,178 | 61,909 | 530,142 | 465,525 | 64,617 | 33 | 566507ed9ead96b130fc7785b82c58348d5dbc1df6e769dc64747fade04d9bd4 |
| Top 70,000 rows | 12 | 63,255 | 61,606 | 1,649 | 70,864 | 589,571 | 530,142 | 59,429 | 36 | dde40d8265239f69fc394c2a8b110fe3b52877ee29ee2618bd7c6b619674c07f |
| Top 80,000 rows | 13 | 71,923 | 69,705 | 2,218 | 79,397 | 644,744 | 589,571 | 55,173 | 39 | 1ff1147705bcb5f39bc2906c1b7f7669d33204cad344b5fe193d67c1370b5daa |
| Top 90,000 rows | 14 | 80,556 | 77,688 | 2,868 | 87,872 | 698,173 | 644,744 | 53,429 | 42 | e660db82617968ebc6e4ef63361609c9b34e9fab26c8c441cc5ce3834d7001c2 |
| Top 100,000 rows | 15 | 89,142 | 85,514 | 3,628 | 96,081 | 748,745 | 698,173 | 50,572 | 45 | fe6024a2fa0ef1a1a589ec7ce94700f1810da40fb0c0049d9919c1a036cda622 |

## Top-20k continuation results

The top-20k expansion followed the top-10k procedure with source run 6 and target run 7.

~~~bash
translationctl --config config.luna.clean-v1.toml \
  select-jpdb-scope \
  work/downloads/Freq.JPDB_2022-05-10T03_27_02.930Z.zip \
  --limit 20000

translationctl --config config.luna.clean-v1.toml extract-units

translationctl --config config.luna.clean-v1.toml \
  reuse-translations \
  --source-run-id 6 \
  --target-run-id 7

translationctl --config config.luna.clean-v1.toml \
  make-batches \
  --run-id 7
~~~

Observed scope and extraction:

~~~text
requested rows:          20,000
unique terms:            18,595
matched terms:           18,481
skipped terms:              114
selected articles:       23,432
frequency mappings:      26,967
rank-10,001–20,000 unique terms:   9,200
rank-10,001–20,000 matched terms:  9,131
rank-10,001–20,000 skipped terms:     69
new articles beyond run 6:         10,531
translation units:      241,479
articles without units:   1,154
reused run-6 units:      148,017
new Luna units:           93,462
initial batches:           1,749
~~~

Four pools ran at concurrency 20 with prefixes `jpdb20k-pool1` through `jpdb20k-pool4`. Automatic retries and recursive splits validated 93,460 new units. Two exhausted singleton example units were requeued, explicitly claimed, translated from their supplied Japanese article context, and ingested through the standard validator:

| Source | Accepted Russian target |
|---|---|
| Why don't you try out getting a new Windows Media Player skin and changing the player's look? | Попробуйте установить новую тему оформления для «Виндоус Медиа Плеер» и изменить внешний вид проигрывателя. |
| What Microsoft is launching is a beta version of its "NetShow streaming server"; it supplies video and audio on demand. | Компания «Майкрософт» запускает бета-версию сервера потоковой передачи «НетШоу», который предоставляет видео и аудио по запросу. |

Final translation state before acceptance:

~~~text
deterministic_validated units: 93,462
active batches:                     0
unresolved errors:                  0
leaf-blocked batches:               0
translated units:             241,479
~~~

Acceptance and coverage:

~~~bash
translationctl --config config.luna.clean-v1.toml \
  accept-translations \
  --run-id 7

translationctl --config config.luna.clean-v1.toml \
  report-jpdb-coverage \
  --run-id 7
~~~

Observed: 93,462 newly accepted translations and `complete: true`, covering all 18,481 matched terms and all 23,432 frozen articles.

Build and verification:

~~~bash
translationctl --config config.luna.clean-v1.toml \
  build \
  --run-id 7 \
  --output dist/jitendex-jpdb-20k-ru-luna-clean-v1.zip

translationctl --config config.luna.clean-v1.toml \
  verify \
  dist/jitendex-jpdb-20k-ru-luna-clean-v1.zip
~~~

Verified output:

~~~text
articles:               23,432
ZIP members:                36
schema-validated banks:     16
SHA-256: cfe26fc8dd4177d4dffea667af8e27eef6df4fb5869eca4f79f4d237141a861a
~~~

Run validation reported 241,479 accepted units, zero batch-membership mismatches, and zero blocking issues. As with earlier Luna-only runs, `release_ready` remains false only because the optional review stage was intentionally omitted.

## Top-30k continuation results

The top-30k expansion followed the same cumulative procedure with source run 7 and target run 8.

~~~bash
translationctl --config config.luna.clean-v1.toml \
  select-jpdb-scope \
  work/downloads/Freq.JPDB_2022-05-10T03_27_02.930Z.zip \
  --limit 30000

translationctl --config config.luna.clean-v1.toml extract-units

translationctl --config config.luna.clean-v1.toml \
  reuse-translations \
  --source-run-id 7 \
  --target-run-id 8

translationctl --config config.luna.clean-v1.toml \
  make-batches \
  --run-id 8
~~~

Observed scope and extraction:

~~~text
requested rows:          30,000
unique terms:            27,717
matched terms:           27,472
skipped terms:              245
selected articles:       33,603
frequency mappings:      38,792
rank-20,001–30,000 unique terms:   9,122
rank-20,001–30,000 matched terms:  8,991
rank-20,001–30,000 skipped terms:    131
new articles beyond run 7:         10,171
translation units:      323,186
articles without units:   1,749
reused run-7 units:      241,479
new Luna units:           81,707
initial batches:           1,635
~~~

Four pools ran at concurrency 20 with prefixes `jpdb30k-pool1` through `jpdb30k-pool4`. Automatic retries and recursive splits validated 81,705 new units. Two exhausted singleton units were requeued, explicitly claimed, translated from their supplied article context, and ingested through the standard validator:

| Source | Accepted Russian target |
|---|---|
| kozo (Broussonetia kazinoki x papyrifera); Japanese paper mulberry tree | кодзо (гибрид бруссонетии Кадзиноки и бруссонетии бумажной); японское бумажное дерево |
| edible seaweed, usu. Porphyra yezoensis or P. tenera, usu. dried and pressed into sheets | съедобная морская водоросль, обычно порфира йезоэнсис или порфира тенера; как правило, высушивается и прессуется в листы |

Final translation state before acceptance:

~~~text
deterministic_validated units: 81,707
active batches:                     0
unresolved errors:                  0
leaf-blocked batches:               0
translated units:             323,186
~~~

Acceptance and coverage reported 81,707 newly accepted translations and `complete: true`, covering all 27,472 matched terms and all 33,603 frozen articles.

Verified output:

~~~text
articles:               33,603
ZIP members:                48
schema-validated banks:     21
SHA-256: f6334307b20eb69f80ecfa7932f3a8d76655c1acf389d573c91946ac741a4824
~~~

Run validation reported 323,186 accepted units, zero batch-membership mismatches, and zero blocking issues. All 52 tests passed. As with earlier Luna-only runs, `release_ready` remains false only because the optional review stage was intentionally omitted.

## Top-40k continuation results

The top-40k expansion used source run 8 and target run 9.

~~~text
requested rows:          40,000
unique terms:            36,700
matched terms:           36,233
skipped terms:              467
selected articles:       43,347
frequency mappings:      50,254
rank-30,001–40,000 unique terms:   8,983
rank-30,001–40,000 matched terms:  8,761
rank-30,001–40,000 skipped terms:    222
new articles beyond run 8:          9,744
translation units:      397,771
articles without units:   2,380
reused run-8 units:      323,186
new Luna units:           74,585
initial batches:           1,555
~~~

Four pools ran at concurrency 20 with prefixes `jpdb40k-pool1` through `jpdb40k-pool4`. One 43-unit batch remained silent for repeated bounded waits in a live Codex subprocess. The owning pool was interrupted, the exact claimed attempt was marked `interrupted`, the batch was requeued with a `recover_interrupted_worker` audit event, and a one-worker replacement ingested all 43 units.

Automatic retries and recursive splits validated 74,573 new units. Twelve exhausted singleton units were requeued, explicitly claimed, translated from their supplied article context, and ingested through the standard validator:

| Source | Accepted Russian target |
|---|---|
| lowest seat; foot of the table; seat furthest from the seat of honour | последнее место; нижний конец стола; место, наиболее удалённое от почётного места |
| spelling and reading variants | варианты написания и чтения |
| forms | формы |
| large pink (Dianthus superbus var. longicalycinus) | гвоздика пышная длинночашечковая |
| Lagenaria siceraria var. depressa (variety of bottle gourd) | лагенария обыкновенная, разновидность приплюснутая (сорт бутылочной тыквы) |
| wasei | японское слово, образованное из английских элементов |
| English: "concent(ric plug)" | англ.: «концентрическая вилка» |
| noun | сущ. |
| ① pink (any flower of genus Dianthus, esp. the fringed pink, Dianthus superbus) | ① гвоздика (любое растение рода Гвоздика, особенно гвоздика пышная) |
| English: "towel (blan)ket" | англ.: от «полотенце» и «одеяло» |
| ① Macintosh (brand of personal computer manufactured by Apple); Mac | ① «Макинтош» (марка персональных компьютеров компании «Эппл»); «Мак» |
| ① bottle gourd (Lagenaria siceraria var. hispida); calabash | ① бутылочная тыква (лагенария обыкновенная, разновидность щетинистая); калебаса |

Final translation state before acceptance:

~~~text
deterministic_validated units: 74,585
active batches:                     0
unresolved errors:                  0
leaf-blocked batches:               0
translated units:             397,771
~~~

Acceptance and coverage reported 74,585 newly accepted translations and `complete: true`, covering all 36,233 matched terms and all 43,347 frozen articles.

Verified output:

~~~text
articles:               43,347
ZIP members:                56
schema-validated banks:     25
SHA-256: 97b0414caf834589cf2750c05a83a9ada70b152671e1261d35ed8801ad228489
~~~

Run validation reported 397,771 accepted units, zero batch-membership mismatches, and zero blocking issues. All 52 tests passed. `release_ready` remains false only because the optional review stage was intentionally omitted.

## Top-50k continuation results

The top-50k expansion used source run 9 and target run 10.

~~~text
requested rows:          50,000
unique terms:            45,581
matched terms:           44,791
skipped terms:              790
selected articles:       52,631
frequency mappings:      61,157
rank-40,001–50,000 unique terms:   8,881
rank-40,001–50,000 matched terms:  8,558
rank-40,001–50,000 skipped terms:    323
new articles beyond run 9:          9,284
translation units:      465,525
articles without units:   3,065
reused run-9 units:      397,771
new Luna units:           67,754
initial batches:           1,459
~~~

Four pools ran at concurrency 20 with prefixes `jpdb50k-pool1` through `jpdb50k-pool4`. Automatic retries and recursive splits validated 67,751 new units. Three exhausted singleton units were requeued, explicitly claimed, translated from their supplied article context, and ingested through the standard validator:

| Source | Accepted Russian target |
|---|---|
| marron (Cherax tenuimanus and Cherax cainii species of freshwater crayfish) | маррон (пресноводный рак видов херакс тенуиманус и херакс Каина) |
| gentian (Gentiana scabra var. buergeri); autumn bellflower | горечавка шероховатая, разновидность Бюргера; осенний колокольчик |
| English: "televi(sion) game" | англ.: «телевизионная игра» |

Final translation state before acceptance:

~~~text
deterministic_validated units: 67,754
active batches:                     0
unresolved errors:                  0
leaf-blocked batches:               0
translated units:             465,525
~~~

Acceptance and coverage reported 67,754 newly accepted translations and `complete: true`, covering all 44,791 matched terms and all 52,631 frozen articles.

Verified output:

~~~text
articles:               52,631
ZIP members:                75
schema-validated banks:     29
SHA-256: 562b3f628c7fcbab03cb7701bfe8f127ef0a64629b26c1c15983ec7bfa3ee673
~~~

Run validation reported 465,525 accepted units, zero batch-membership mismatches, and zero blocking issues. All 52 tests passed. `release_ready` remains false only because the optional review stage was intentionally omitted.

## Top-60k continuation results

The top-60k expansion used source run 10 and target run 11.

~~~text
requested rows:          60,000
unique terms:            54,442
matched terms:           53,264
skipped terms:            1,178
selected articles:       61,909
frequency mappings:      72,004
rank-50,001–60,000 unique terms:   8,861
rank-50,001–60,000 matched terms:  8,473
rank-50,001–60,000 skipped terms:    388
new articles beyond run 10:         9,278
translation units:      530,142
articles without units:   3,749
reused run-10 units:     465,525
new Luna units:           64,617
initial batches:           1,447
~~~

Four pools ran at concurrency 20 with prefixes `jpdb60k-pool1` through `jpdb60k-pool4`. Automatic retries and recursive splits validated 64,610 new units. Seven exhausted singleton units were requeued, explicitly claimed, translated from their supplied article context, and ingested through the standard validator:

| Source | Accepted Russian target |
|---|---|
| ramie (Boehmeria nivea var. candicans) | рами (бёмерия снежная, разновидность беловатая) |
| English: "game soft(ware)" | англ.: «игровое программное обеспечение» |
| Manchurian ash (Fraxinus mandshurica var. japonica), in two articles | ясень маньчжурский, разновидность японская |
| English: "hit and away" | англ.: «ударить и отойти» |
| Alpine leek (Allium victorialis var. platyphyllum) | лук победный, разновидность широколистная |
| Asian hazel (Corylus heterophylla var. thunbergii); Siberian hazel | лещина разнолистная, разновидность Тунберга; лещина сибирская |

Final translation state before acceptance:

~~~text
deterministic_validated units: 64,617
active batches:                     0
unresolved errors:                  0
leaf-blocked batches:               0
translated units:             530,142
~~~

Acceptance and coverage reported 64,617 newly accepted translations and `complete: true`, covering all 53,264 matched terms and all 61,909 frozen articles.

Verified output:

~~~text
articles:               61,909
ZIP members:                95
schema-validated banks:     33
SHA-256: 566507ed9ead96b130fc7785b82c58348d5dbc1df6e769dc64747fade04d9bd4
~~~

Run validation reported 530,142 accepted units, zero batch-membership mismatches, and zero blocking issues. All 52 tests passed. `release_ready` remains false only because the optional review stage was intentionally omitted.

## Top-70k continuation results

The top-70k expansion used source run 11 and target run 12.

~~~text
requested rows:          70,000
unique terms:            63,255
matched terms:           61,606
skipped terms:            1,649
selected articles:       70,864
frequency mappings:      82,516
rank-60,001–70,000 unique terms:   8,813
rank-60,001–70,000 matched terms:  8,342
rank-60,001–70,000 skipped terms:    471
new articles beyond run 11:         8,955
translation units:      589,571
articles without units:   4,462
reused run-11 units:     530,142
new Luna units:           59,429
initial batches:           1,384
~~~

Four pools ran at concurrency 20 with prefixes `jpdb70k-pool1` through `jpdb70k-pool4`. Automatic retries and recursive splits validated 59,426 new units. Three exhausted singleton units from one bottle-gourd article were requeued, explicitly claimed, translated with the same validated Cyrillic taxonomy used in earlier runs, and ingested through the standard validator:

| Source | Accepted Russian target |
|---|---|
| Lagenaria siceraria var. gourda; gourd container | лагенария обыкновенная, разновидность гурда; сосуд из плода бутылочной тыквы |
| Lagenaria siceraria var. depressa | лагенария обыкновенная, разновидность приплюснутая |
| bottle gourd (Lagenaria siceraria var. hispida); calabash | бутылочная тыква (лагенария обыкновенная, разновидность щетинистая); калебаса |

Final translation state before acceptance:

~~~text
deterministic_validated units: 59,429
active batches:                     0
unresolved errors:                  0
leaf-blocked batches:               0
translated units:             589,571
~~~

Acceptance and coverage reported 59,429 newly accepted translations and `complete: true`, covering all 61,606 matched terms and all 70,864 frozen articles.

Verified output:

~~~text
articles:               70,864
ZIP members:               108
schema-validated banks:     36
SHA-256: dde40d8265239f69fc394c2a8b110fe3b52877ee29ee2618bd7c6b619674c07f
~~~

Run validation reported 589,571 accepted units, zero batch-membership mismatches, and zero blocking issues. All 52 tests passed. `release_ready` remains false only because the optional review stage was intentionally omitted.

## Top-80k continuation results

The top-80k expansion used source run 12 and target run 13.

~~~text
requested rows:          80,000
unique terms:            71,923
matched terms:           69,705
skipped terms:            2,218
selected articles:       79,397
frequency mappings:      92,686
rank-70,001–80,000 unique terms:   8,668
rank-70,001–80,000 matched terms:  8,099
rank-70,001–80,000 skipped terms:    569
new articles beyond run 12:         8,533
translation units:      644,744
articles without units:   5,131
reused run-12 units:     589,571
new Luna units:           55,173
initial batches:           1,317
~~~

Four pools ran at concurrency 20 with prefixes `jpdb80k-pool1` through `jpdb80k-pool4`. Automatic retries and recursive splits validated 55,167 new units. One expired 58-unit attempt left a Luna subprocess orphaned after a replacement attempt had already split its parent; the orphan was interrupted and audited using the stalled-worker recovery procedure, with no lost units. Six exhausted singleton units were then requeued, explicitly claimed, translated, and ingested through the standard validator. The botanical and product-name entries needed one additional fully Cyrillic retry:

| Source | Accepted Russian target |
|---|---|
| English: "one box car" | из англ. «однокорпусный автомобиль» |
| Spanish: "cha cha cha" | из исп. «ча-ча-ча» |
| English: "royal milk tea" | из англ. «королевский чай с молоком» |
| shiso (Perilla frutescens var. crispa); perilla; beefsteak plant | сисо (перилла нанкинская); перилла; перилла кустарниковая |
| Why don't you try out getting a new Windows Media Player skin and changing the player's look? | Попробуйте установить новую тему оформления для проигрывателя «Виндоус Медиа Плеер» и изменить его внешний вид. |
| English: "one-room mansion" | из англ. «однокомнатная квартира» |

Final translation state before acceptance:

~~~text
deterministic_validated units: 55,173
active batches:                     0
unresolved errors:                  0
leaf-blocked batches:               0
translated units:             644,744
~~~

Acceptance and coverage reported 55,173 newly accepted translations and `complete: true`, covering all 69,705 matched terms and all 79,397 frozen articles.

Verified output:

~~~text
articles:               79,397
ZIP members:               123
schema-validated banks:     39
SHA-256: 1ff1147705bcb5f39bc2906c1b7f7669d33204cad344b5fe193d67c1370b5daa
~~~

Run validation reported 644,744 accepted units, zero batch-membership mismatches, and zero blocking issues. The acceptance audit found exactly one accepted translation per unit and no active, unresolved, or leaf-blocked work. All 52 tests passed. `release_ready` remains false only because the optional review stage was intentionally omitted.

## Top-90k continuation results

The top-90k expansion used source run 13 and target run 14.

~~~text
requested rows:          90,000
unique terms:            80,556
matched terms:           77,688
skipped terms:            2,868
selected articles:       87,872
frequency mappings:     102,919
rank-80,001–90,000 unique terms:   8,633
rank-80,001–90,000 matched terms:  7,983
rank-80,001–90,000 skipped terms:    650
new articles beyond run 13:         8,475
translation units:      698,173
articles without units:   5,867
reused run-13 units:     644,744
new Luna units:           53,429
initial batches:           1,297
~~~

Four pools ran at concurrency 20 with prefixes `jpdb90k-pool1` through `jpdb90k-pool4`. Automatic retries and recursive splits validated 53,425 new units. Four exhausted singleton units were requeued, explicitly claimed, translated with fully Cyrillic botanical naming where necessary, and ingested through the standard validator:

| Source | Accepted Russian target |
|---|---|
| See also | См. также |
| ramie (Boehmeria nivea var. candicans) | рами (бемерия снежная, разновидность беловатая) |
| ramie (Boehmeria nivea var. nipononivea) | рами (бемерия снежная, разновидность японская) |
| English: "plus minus zero" | из англ. «плюс-минус ноль» |

Final translation state before acceptance:

~~~text
deterministic_validated units: 53,429
active batches:                     0
unresolved errors:                  0
leaf-blocked batches:               0
translated units:             698,173
~~~

Acceptance and coverage reported 53,429 newly accepted translations and `complete: true`, covering all 77,688 matched terms and all 87,872 frozen articles.

Verified output:

~~~text
articles:               87,872
ZIP members:               140
schema-validated banks:     42
SHA-256: e660db82617968ebc6e4ef63361609c9b34e9fab26c8c441cc5ce3834d7001c2
~~~

Run validation reported 698,173 accepted units, zero batch-membership mismatches, and zero blocking issues. The acceptance audit found exactly one accepted translation per unit and no active, unresolved, or leaf-blocked work. All 52 tests passed. `release_ready` remains false only because the optional review stage was intentionally omitted.

## Top-100k continuation results

The top-100k expansion used source run 14 and target run 15.

~~~text
requested rows:         100,000
unique terms:            89,142
matched terms:           85,514
skipped terms:            3,628
selected articles:       96,081
frequency mappings:     112,833
rank-90,001–100,000 unique terms:   8,586
rank-90,001–100,000 matched terms:  7,826
rank-90,001–100,000 skipped terms:    760
new articles beyond run 14:          8,209
translation units:      748,745
articles without units:   6,504
reused run-14 units:     698,173
new Luna units:           50,572
initial batches:           1,269
~~~

Four pools ran at concurrency 20 with prefixes `jpdb100k-pool1` through `jpdb100k-pool4`. Automatic retries and recursive splits validated 50,566 new units. Six exhausted singleton units were requeued, explicitly claimed, translated with fully Cyrillic taxonomy and etymology where necessary, and ingested through the standard validator:

| Source | Accepted Russian target |
|---|---|
| word usually written using kana alone | слово обычно записывается только каной |
| See also | См. также |
| Elatostema umbellatum var. majus (variety of plant related to the nettles) | элатостема зонтичная, разновидность крупная (растение, родственное крапиве) |
| English: "doctor heli(copter)" | из англ. «врачебный вертолёт» |
| English: "body buil(ding)" | из англ. «построение тела» |
| Elatostema umbellatum var. majus (glossary set) | элатостема зонтичная, разновидность крупная (растение, родственное крапиве) |

Final translation state before acceptance:

~~~text
deterministic_validated units: 50,572
active batches:                     0
unresolved errors:                  0
leaf-blocked batches:               0
translated units:             748,745
~~~

Acceptance and coverage reported 50,572 newly accepted translations and `complete: true`, covering all 85,514 matched terms and all 96,081 frozen articles. The remaining 3,628 unique JPDB terms were absent from Jitendex and therefore correctly skipped.

Verified output:

~~~text
articles:               96,081
ZIP members:               168
schema-validated banks:     45
SHA-256: fe6024a2fa0ef1a1a589ec7ce94700f1810da40fb0c0049d9919c1a036cda622
~~~

Run validation reported 748,745 accepted units, zero batch-membership mismatches, and zero blocking issues. The acceptance audit found exactly one accepted translation per unit and no active, unresolved, or leaf-blocked work. All 52 tests passed. `release_ready` remains false only because the optional review stage was intentionally omitted.

## Known exporter limitation

src/jitendex_ru/build_dictionary.py currently hardcodes these values for every frequency-scoped run:

~~~text
title:       Jitendex JPDB 5k — русский
revision:    ...-jpdb-5k-ru
description: ...верхним 5000 строкам JPDB...
~~~

The top-10k through top-100k archives contain the correct cumulative articles and pass coverage/schema verification, but their internal titles and descriptions still say 5k.

Do not treat metadata as scope-size-aware until frequency-scope identity is frozen per run and the exporter derives the label from that frozen identity rather than a hardcoded string or the mutable live frequency_term table.

## Optional human Yomitan smoke gate

The orchestrator did not perform this UI-dependent step. For a full release gate, import the ZIP into a clean Yomitan profile, run all required lookup/render checks, create the smoke report, then record it:

~~~bash
translationctl --config config.luna.clean-v1.toml \
  record-yomitan-smoke \
  '<SMOKE_REPORT_PATH>' \
  --actor '<ACTOR>'
~~~

Only that human-observed gate marks the run state complete.
