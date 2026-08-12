# RUN — JPDB Luna Translation Orchestration Runbook

RUN-1 — This is the operational source of truth for continuing Russian Jitendex translation in cumulative JPDB-frequency batches. It contains goals, pinned inputs, provenance rules, and repeatable commands. Completed-run measurements and incident details belong in [JPDB_LUNA_RUN_HISTORY.md](JPDB_LUNA_RUN_HISTORY.md), not here.

## RUN-GOAL — Goal and completion criteria

RUN-GOAL-1 — Process JPDB in cumulative 10,000-rank increments using Luna medium, reuse every compatible accepted translation from the preceding run, and export a verified Russian Yomitan dictionary after each increment.

RUN-GOAL-2 — For each target limit:

RUN-GOAL-3 — select JPDB ranks `1..TARGET_LIMIT`;

RUN-GOAL-4 — match exact normalized JPDB spellings against Jitendex expressions and readings;

RUN-GOAL-5 — skip JPDB terms absent from Jitendex;

RUN-GOAL-6 — translate every remaining translatable Jitendex unit with Luna;

RUN-GOAL-7 — store model, prompt, source, unit, attempt, acceptance, and export provenance in SQLite;

RUN-GOAL-8 — prove exactly one accepted translation per unit and zero unresolved blocking issues;

RUN-GOAL-9 — build and verify the cumulative Yomitan ZIP before changing the live JPDB scope.

RUN-GOAL-10 — The current planned sequence is top 150k, 160k, and so on through top 300k. The final top-300k run additionally requires the deterministic tag/terminology canonicalization gate described below.

## RUN-STOP — Current stopping point

RUN-STOP-1 — The last completed cumulative scope is **JPDB top 140k**, run **19**.

~~~text
JPDB rank range:               1–140,000
unique JPDB terms:               123,386
matched JPDB terms:              115,077
skipped because absent:            8,309
frozen Jitendex articles:         126,943
accepted translation units:       932,516
verified export: dist/jitendex-jpdb-140k-ru-luna-clean-v1.zip
SHA-256: 73c13b9df09a24dd2af35763ff40aa29d515003131723208030e1ac972d91007
~~~

RUN-STOP-2 — The next run should therefore use:

~~~text
source run:   19
target scope: 150,000
concurrency:  80 (four pools of 20)
~~~

RUN-STOP-3 — The detailed evidence for completed scopes is in [JPDB_LUNA_RUN_HISTORY.md](JPDB_LUNA_RUN_HISTORY.md).

## RUN-SRC — Pinned sources and runtime

RUN-SRC-1 — Run commands from the repository root:

~~~text
/Users/iuriikatkov/Documents/ChatGPT/jitendex-translations
~~~

RUN-SRC-2 — Environment:

~~~bash
export PYTHONPATH=src
export UV_CACHE_DIR=/private/tmp/jitendex-uv-cache
~~~

RUN-SRC-3 — Authoritative configuration and state:

| Purpose | Value |
|---|---|
| Configuration | `config.luna.clean-v1.toml` |
| SQLite database | `work/progress.sqlite3` |
| Jitendex version | `2026.07.09.0` |
| Jitendex URL | `https://github.com/stephenmk/stephenmk.github.io/releases/download/2026.07.09.0/jitendex-yomitan.zip` |
| Jitendex SHA-256 | `807d911114af9d2154d270702972aafb2b6a6c2dc2400afa98db870d035c1a0b` |
| JPDB frequency URL | `https://github.com/MarvNC/jpdb-freq-list/releases/download/2022-05-09/Freq.JPDB_2022-05-10T03_27_02.930Z.zip` |
| JPDB local file | `work/downloads/Freq.JPDB_2022-05-10T03_27_02.930Z.zip` |
| JPDB SHA-256 | `5bda39a9e3b443b02199435ea723aa0555c891d1ce2c92ea7680163b72b07a0e` |
| Legacy Kaishi baseline | `v2.4.1`, configured in `config.luna.clean-v1.toml` |
| Extractor | `extractor-v2` |
| Pipeline | `lexicographer-v2` |

RUN-SRC-4 — Verify pinned local inputs before a fresh import:

~~~bash
shasum -a 256 work/downloads/jitendex-yomitan.zip
shasum -a 256 work/downloads/Freq.JPDB_2022-05-10T03_27_02.930Z.zip
~~~

RUN-SRC-5 — The configured `acquire` command downloads and verifies Jitendex and the legacy Kaishi source. JPDB is selected from the separately pinned ZIP above.

