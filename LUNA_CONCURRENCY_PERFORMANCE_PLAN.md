# LCP — Luna PostgreSQL online-tuning plan

LCP-1 — Status: complete. Date: 2026-08-14. Productive PostgreSQL tuning selected concurrency 100. The earlier disposable experiment matrix remains cancelled.

## LCP-GOAL — Decision to make

LCP-GOAL-1 — Find a safe Luna concurrency above 80 that improves fully translated headwords per minute while every response translates useful production work.

LCP-GOAL-2 — Keep the model, medium reasoning, Luna v4 prompt, batch limits, validator, and runner revision fixed. A concurrency experiment changes only the declared experiment variables.

LCP-GOAL-3 — Use the authoritative PostgreSQL database only. Do not spend Luna allowance on SQLite comparison stages.

LCP-GOAL-4 — Keep one database coordinator. Change database-worker parallelism only if database duty cycle or ingestion delay measurably limits model replacement.

## LCP-NOW — Current boundary

LCP-NOW-1 — PostgreSQL is authoritative. The next tuning run is also the next productive translation batch, so accepted results, attempts, audits, and exports remain normal production history.

LCP-NOW-2 — Finish local tests, the parity verifier, recovery checks, and online-observability preparation without Luna usage before starting the next translation batch.

LCP-NOW-3 — Do not return production to SQLite. Keep the completed SQLite migration source read-only as historical recovery evidence.

LCP-NOW-4 — Runs 46, 47, and 49 are complete and verified. The fixed windows measured 275.9 headwords per minute at 70, 300.0 at 80, 311.9 at 90, 346.0 at 100, and 332.0 at 110. Run 48 was never created because its PostgreSQL sequence value was consumed by a rolled-back transaction.

## LCP-SAFE — Protect the active translation

LCP-SAFE-1 — Do not run a disposable Luna benchmark. Concurrency changes happen only inside an authorized productive PostgreSQL translation run.

LCP-SAFE-2 — Before the next batch, require the prior run to have zero unfinished batches, zero unresolved blocking errors, complete accepted-unit coverage, and a verified Yomitan export.

LCP-SAFE-3 — Before starting the next batch, verify zero stale claimed attempts and no other production writer. Change concurrency only between fixed-concurrency runner sessions after the prior session stops new claims and drains every active request.

LCP-SAFE-4 — Retain the verified PostgreSQL backup and the read-only SQLite migration source. Record their paths, hashes, versions, run IDs, accepted-unit counts, and verified export hashes.

LCP-SAFE-5 — Use normal production run IDs and normal isolated run directories. Every claimed item must belong to the next real Jitendex batch.

LCP-SAFE-6 — Keep all tuning attempts, translations, audit events, and exports in production history because they are productive work. Store only small metric summaries outside the database.

## LCP-ARCH — Minimal database boundary

LCP-ARCH-1 — Add one small database module that exposes connection checkout, transaction scope, row mappings, backend error classification, and schema migration. Do not add an ORM or domain repository layer.

LCP-ARCH-2 — Keep pipeline functions operating on a connection-like object with `execute`, `executemany`, `commit`, `rollback`, and mapping-style rows. This limits changes to current call sites.

LCP-ARCH-3 — Put backend selection in configuration. SQLite uses a path. PostgreSQL uses a URL read from an environment variable named by the configuration. Never store credentials in TOML, logs, manifests, or performance results.

LCP-ARCH-4 — Keep PostgreSQL explicit in the production configuration. The missing-setting SQLite fallback remains only for compatibility and tests.

LCP-ARCH-5 — Use a maintained PostgreSQL DB-API driver and its small connection pool. Pin the driver and PostgreSQL major version. Record both versions in migration and online-tuning reports.

LCP-ARCH-6 — A Luna model request must never hold a database connection. Check out a connection only for claim, ingest, retry, progress, or audit work and return it immediately after commit or rollback.

## LCP-PREP — Fast productive preparation

LCP-PREP-1 — A cumulative PostgreSQL run copies unchanged `run_article` and `translation_unit` metadata from the verified source run. It parses Jitendex JSON only for newly selected articles.

LCP-PREP-2 — Stream newly extracted rows through PostgreSQL `COPY`. Reuse accepted translations with set-based `INSERT … SELECT` and `UPDATE` statements instead of Python row loops.

