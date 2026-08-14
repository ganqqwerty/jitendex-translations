# RUN — PostgreSQL Luna translation runbook

RUN-1 — This is the short operational source of truth for the next productive Jitendex translation batch. Install and version details are in [DEVELOPER_TOOLING.md](DEVELOPER_TOOLING.md). Completed results and incidents belong in [JPDB_LUNA_RUN_HISTORY.md](JPDB_LUNA_RUN_HISTORY.md).

RUN-2 — Measure every phase. Preserve its command, start and finish time, result, report path, and relevant hash.

## RUN-STOP — Current state (update when state changed)

RUN-STOP-1 — Run 59 is complete in authoritative PostgreSQL with all 433,885 frozen articles, 2,053,045 accepted units, zero unfinished leaf work, and verified release exports 65 through 67 and 70 through 72.

RUN-STOP-2 — Verified export 65 remains unchanged at `dist/jitendex-articles-433885-ru-luna-v4.zip`, SHA-256 `68b4ef51f06213428e0c5b223b6715e2099542e28456c9fe8e42df75587d127b`.
RUN-STOP-3 — Run 59 is the completed full-corpus checkpoint. All 431,545 Jitendex headwords are translated and zero remain. There is no next productive scope unless the source dictionary gains articles.

RUN-STOP-4 — PostgreSQL is authoritative. The old SQLite source is read-only migration evidence and must not receive production writes.

RUN-STOP-5 — Concurrency 100 remains the proven future setting. The concurrency-110 fixed window reached 332.0 headwords per minute, 4.0% below concurrency 100, although it remained operationally clean.

RUN-STOP-6 — Docker's internal disk limit is 264 GB and its PostgreSQL filesystem has about 115 GB free. Its disk image remains under `~/Library/Containers`, outside Documents and iCloud.

RUN-STOP-7 — The verified co-author `tags-ru-v1` exports are Yomitan 73, GoldenDict 74, MDict 75, PocketBook 76, and Apple Dictionary 77. Their hashes are recorded in [README-STATE](README.md) and the run history. Client release still requires the manual gates in [TOOL-CLIENT](DEVELOPER_TOOLING.md).

## RUN-PIN — Pinned runtime

RUN-PIN-1 — Run from `/Users/iuriikatkov/Documents/ChatGPT/jitendex-translations` with `config.luna.toml` and the configured `JITENDEX_POSTGRES_URL`.

RUN-PIN-2 — Translation uses `gpt-5.6-luna`, medium reasoning, `prompts/translate_luna_v4.txt`, `lexicographer-v2`, and the batch limits in `config.luna.toml`.

RUN-PIN-3 — Do not change the model, prompt, reasoning, validator, batching limits, or runner revision during online concurrency tuning.

## RUN-ENV — Open a production shell

RUN-ENV-1 — Start from the repository root, confirm Docker health, and create the PostgreSQL URL from the running container. Never print or record the URL because it contains the database password.

~~~bash
cd /Users/iuriikatkov/Documents/ChatGPT/jitendex-translations
docker inspect jitendex-postgres --format '{{.State.Health.Status}}'
JITENDEX_DB_PASSWORD="$(docker exec jitendex-postgres printenv POSTGRES_PASSWORD)"
JITENDEX_DB_PORT="$(docker port jitendex-postgres 5432/tcp | awk -F: 'END {print $NF}')"
export JITENDEX_POSTGRES_URL="postgresql://jitendex:${JITENDEX_DB_PASSWORD}@127.0.0.1:${JITENDEX_DB_PORT}/jitendex"
unset JITENDEX_DB_PASSWORD JITENDEX_DB_PORT
export PYTHONPATH="$PWD/src"
~~~

RUN-ENV-2 — Set the run values for the authorized batch. `JPDB_SOURCE_RUN_ID` is the completed run being extended, `JPDB_ADD_ARTICLES` is the number of new articles, and the preparation report supplies the new `JPDB_RUN_ID`.

~~~bash
export JPDB_SOURCE_RUN_ID=59
export JPDB_ADD_ARTICLES=NUMBER_OF_NEW_ARTICLES
export JPDB_TARGET_ARTICLES=EXPECTED_TOTAL_ARTICLES
export JPDB_SCOPE_LABEL=EXPECTED_TOTAL_ARTICLES
~~~