## RUN-MODEL — Model and prompt

RUN-MODEL-1 — Translation batches must use exactly:

~~~text
model:            gpt-5.6-luna
reasoning effort: medium
prompt:           prompts/translate_luna_clean_v1.txt
prompt SHA-256:   f6ed47cfeeb244e5668a774383f4a073344ec4d5c08a0a446771db227a8cb78a
transport:        bundled Codex CLI in a read-only temporary workspace
~~~

RUN-MODEL-2 — The model and effort are read from `[models.translation]` in `config.luna.clean-v1.toml`. Do not substitute a different prompt, model, effort, or configuration without intentionally creating a new provenance identity.

RUN-MODEL-3 — The optional Terra review pass is not part of this workflow. Consequently, `translationctl validate` reports `release_ready: false` and `reviewed_units: 0` even when a Luna-only run is otherwise complete. The authoritative blocking gate is `blocking_issues: 0` plus the database and archive audits below.

## RUN-DB — Populate a new database

RUN-DB-1 — Do this only for a genuinely new database. Continuing batches should use the existing `work/progress.sqlite3`.

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml init-db

PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml acquire

PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml import-sources
~~~

RUN-DB-2 — This initializes the schema, downloads and hash-verifies configured sources, records immutable `source_snapshot` rows, imports Jitendex articles/tags, and imports the legacy Kaishi provenance baseline.

RUN-DB-3 — Download JPDB separately if its pinned ZIP is missing:

~~~bash
curl -L \
  'https://github.com/MarvNC/jpdb-freq-list/releases/download/2022-05-09/Freq.JPDB_2022-05-10T03_27_02.930Z.zip' \
  -o work/downloads/Freq.JPDB_2022-05-10T03_27_02.930Z.zip

shasum -a 256 work/downloads/Freq.JPDB_2022-05-10T03_27_02.930Z.zip
~~~

RUN-DB-4 — Do not proceed unless the JPDB hash matches the pinned value.

RUN-DB-5 — The current database schema is version 7. Initialization upgrades the old frequency tables in place. The upgrade preserves every term and mapping, adds `frequency_source`, and changes frequency identity from rank-based to term-based so tied ranks are safe.

RUN-DB-6 — `frequency_source` records one active snapshot per stable source key, including its SHA-256, rank limit, local path, parser version, and source metadata. `frequency_term` uses `(source, source_sha256, term)` as its primary key. Rank is data and may repeat. `frequency_article` uses `(source, source_sha256, term, article_id)` as its primary key and references the exact term row.

RUN-DB-7 — Before a production upgrade, make an online SQLite backup and run `PRAGMA quick_check`. After the upgrade, require schema version 7, zero rows from `PRAGMA foreign_key_check`, and unchanged counts for the preceding frozen run.

## RUN-PROV — Provenance: how JPDB words and translations are marked

RUN-PROV-1 — Always use `select-jpdb-scope`; never mark `article.selected` or populate provenance tables manually.

RUN-PROV-2 — The selector records the active source hash, rank limit, local path, parser version, and metadata in `frequency_source`.

RUN-PROV-3 — every deduplicated JPDB spelling in `frequency_term` with `source='jpdb'`, the JPDB ZIP SHA-256, earliest rank, exact term, and `matched` flag;

RUN-PROV-4 — every Jitendex match in `frequency_article` with the same source/hash/term identity, retained rank, `article_id`, and `match_kind` (`expression` or `reading`);

RUN-PROV-5 — the selected Jitendex articles for unit extraction.

RUN-PROV-6 — `extract-units` then creates a run whose identity pins the Jitendex/Kaishi snapshots, selection hash, extractor, prompt hash, review-prompt hash, terminology hash, pipeline, and batching limits. It freezes selected articles and structural fingerprints in `run_article`. Each `translation_unit` pins its article, JSON pointer, role, English source text/hash, and protected tokens.

RUN-PROV-7 — The Luna runner records each attempt's worker, requested/effective model, reasoning effort, prompt hash, transport, request/thread identifiers, token counts, latency, response path, and outcome. Accepted outputs are immutable `translation` rows linked back to the attempt and unit. A partial unique index guarantees at most one accepted translation for each `(run_id, unit_id)`.

RUN-PROV-8 — `reuse-translations` preserves provenance rather than copying by text alone: reuse requires the same article ID, JSON pointer, role, source SHA-256, and an accepted source-run translation. `build` and `verify` record the output path, manifest hash, ZIP hash, member hashes, and verification state in `export` and `export_file`.