LCP-PREP-3 — Refresh PostgreSQL statistics after scope selection, extraction, reuse, and batch creation. Record each phase time through `scripts/prepare_luna_run.py`.

LCP-PREP-4 — Preserve deterministic unit IDs, source hashes, structural fingerprints, accepted-translation provenance, SQLite compatibility, and all pre-Luna integrity gates.

## LCP-COMPAT — SQL compatibility work

LCP-COMPAT-1 — Move the SQLite schema and embedded upgrades out of `db.py` into numbered SQLite migrations. Add equivalent numbered PostgreSQL migrations. Both paths update `schema_meta` and produce the same logical schema version.

LCP-COMPAT-2 — Replace direct `sqlite3.Connection` and `sqlite3.Row` annotations with small project protocols. Keep SQLite-specific setup inside the SQLite adapter.

LCP-COMPAT-3 — Handle parameter placeholders in the database adapter. Application code must use one project parameter style; the adapter converts it for SQLite or PostgreSQL.

LCP-COMPAT-4 — Replace every `INSERT OR IGNORE` with explicit conflict handling. Replace `INSERT OR REPLACE` with an upsert that updates only the intended columns. Do not use delete-and-reinsert semantics.

LCP-COMPAT-5 — Replace `cursor.lastrowid` with `INSERT ... RETURNING id` through the adapter.

LCP-COMPAT-6 — Map SQLite `BEGIN IMMEDIATE` to a normal PostgreSQL transaction. Operations that need row ownership must lock the exact rows instead of locking all writers.

LCP-COMPAT-7 — Keep SQLite PRAGMAs, schema introspection, `executescript`, and integrity checks inside the SQLite implementation. PostgreSQL uses catalog queries and separate statements.

LCP-COMPAT-8 — Replace SQLite-only busy error detection with backend error categories: transient lock or serialization error, connection loss, constraint error, and permanent SQL error.

LCP-COMPAT-9 — Retry only complete idempotent database operations. Never retry half of an ingestion transaction.

LCP-COMPAT-10 — Add a source check that fails when new SQLite-only SQL appears outside the backend and migration modules.

## LCP-SCHEMA — PostgreSQL schema rules

LCP-SCHEMA-1 — Preserve every table, column, primary key, foreign key, check, unique constraint, partial unique index, immutable-history rule, and audit field from SQLite.

LCP-SCHEMA-2 — Use generated identity columns for PostgreSQL integer IDs that SQLite currently assigns. Allow explicit IDs during migration, then reset each sequence above the copied maximum.

LCP-SCHEMA-3 — Use `timestamptz` for timestamps. Parse every copied SQLite timestamp as UTC and reject ambiguous values. Use database time for lease creation and expiry.

LCP-SCHEMA-4 — Keep canonical JSON payloads as text during the first migration. This preserves hashes and byte-for-byte parity. A later JSONB migration is separate work.

LCP-SCHEMA-5 — Keep current integer zero-or-one fields during the first migration. Converting them to PostgreSQL booleans is separate work after parity.

LCP-SCHEMA-6 — Recreate immutable-history triggers with PostgreSQL trigger functions. Test that update and delete still fail.

LCP-SCHEMA-7 — Create indexes for every claim, progress, validation, export, and run-integrity query before performance testing.

## LCP-CLAIM — Concurrent claim semantics

LCP-CLAIM-1 — Claim one eligible batch in a short transaction using `FOR UPDATE SKIP LOCKED`. The candidate order must remain deterministic.

LCP-CLAIM-2 — Update the batch lease and insert the attempt and audit event in the same transaction. Return the claimed row only after the transaction commits.

LCP-CLAIM-3 — Use database time plus an interval for lease expiry. Do not compare application clocks from different processes.

LCP-CLAIM-4 — Preserve exact lease-token compare-and-set checks for ingestion, interruption, and recovery. A stale worker must not change a newer claim.

LCP-CLAIM-5 — Make response ingestion, accepted attempt state, deterministic batch state, translation rows, unit status, and audit events one transaction.

LCP-CLAIM-6 — Make retry or split state changes atomic and idempotent. Concurrent coordinators must not create duplicate child batches.