RUN-ENV-3 — Run 59 still has the historical database lifecycle value `active`. Its workload is complete. Judge operational completeness from leaf-batch states, translated-unit coverage, acceptance, validation, and verified exports; do not infer it from that label alone.

## RUN-TAGS — Approved Russian tags

RUN-TAGS-1 — `terminology/jitendex-tags-ru.csv` is the exact authority for 236 labels and tooltips. Import it with `import-approved-tags --csv PATH --snapshot-id ID` after a PostgreSQL backup.

RUN-TAGS-2 — Yomitan and GoldenDict builds load only complete `approved_workbook` rows from `jitendex_tag`. Missing, duplicate, incomplete, or colliding mappings stop the build.

RUN-TAGS-3 — Both exporters localize embedded tags from source category and code. Yomitan also localizes tag-bank names, descriptions, and term references. Do not edit historical Luna translations or use `terminology/tag-bank-ru-v1.json` for current builds.

## RUN-BACKUP — Preserve PostgreSQL

RUN-BACKUP-1 — After authorization and before preparation, import, migration, or repair, create a unique custom-format dump and verify that PostgreSQL can list it.

~~~bash
mkdir -p work/backups
JPDB_BACKUP_PATH="$PWD/work/backups/jitendex-postgresql-before-run${JPDB_SOURCE_RUN_ID}-continuation.dump"
docker exec jitendex-postgres pg_dump -U jitendex -d jitendex --format=custom \
  > "$JPDB_BACKUP_PATH"
docker exec -i jitendex-postgres pg_restore --list < "$JPDB_BACKUP_PATH" > /dev/null
shasum -a 256 "$JPDB_BACKUP_PATH"
unset JPDB_BACKUP_PATH
~~~

RUN-BACKUP-2 — Record the dump name, SHA-256, elapsed time, source run, and reason in the run history. Never restore over production as an ordinary recovery step; follow [TOOL-BACKUP](DEVELOPER_TOOLING.md).

## RUN-PREFLIGHT — Protect production

RUN-PREFLIGHT-1 — Refresh the locked environment and run the complete local suite without Luna usage.

~~~bash
uv sync --extra test
PYTHONPATH=src .venv/bin/pytest -q
~~~

RUN-PREFLIGHT-2 — Require the intended PostgreSQL database, no other runner, zero claimed attempts, zero unfinished work in `JPDB_SOURCE_RUN_ID`, and its verified export hash before changing scope.

~~~bash
docker exec jitendex-postgres psql -U jitendex -d jitendex -Atc \
  "SELECT current_database(), current_user, version();"
pgrep -fl 'run_luna_online_window.py|run_codex_batches.py' || true
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml report progress
~~~

RUN-PREFLIGHT-3 — There is no next run now. Run 59 covers the current snapshot. `prepare_luna_run.py` can add articles only from the same source snapshot as its source run, so a new Jitendex snapshot requires an explicitly reviewed cross-snapshot continuation change before preparation. Do not assume the existing driver will discover it.

RUN-PREFLIGHT-4 — Do not enforce the historical five-hour usage window. Stop only when the live runner reports an actual quota, capacity, or authentication boundary.

RUN-PREFLIGHT-5 — Before a real model window, run the wrapper once with a new evidence ID and `--dry-run`. This writes an empty event log and a preflight result but makes no Luna request.

~~~bash
PYTHONPATH=src .venv/bin/python scripts/run_luna_online_window.py \
  --config config.luna.toml \
  --run-id "$JPDB_RUN_ID" \
  --window-id "run${JPDB_RUN_ID}-preflight-1" \
  --concurrency 100 \
  --ramp-seconds 30 \
  --steady-seconds 90 \
  --minimum-completed 60 \
  --request-timeout-seconds 180 \
  --dry-run
~~~

RUN-PREFLIGHT-6 — The dry run must identify PostgreSQL, the latest intended run, zero global claims, and zero postflight integrity failures. Evidence IDs are immutable even for dry runs; increment the suffix instead of deleting or reusing one.

## RUN-PREP — Create the next productive run

RUN-PREP-1 — After authorization and backup, use the timed preparation driver. It selects the next scope, creates the run, reuses accepted translations, creates productive batches, and enforces the pre-Luna gates.