RUN-PROV-9 — Useful provenance inspection:

~~~bash
sqlite3 -header -column work/progress.sqlite3 "
SELECT source,source_sha256,COUNT(*) terms,MIN(rank) min_rank,MAX(rank) max_rank,
       SUM(matched) matched,SUM(matched=0) skipped
FROM frequency_term
GROUP BY source,source_sha256;

SELECT id,jitendex_snapshot_id,selection_sha256,extractor_version,
       prompt_sha256,terminology_sha256,pipeline_version,created_at
FROM run ORDER BY id DESC LIMIT 5;
"
~~~

## RUN-BATCH — Repeatable procedure for every next 10k batch

RUN-BATCH-1 — The examples below assume the next top-150k run. For later runs, change only the source run, target limit, target run ID, worker prefixes, and output filename.

RUN-BATCH-2 — Set the scope-specific values once:

~~~bash
export JPDB_SOURCE_RUN_ID=19
export JPDB_LIMIT=150000
export JPDB_SCOPE_LABEL=150k
~~~

### RUN-BATCH-S1 — 1. Protect the previous scope

RUN-BATCH-S1-1 — Before selecting a new scope, confirm the previous run has a verified export and complete coverage. `select-jpdb-scope` replaces the live JPDB frequency tables and `article.selected`; frozen prior runs remain intact through `run_article`, but their live coverage report must be captured first.

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml \
  report-jpdb-coverage --run-id "$JPDB_SOURCE_RUN_ID"

sqlite3 -header -column work/progress.sqlite3 "
SELECT id,run_id,output_path,zip_sha256,verified
FROM export WHERE run_id=$JPDB_SOURCE_RUN_ID ORDER BY id DESC LIMIT 1;
"
~~~

RUN-BATCH-S1-2 — Do not change scope unless coverage is complete and `verified=1`.

### RUN-BATCH-S2 — 2. Select the new cumulative JPDB scope

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml \
  select-jpdb-scope \
  work/downloads/Freq.JPDB_2022-05-10T03_27_02.930Z.zip \
  --limit "$JPDB_LIMIT"
~~~

RUN-BATCH-S2-1 — The selection is cumulative. Top 150k includes top 140k; do not subtract the earlier ranks manually. Duplicate JPDB spellings keep their earliest rank. Terms absent from Jitendex remain in `frequency_term` with `matched=0` and are intentionally skipped.

### RUN-BATCH-S3 — 3. Create the run and extract units

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml extract-units
~~~

RUN-BATCH-S3-1 — Copy the returned `run_id` and use it consistently below. If identical inputs resolve to an existing run, verify that this is intended. A genuinely new clean rerun of an identical scope requires an intentional change to `batch.clean_run_nonce` in the configuration.

~~~bash
export JPDB_RUN_ID='<RETURNED_RUN_ID>'

PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml \
  verify-run-identity \
  --run-id "$JPDB_RUN_ID" \
  --baseline-run-id "$JPDB_SOURCE_RUN_ID"
~~~

### RUN-BATCH-S4 — 4. Reuse the preceding cumulative run

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml \
  reuse-translations \
  --source-run-id "$JPDB_SOURCE_RUN_ID" \
  --target-run-id "$JPDB_RUN_ID"
~~~

RUN-BATCH-S4-1 — This is what prevents double-translation. Only the newly selected delta and any structurally changed units remain `ready`.

### RUN-BATCH-S5 — 5. Create Luna batches

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml \
  make-batches --run-id "$JPDB_RUN_ID"
~~~

RUN-BATCH-S5-1 — Configured limits are six articles, 24,576 serialized bytes, and 100 units per normal batch, with explicit singleton and hard article ceilings. Manifests are written to `work/inbox` and include exact ordered unit IDs, source hashes, protected tokens, context, and any known canonical tag guidance.

### RUN-BATCH-S6 — 6. Run Luna medium at concurrency 80

RUN-BATCH-S6-1 — Start four persistent terminal/PTTY sessions, each with concurrency 20:

~~~bash
python scripts/run_codex_batches.py \
  --config config.luna.clean-v1.toml \
  --run-id "$JPDB_RUN_ID" \
  --kind translation \
  --concurrency 20 \
  --worker-prefix "jpdb${JPDB_SCOPE_LABEL}-pool1"