LCP-CLAIM-7 — Use `READ COMMITTED` initially. Add stronger isolation only for a transaction with a demonstrated invariant that row locks and unique constraints cannot protect.

LCP-CLAIM-8 — Base the implementation on the PostgreSQL locking clause documentation: [SELECT locking clause](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE).

## LCP-POOL — Connection use

LCP-POOL-1 — The current runner has one coordinator and does not need one database connection per Luna translator.

LCP-POOL-2 — Start PostgreSQL preparation with a pool maximum of four connections and a finite checkout timeout. This supports the runner, progress reads, and administrative checks without hiding a connection leak.

LCP-POOL-3 — Record pool checkout wait, connections in use, transaction duration, claim duration, and ingestion duration.

LCP-POOL-4 — Increase the pool only if a later approved database-worker experiment adds concurrent database work and shows pool waits. Set the pool maximum to database workers plus two, then measure it.

## LCP-ART — Preparation artifacts

LCP-ART-1 — Add numbered PostgreSQL DDL under `migrations/postgresql/` and numbered SQLite DDL under `migrations/sqlite/`.

LCP-ART-2 — Add `scripts/migrate_sqlite_to_postgresql.py` for a one-way offline copy. It must refuse to run when the source has claimed attempts or unfinished production work unless a clearly named disposable-test flag is present.

LCP-ART-3 — Add `scripts/verify_database_parity.py` for counts, identities, constraints, normalized row hashes, run fingerprints, and dictionary build parity.

LCP-ART-4 — Retain `scripts/prepare_luna_benchmark.py` only as local migration and harness evidence. Do not use its corpus for Luna requests.

LCP-ART-5 — Retain `scripts/run_luna_benchmark.py` for dry local contract tests only. Add production-safe online window recording that cannot create, claim, or replay work by itself.

LCP-ART-6 — Store machine-readable online window results under `reports/luna_performance/`. Do not put credentials or complete translation payloads in results.

## LCP-PG-MIG — Offline migration procedure

LCP-PG-MIG-1 — Record the completed offline migration evidence: zero writers, zero claimed attempts, the PostgreSQL backup, and the read-only SQLite source required by LCP-SAFE-4.

LCP-PG-MIG-2 — Create an empty PostgreSQL database with the pinned server version and apply all PostgreSQL migrations from zero.