~~~bash
PYTHONPATH=src .venv/bin/python scripts/prepare_luna_run.py \
  --config config.luna.toml \
  --source-run-id "$JPDB_SOURCE_RUN_ID" \
  --add-articles "$JPDB_ADD_ARTICLES"
~~~

RUN-PREP-2 — PostgreSQL copies unchanged unit metadata from the source run, parses only newly selected articles, streams new rows with `COPY`, reuses translations with set-based SQL, and refreshes statistics. It sends no LLM requests.

RUN-PREP-3 — The driver must report the target article count, zero source-unit identity gaps, zero claimed attempts, zero unresolved errors, and nonzero ready units and batches. Use its returned `target_run_id` as `JPDB_RUN_ID`.

~~~bash
export JPDB_RUN_ID=TARGET_RUN_ID_FROM_REPORT
~~~

RUN-PREP-4 — Record every reported phase time. The real optimized 10,000-article increment took 171.40 seconds, so allow about three minutes. Investigate PostgreSQL activity and statistics if it exceeds ten minutes.

RUN-PREP-5 — Preserve `reports/run_prep/run-${JPDB_RUN_ID}-prep.json`. It contains the exact counts, wall time, CPU time, and peak memory for source preflight, selection, extraction, reuse, batching, and verification.

## RUN-TUNE — Productive online tuning

RUN-TUNE-1 — Use a 30-second ramp, at least 90 steady seconds, and at least 60 completions for productive adjacent-step comparisons. Stop new claims and drain active requests so successful responses are ingested rather than discarded.

RUN-TUNE-2 — Use the production-safe online window command after its no-request dry run passes. Give every window a unique ID.

~~~bash
PYTHONPATH=src .venv/bin/python scripts/run_luna_online_window.py \
  --config config.luna.toml \
  --run-id "$JPDB_RUN_ID" \
  --window-id "run${JPDB_RUN_ID}-c100-1" \
  --concurrency 100 \
  --ramp-seconds 30 \
  --steady-seconds 90 \
  --minimum-completed 60 \
  --request-timeout-seconds 180
~~~

RUN-TUNE-3 — Review each result before changing concurrency. Require at least 60 completed steady-window requests, zero database failures, zero claim collisions, zero stale-lease rejections, acceptable errors, stable memory and swap, and no active leases after drain.

RUN-TUNE-4 — Use concurrency 100 for production translation. The concurrency 110 fixed window was about 4% slower by headword throughput, so it does not replace 100.

RUN-TUNE-5 — Skip SQLite Luna benchmarking. Skip database-worker experiments unless database duty cycle or ingestion delay proves one coordinator limits replacements.

RUN-TUNE-6 — Ctrl-C remains the emergency stop. It terminates child requests and requeues exact leases. A normal window must use productive drain instead.

RUN-TUNE-7 — Repeat the c100 command with a fresh numeric suffix after each result passes RUN-TUNE-3. When fewer than 60 requests remain, finish the tail directly; it keeps claiming until no ready or retryable work remains.

~~~bash
set -o pipefail
mkdir -p work/luna_performance/tails
PYTHONPATH=src .venv/bin/python scripts/run_codex_batches.py \
  --config config.luna.toml \
  --run-id "$JPDB_RUN_ID" \
  --kind translation \
  --concurrency 100 \
  --worker-prefix "run${JPDB_RUN_ID}-tail-1" \
  --progress-interval 60 \
  --request-timeout-seconds 180 \
  2>&1 | tee "work/luna_performance/tails/run${JPDB_RUN_ID}-tail-1.jsonl"
~~~

RUN-TUNE-8 — Never run the online wrapper and direct tail runner at the same time. Preserve every result JSON, JSONL log, rejected response, retry, and split record.

## RUN-MON — Required observations

RUN-MON-1 — Every online window records headwords, articles, units, source characters, request latency, tokens, 429s, timeouts, transport failures, validation rejections, retries, splits, claim collisions, stale-lease rejections, database duty cycle, claim and ingestion delay, pool and lock waits, PostgreSQL statistics, peak memory, memory pressure, and swap.

RUN-MON-2 — Live progress uses the shared production query in `jitendex_ru.run_integrity`. Accepted rows alone are not a live throughput metric because final acceptance is deferred.

RUN-MON-3 — `ready`, `leased`, and `retryable` are unfinished. `deterministic_validated` is completed translation work awaiting final acceptance. Only terminal blocked leaves require repair.