~~~

RUN-BATCH-S6-2 — Repeat with pool suffixes `pool2`, `pool3`, and `pool4`. The runner claims work, invokes Luna with the pinned prompt/schema, writes responses to `work/outbox`, validates them, ingests valid translations, and recursively retries/splits failures until no ready work remains.

RUN-BATCH-S6-3 — The runner has no explicit subprocess timeout. Use bounded monitoring and recover only workers proven stalled.

### RUN-BATCH-S7 — 7. Monitor authoritative database state

~~~bash
sqlite3 -cmd '.timeout 5000' -header -column work/progress.sqlite3 "
SELECT state,COUNT(*) batches,SUM(unit_count) units
FROM batch WHERE run_id=$JPDB_RUN_ID
GROUP BY state ORDER BY state;

SELECT COUNT(*) unresolved_errors
FROM validation_issue
WHERE run_id=$JPDB_RUN_ID
  AND severity='error' AND resolved_at IS NULL;

SELECT COUNT(*) leaf_blocked
FROM batch b
WHERE b.run_id=$JPDB_RUN_ID
  AND b.state='blocked'
  AND NOT EXISTS (
    SELECT 1 FROM audit_event ae
    WHERE ae.event_type='split' AND ae.entity_id=b.id
  );
"
~~~

RUN-BATCH-S7-1 — `ready`, `leased`, and `retryable` are unfinished. `deterministic_validated` is complete work awaiting acceptance. A blocked parent with a split audit event is superseded; only terminal blocked leaves require attention.

RUN-BATCH-S7-2 — Allow automatic retry/split isolation to finish before repairing terminal leaves. Recover a genuinely stalled lease only after stopping its owning process, recording the attempt as interrupted, and requeueing it. The exact recovery examples from prior incidents are preserved in [JPDB_LUNA_RUN_HISTORY.md](JPDB_LUNA_RUN_HISTORY.md).

### RUN-BATCH-S8 — 8. Repair only genuine validation failures

RUN-BATCH-S8-1 — Targeted repairs must go through normal `claim` and `ingest-response` provenance. Do not insert accepted translations directly in SQLite.

RUN-BATCH-S8-2 — Repair invalid shapes, wrong unit sets/order, empty output, markup/control characters, excessive untranslated English, invalid glossary arrays, and genuinely lost protected tokens. Do **not** repair or requeue an otherwise valid Russian result solely because its canonical tag/terminology wording differs; that difference is deferred to the final deterministic canonicalization pass.

### RUN-BATCH-S9 — 9. Prove translation work is drained

RUN-BATCH-S9-1 — Required before acceptance:

~~~text
active ready/leased/retryable batches: 0
terminal blocked leaves:               0
unresolved validation errors:          0
ready translation units:               0
translated + already accepted units:   total run units
~~~

### RUN-BATCH-S10 — 10. Accept deterministic translations

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml \
  accept-translations --run-id "$JPDB_RUN_ID"
~~~

RUN-BATCH-S10-1 — Then prove every unit has exactly one accepted translation:

~~~bash
sqlite3 -header -column work/progress.sqlite3 "
SELECT COUNT(*) units_without_exactly_one_accept
FROM translation_unit tu
WHERE tu.run_id=$JPDB_RUN_ID
  AND (
    SELECT COUNT(*) FROM translation t
    WHERE t.run_id=tu.run_id AND t.unit_id=tu.id AND t.accepted=1
  )<>1;
"
~~~

RUN-BATCH-S10-2 — The required result is zero.

### RUN-BATCH-S11 — 11. Run the cumulative coverage gate

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml \
  report-jpdb-coverage --run-id "$JPDB_RUN_ID"
~~~

RUN-BATCH-S11-1 — Required: `complete: true`. Every matched JPDB term and every frozen selected article must be fully accepted. Unmatched JPDB terms are expected skips, not gaps.

### RUN-BATCH-S12 — 12. Build and verify the Yomitan dictionary

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml \
  build \
  --run-id "$JPDB_RUN_ID" \
  --output "dist/jitendex-jpdb-${JPDB_SCOPE_LABEL}-ru-luna-clean-v1.zip"

PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml \
  verify "dist/jitendex-jpdb-${JPDB_SCOPE_LABEL}-ru-luna-clean-v1.zip"
~~~

RUN-BATCH-S12-1 — Verification checks index placement, duplicate members, target language, media, frozen article count, recorded export hash, and every pinned Yomitan term-bank schema.