LCP-PG-MIG-3 — Copy tables in foreign-key dependency order with PostgreSQL `COPY` through the migration script. Stream values directly; do not create an editable CSV containing production data. See [PostgreSQL COPY](https://www.postgresql.org/docs/current/sql-copy.html).

LCP-PG-MIG-4 — Preserve explicit IDs, exact text, nulls, canonical JSON text, hashes, paths, attempt history, leases, audit events, and timestamps.

LCP-PG-MIG-5 — Reset every generated sequence after copy. The verifier must insert and roll back one row for each generated-ID table to prove the next value is safe.

LCP-PG-MIG-6 — Run PostgreSQL constraint validation and require zero orphaned foreign keys, duplicate unique identities, invalid checks, and mutable-history gaps.

LCP-PG-MIG-7 — Compare every table count and a deterministic normalized hash of every table. Normalize backend representation only for timestamps and row types; do not normalize stored text.

LCP-PG-MIG-8 — Compare run-history fingerprints, accepted translation identity and target hashes, attempt usage, audit events, unresolved validation issues, and export records.

LCP-PG-MIG-9 — Build the completed dictionary from SQLite and PostgreSQL and require the same ZIP SHA-256. Run Yomitan verification against the PostgreSQL build.

LCP-PG-MIG-10 — Run claim, concurrent claim, ingestion replay, lease expiry, retry, split, graceful interruption, killed worker, lost connection, and PostgreSQL restart tests on disposable migrated copies.

LCP-PG-MIG-11 — Keep the completed SQLite source unchanged and read-only after migration.

## LCP-OBS — Observability before online tuning

LCP-OBS-1 — Extend runner progress events with database backend, progress-query seconds, claim milliseconds, ingestion milliseconds, database retries, pool-wait milliseconds, and workers active.

LCP-OBS-2 — Keep headwords done, headwords remaining, and headwords per minute in every progress report.

LCP-OBS-3 — Record request count, request latency, input and output tokens, 429s, timeouts, transport failures, validation rejections, retries, splits, and worker memory.

LCP-OBS-4 — Record PostgreSQL snapshots from `pg_stat_activity`, `pg_locks`, `pg_stat_database`, and `pg_stat_statements`. Enable `pg_stat_statements` before the production run, not during a tuning window. See [PostgreSQL monitoring statistics](https://www.postgresql.org/docs/current/monitoring-stats.html).

LCP-OBS-5 — Define one JSON online-window schema before the production run. Reject a result missing its configuration, runner revision, production run ID, window ID, ordered-batch hash, start and end time, or required counters.

## LCP-METRIC — Primary and supporting metrics

LCP-METRIC-1 — The primary metric is `headwords_per_minute = newly completed headwords / measured wall-clock minutes`.

LCP-METRIC-2 — A headword is complete only when every article for its expression and reading is selected and every translation unit is accepted or belongs to a deterministically validated batch. This must use the same query as production progress reporting.

LCP-METRIC-3 — Acceptance is deferred in production, so accepted rows alone are not a valid live throughput metric.

LCP-METRIC-4 — Also record completed articles per minute, deterministically validated units per minute, and validated source characters per minute. These expose workload differences.

LCP-METRIC-5 — Record p50, p95, and p99 model latency; failure rates; duplicate-claim collisions; stale-lease rejections; database duty cycle; claim, ingestion, and progress-query time; pool and lock wait; memory pressure; swap growth; and peak memory.

LCP-METRIC-6 — A claim collision means two workers or coordinators contend for the same batch identity. `SKIP LOCKED` skips are normal and are not collisions. Record duplicate attempts, lease compare-and-set rejections, stale ingestion attempts, and unique-constraint conflicts separately.

## LCP-CORPUS — Productive work

LCP-CORPUS-1 — Do not freeze or duplicate a benchmark corpus. Use successive real items from the next production batch.

LCP-CORPUS-2 — Keep the production rule that all articles sharing an expression and reading stay together. A headword must never be split by a tuning window.

LCP-CORPUS-3 — Record headword count, article count, unit count, source characters, serialized bytes, and validation difficulty for every window. Use these fields to identify workload drift.

LCP-CORPUS-4 — Windows are consecutive parts of one productive run, not identical replays. Treat comparisons as online tuning evidence and state this limitation in the decision.

LCP-CORPUS-5 — Record the first and last batch IDs and a hash of the ordered batch IDs for each window. Do not copy translation payloads into metric reports.

LCP-CORPUS-6 — Keep the runner revision, prompt hash, model, medium reasoning, batch limits, machine, power state, and network fixed while changing concurrency.

## LCP-HARNESS — Online controls to implement

LCP-HARNESS-1 — Keep smooth launch timing and record requested and actual launch time for each request. Do not run a separate startup-spacing experiment.

LCP-HARNESS-2 — Add production-safe window markers for concurrency 80, 90, 100, and later approved steps. Each fixed-concurrency runner session records exact ramp, steady-window, drain, and end times.

LCP-HARNESS-3 — At a normal window boundary, stop new claims and drain active model requests so every successful response remains useful. Use lease requeue only for an emergency interruption, and prove every exact lease is recovered.

LCP-HARNESS-4 — Record the production run ID, runner revision, prompt hash, limits hash, window ID, concurrency, and ordered-batch hash for every online result.

LCP-HARNESS-5 — Add a preflight that verifies the intended production PostgreSQL database, the next production run ID, the normal run directories, one writer, and zero stale claims.

LCP-HARNESS-6 — After every drained window, require zero claimed attempts, zero leased batches, zero missing units, zero duplicate deterministic translations, and zero source-hash mismatches. Record unresolved blocking errors and do not increase concurrency until normal retry or repair resolves them. Require zero blocking errors at final run shutdown.

LCP-HARNESS-7 — Dry-run window recording and safety checks without Luna requests before the productive run. The dry run must not claim work.

## LCP-EXP0 — Baseline order

LCP-EXP0-1 — Start the next productive PostgreSQL translation batch at concurrency 80 only after the local readiness gates pass and the runbook preflight authorizes the new production run.

LCP-EXP0-2 — Skip SQLite benchmarking because PostgreSQL is authoritative.

LCP-EXP0-3 — After the initial ramp, record one clean fixed-duration PostgreSQL window of at least 90 steady seconds and at least 60 completed requests. The observed 80-worker interval completed 77 requests; 60 is a concurrency-neutral evidence floor for comparing 70, 80, and 90 without consuming the finite workload. All successful responses are ingested into production.

LCP-EXP0-4 — Before increasing concurrency, record headwords, articles, units, source characters, request latency, errors, claim collisions, stale-lease rejections, database duty cycle, lock and pool waits, claim and ingestion delay, worker memory, memory pressure, and swap growth.

## LCP-EXP1 — Find useful model concurrency

LCP-EXP1-1 — Increase only after the concurrency-80 window is clean, useful work remains, and current Codex allowance is sufficient for another window.

LCP-EXP1-2 — Increase in steps of ten: 80, 90, 100, and then 110 or higher only while the preceding step passes. Add new slots smoothly over 30 seconds, then replace each completion immediately.

LCP-EXP1-3 — Record at least 90 steady seconds and at least 60 completed requests at each concurrency. Run 46 had 761 batches before tuning, so this evidence bound preserves useful work for productive adjacent-step comparisons. Do not replay completed work or create a disposable comparison stage.

LCP-EXP1-4 — Exclude each 30-second ramp from the steady window. Close a window early only for a stop rule, exhausted work, or a usage boundary; do not use an incomplete window to justify an increase.

LCP-EXP1-5 — Stop increasing when headwords per minute fails to improve by at least 5%, 429s exceed 1%, timeouts plus transport failures exceed 2%, any database failure occurs, claim collisions or stale-lease rejections appear, memory pressure becomes red, swap grows continuously, or p95 latency rises by 50% without a throughput gain.

LCP-EXP1-6 — If workload drift makes two adjacent windows inconclusive, keep translating at the lower setting and record another productive window there. Choose the faster repeatable safe setting, not a one-off peak.

## LCP-EXP2 — Ramp behavior

LCP-EXP2-1 — Do not run a separate startup-spacing matrix.

LCP-EXP2-2 — Keep the 30-second smooth increase used by LCP-EXP1-2 unless logs show a service burst or synchronized replacement burst.

LCP-EXP2-3 — Add replacement jitter only when logs show synchronized bursts.

LCP-EXP2-4 — Record ramp errors and launch delays separately from the steady window so a harmful ramp remains visible.

LCP-EXP2-5 — Prefer the simpler current replacement behavior when jitter or a longer ramp does not improve errors or throughput.

## LCP-EXP3 — Database workers only if needed

LCP-EXP3-1 — Skip database-worker experiments unless online windows show sustained ingestion delay or database duty cycle limiting model replacement. Otherwise record that one coordinator remained sufficient.

LCP-EXP3-2 — If needed, compare one, four, and eight database workers at the chosen model concurrency. Keep claim and ingestion operations independent and preserve per-batch transactions.

LCP-EXP3-3 — Set pool maximum to database workers plus two. Stop increasing database workers when throughput does not improve by 3% or lock waits, deadlocks, pool waits, or ingestion retries increase.

## LCP-DECISION — Production setting

LCP-DECISION-1 — PostgreSQL remains authoritative. Local parity and recovery checks protect it; online tuning does not decide the database backend.

LCP-DECISION-2 — Keep a concurrency above 80 only after productive windows pass with zero missing units, zero duplicate accepted translations, zero source-hash mismatches, zero unrecovered claims, zero claim collisions, and zero unresolved blocking errors.

LCP-DECISION-3 — Keep one step below any observed service, database, or machine failure boundary.

LCP-DECISION-4 — If no clean online setting beats concurrency 80 by at least 5%, keep 80. Do not add scheduler complexity without measured throughput.

LCP-DECISION-5 — Record PostgreSQL and driver versions, pool size, model concurrency, ramp, raw window results, usage-boundary events, and the decision reason in run history before the following production run.

LCP-DECISION-6 — The concurrency-100 window improved headwords per minute by 15.3% over 80 and 10.9% over 90, kept p95 latency at 95.6 seconds, used 6.7% database duty, and passed all postflight integrity gates.

LCP-DECISION-7 — Run 49 tested concurrency 110 with user authorization. Its productive 90-second window reached 332.0 headwords and 1,909.3 units per minute, with p50 74.8 seconds, p95 99.1 seconds, 7.3% database duty, 196 MB peak memory, and zero database retries, collisions, stale leases, rate limits, timeouts, transport failures, missing units, duplicates, or hash mismatches. It was 4.0% slower in headwords per minute than concurrency 100, so concurrency 100 remains the recommendation.

## LCP-CUT — Cutover and rollback

LCP-CUT-1 — Database cutover is complete. There is no live migration and no dual writing.

LCP-CUT-2 — SQLite rollback is no longer valid because PostgreSQL has accepted production writes.

LCP-CUT-3 — On failure, stop and recover PostgreSQL from its audit trail or backup. Never silently return to SQLite.

LCP-CUT-4 — Retain the verified PostgreSQL backup and read-only SQLite migration source according to the project backup policy.

## LCP-READY — Gates before online tuning

LCP-READY-1 — The active production run is complete and has a verified export.

LCP-READY-2 — Database adapters and both migration paths pass the full test suite.

LCP-READY-3 — A disposable SQLite-to-PostgreSQL migration passes all count, hash, constraint, fingerprint, and ZIP parity checks.

LCP-READY-4 — Concurrent claim, interruption, restart, replay, retry, split, and connection-loss tests pass.

LCP-READY-5 — Online window records, the result schema, production safety preflight, and postflight are reviewed without Luna usage.

LCP-READY-6 — PostgreSQL version, driver version, configuration, backup procedure, and monitoring setup are recorded.

LCP-READY-7 — A final readiness report states the productive online ladder, expected request range, usage-limit handling, duration, PostgreSQL target, and exact stop conditions.

LCP-READY-8 — The user approved replacing the disposable matrix with productive PostgreSQL online tuning on 2026-08-13. Starting the next batch still follows the production runbook preflight.

## LCP-ORDER — Preparation order

LCP-ORDER-1 — First add the database configuration and minimal adapter while keeping SQLite behavior unchanged.

LCP-ORDER-2 — Then extract SQLite migrations and add PostgreSQL DDL plus backend contract tests.

LCP-ORDER-3 — Then implement PostgreSQL claim, ingest, retry, progress, audit, and export paths.

LCP-ORDER-4 — Then implement offline migration and parity verification.

LCP-ORDER-5 — Then pass recovery and concurrency correctness tests on disposable data.

LCP-ORDER-6 — Then implement online window recording, observability, and dry-run-only validation.

LCP-ORDER-7 — Finish local checks without Luna. Then follow the production runbook to start the next batch at concurrency 80 and tune through LCP-EXP0 and LCP-EXP1. Do not run the old disposable matrix.

## LCP-RESULT — Small result record

LCP-RESULT-1 — Record database and versions, runner revision, production run and window IDs, ordered-batch hash, model concurrency, ramp seconds, database workers, pool maximum, headwords per minute, articles per minute, units per minute, source characters per minute, request latency, 429 rate, failure rate, validation rejection rate, claim collisions, stale-lease rejections, database duty cycle, claim and ingestion delay, database and pool waits, retries, memory pressure, swap, and peak memory for each window.

LCP-RESULT-2 — End with one production recommendation and the measured percentage improvement over the productive PostgreSQL concurrency-80 baseline.

## LCP-USAGE — Codex allowance

LCP-USAGE-1 — Before the run and before every increase, check the live usage dashboard or `/status`. The account's live status is authoritative. Do not infer remaining allowance from historical token counts.

LCP-USAGE-2 — The current account does not enforce a five-hour window. Official documentation still describes plan-dependent usage estimates and possible limits, so keep it as general guidance rather than a timer for this run: [Codex pricing and usage limits](https://learn.chatgpt.com/docs/pricing#what-are-the-usage-limits-for-my-plan).

LCP-USAGE-3 — A quota warning, authentication boundary, or exhausted allowance stops concurrency increases. Keep completed productive work, close the current window as incomplete, gracefully requeue exact leases, and resume later at the last proven safe concurrency.

LCP-USAGE-4 — Do not switch this run to API-key billing or buy credits automatically. Any billing change requires a separate user decision.