RUN-MON-4 — Repair genuine validation failures through normal claim and ingest provenance. Revalidate a saved response after a validator fix; do not ask Luna to translate it again.

RUN-MON-5 — Use the database progress report and process list while a run is active. The online wrapper also writes `reports/luna_performance/online/WINDOW.json` and `work/luna_performance/online/WINDOW.jsonl`.

~~~bash
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml report progress
pgrep -fl 'run_luna_online_window.py|run_codex_batches.py|/Resources/codex exec'
~~~

## RUN-FINISH — Accept and export

RUN-FINISH-1 — Before acceptance, require zero ready, leased, or retryable batches; zero terminal blocked leaves; zero unresolved validation errors; and complete translated-unit coverage.

~~~bash
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  accept-translations --run-id "$JPDB_RUN_ID"

PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  validate --run-id "$JPDB_RUN_ID"
~~~

RUN-FINISH-2 — Require exactly one accepted translation per unit, zero blocking issues, and exactly `JPDB_TARGET_ARTICLES` frozen articles.

~~~bash
export PGOPTIONS='-c work_mem=512MB -c max_parallel_workers_per_gather=0'

PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  build --run-id "$JPDB_RUN_ID" \
  --output "dist/jitendex-articles-${JPDB_SCOPE_LABEL}-ru-luna-v4-tags-ru-v1.zip"

PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  verify "dist/jitendex-articles-${JPDB_SCOPE_LABEL}-ru-luna-v4-tags-ru-v1.zip"

shasum -a 256 "dist/jitendex-articles-${JPDB_SCOPE_LABEL}-ru-luna-v4-tags-ru-v1.zip"

unset PGOPTIONS
~~~

RUN-FINISH-3 — The session-only `PGOPTIONS` prevents the large full-corpus export and independent verifier queries from spilling parallel sorts into Docker's disk. It does not change persistent PostgreSQL settings.

RUN-FINISH-4 — Run the full test suite. Build any additional formats with the commands in [TOOL-EXPORT](DEVELOPER_TOOLING.md). Every archive needs a new filename, its matching verifier, a SHA-256, and a verified database export record.

RUN-FINISH-5 — Record the backup, preparation, windows, tail, acceptance, validation, builds, verification, tests, incidents, and hashes in [JPDB_LUNA_RUN_HISTORY.md](JPDB_LUNA_RUN_HISTORY.md). Explain unusually fast or slow phases and record a mitigation for every incident. Update RUN-STOP for the following batch.

## RUN-RECOVER — PostgreSQL recovery

RUN-RECOVER-1 — After any PostgreSQL production write, never return to SQLite. Stop writers and recover PostgreSQL from its audit trail or verified backup.

RUN-RECOVER-2 — Do not delete attempts, translations, audit events, or online window evidence. Preserve failed and interrupted provenance.

RUN-RECOVER-3 — After a reboot or suspected clock jump, compare the host and database UTC clocks, confirm Docker health, prove that no runner remains, then inspect progress before restarting anything.

~~~bash
date -u
docker inspect jitendex-postgres --format '{{.State.Health.Status}}'
docker exec jitendex-postgres psql -U jitendex -d jitendex -Atc \
  "SELECT clock_timestamp() AT TIME ZONE 'UTC';"
pgrep -fl 'run_luna_online_window.py|run_codex_batches.py|/Resources/codex exec' || true
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml report progress
~~~

RUN-RECOVER-4 — Expired PostgreSQL leases recover through the next normal claim and produce `recover_expired_lease` audit evidence. Never clear claims or leases manually while a worker may still be alive. If the normal recovery path fails, stop and diagnose before mutating state.

## RUN-LOG — Progress reports

RUN-LOG1 — Present progress as a compact table, not only prose. Always show the current step code, such as RUN-TUNE-2 or RUN-FINISH-2.

RUN-LOG2 — Report translated headwords, headwords remaining in Jitendex, elapsed time for the current step, and elapsed time since the batch began.

RUN-LOG3 — Report the run number, elapsed time since that run began, and the number of active translation processes.

RUN-LOG4 — Use these columns: `step`, `run`, `step elapsed`, `batch elapsed`, `translated headwords`, `remaining headwords`, and `active translators`. Add one short incident note only when state changed.