RUN-BATCH-S12-2 — Export metadata is scope-aware. `build_dictionary.py` derives the JPDB or combined-frequency title, revision, and description from the active `frequency_source` rows that map into the frozen run. Inspect `index.json` after every build and require the label to match the intended scope.

### RUN-BATCH-S13 — 13. Validate, test, and audit

~~~bash
PYTHONPATH=src .venv/bin/pytest -q

PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml \
  validate --run-id "$JPDB_RUN_ID"

shasum -a 256 "dist/jitendex-jpdb-${JPDB_SCOPE_LABEL}-ru-luna-clean-v1.zip"
~~~

RUN-BATCH-S13-1 — Final database audit:

~~~bash
sqlite3 -header -column work/progress.sqlite3 "
SELECT COUNT(*) unique_terms,SUM(matched) matched_terms,SUM(matched=0) skipped_terms,
       MIN(rank) min_rank,MAX(rank) max_rank
FROM frequency_term WHERE source='jpdb';

SELECT COUNT(*) missing_mapped_run_articles
FROM frequency_article fa
WHERE fa.source='jpdb'
  AND NOT EXISTS (
    SELECT 1 FROM run_article ra
    WHERE ra.run_id=$JPDB_RUN_ID AND ra.article_id=fa.article_id
  );

SELECT COUNT(*) units FROM translation_unit WHERE run_id=$JPDB_RUN_ID;

SELECT COUNT(*) accepted_translations,COUNT(DISTINCT unit_id) accepted_units
FROM translation WHERE run_id=$JPDB_RUN_ID AND accepted=1;

SELECT COUNT(*) unresolved_errors
FROM validation_issue
WHERE run_id=$JPDB_RUN_ID AND severity='error' AND resolved_at IS NULL;

SELECT id,run_id,output_path,zip_sha256,verified
FROM export WHERE run_id=$JPDB_RUN_ID ORDER BY id DESC LIMIT 1;
"
~~~

RUN-BATCH-S13-2 — Required: selected rank maximum equals the target limit; missing mapped articles, units without exactly one acceptance, unresolved errors, active batches, and terminal blocked leaves are all zero; accepted units equal total units; the latest export has `verified=1`; the filesystem SHA-256 equals the recorded export hash.

RUN-BATCH-S13-3 — Record the completed run's measurements, repairs, validation output, and verified archive hash in [JPDB_LUNA_RUN_HISTORY.md](JPDB_LUNA_RUN_HISTORY.md). Update only the stopping-point section of this runbook.

## RUN-TAG — Terminology and tag policy through top 300k

RUN-TAG-1 — Known tag mappings remain strong generation guidance in Luna manifests, but canonical wording differences do not block intermediate batches. A structured tag missing from the approved catalog also does not stop batch creation. All other deterministic validation remains active.

RUN-TAG-2 — Because English tag identity maps one-to-one to canonical Russian output, tag normalization is fully algorithmic. After the final top-300k cumulative run is accepted, but before its definitive export:

RUN-TAG-3 — Run one deterministic normalizer over the final run only.

RUN-TAG-4 — Resolve structured tag `content` and `title` by stable `(category, code, field)` identity, not by ambiguous visible text.

RUN-TAG-5 — Replace them with exact approved `label_ru` and `description_ru` values.

RUN-TAG-6 — Replace any other whole-leaf field carrying exact `required_terminology.target_text` with that exact target.

RUN-TAG-7 — Fail closed on missing, duplicate, or ambiguous mappings.

RUN-TAG-8 — Never do blind substring replacement inside definitions, glossary arrays, examples, or explanatory prose.

RUN-TAG-9 — Record changed values with final-run provenance rather than rewriting historical source runs.

RUN-TAG-10 — Re-run deterministic validation, acceptance invariants, tests, build, and verify.

RUN-TAG-11 — The canonicalization command is not implemented yet. It must be implemented and tested before the final top-300k export; it is not required to continue the intermediate 150k–290k translation batches.

## RUN-SMOKE — Optional human Yomitan smoke gate

RUN-SMOKE-1 — For a full human release gate, import the verified ZIP into a clean Yomitan profile, exercise representative lookups and rendering, save a smoke report, and record it:

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.clean-v1.toml \
  record-yomitan-smoke '<SMOKE_REPORT_PATH>' --actor '<ACTOR>'
~~~

RUN-SMOKE-2 — This UI-dependent check is optional for intermediate cumulative archives.
