# RUN — PostgreSQL Luna translation runbook

RUN-1 — This is the short operational source of truth for the next productive Jitendex translation batch. Completed results and incidents belong in [JPDB_LUNA_RUN_HISTORY.md](JPDB_LUNA_RUN_HISTORY.md).

RUN-2 measure the time of the things you do.

## RUN-STOP — Current state (update when state changed)

RUN-STOP-1 — Run 49 is complete in authoritative PostgreSQL with 336,368 frozen articles, 1,692,336 accepted units, zero unfinished work, and verified export 55. Run 48 was never created; its PostgreSQL sequence value was consumed by a rolled-back preparation attempt.

RUN-STOP-2 — The verified archive is `dist/jitendex-articles-336368-ru-luna-v4.zip`. Its SHA-256 is `84dcf1ecf6c5d4fe9532f2b1f415abc2f1f4edfe53422477ccfff116858001b2`.
RUN-STOP-3 — Stop at Run 49. Do not create another run or send more Luna requests without new user authorization.

RUN-STOP-4 — PostgreSQL is authoritative. The old SQLite source is read-only migration evidence and must not receive production writes.

RUN-STOP-5 — Concurrency 100 remains the proven future setting. The concurrency-110 fixed window reached 332.0 headwords per minute, 4.0% below concurrency 100, although it remained operationally clean.

## RUN-PIN — Pinned runtime

RUN-PIN-1 — Run from `/Users/iuriikatkov/Documents/ChatGPT/jitendex-translations` with `config.luna.toml` and the configured `JITENDEX_POSTGRES_URL`.

RUN-PIN-2 — Translation uses `gpt-5.6-luna`, medium reasoning, `prompts/translate_luna_v4.txt`, `lexicographer-v2`, and the batch limits in `config.luna.toml`.

RUN-PIN-3 — Do not change the model, prompt, reasoning, validator, batching limits, or runner revision during online concurrency tuning.

~~~bash
export PYTHONPATH=src
export JPDB_SOURCE_RUN_ID=49
export JPDB_ADD_ARTICLES=10000
export JPDB_TARGET_ARTICLES=346368
export JPDB_SCOPE_LABEL=346368
~~~

## RUN-PREFLIGHT — Protect production

RUN-PREFLIGHT-1 — Finish the local test, recovery, and parity gates in LCP-READY-2 through LCP-READY-6 without Luna usage.

RUN-PREFLIGHT-2 — Require one intended PostgreSQL database, no other runner, zero claimed attempts, zero unfinished work in `JPDB_SOURCE_RUN_ID`, and its verified export hash before changing scope.

RUN-PREFLIGHT-3 — Make and hash a PostgreSQL backup before creating the next run. Never put the database URL in a command log or report.

~~~bash
pg_dump -Fc "$JITENDEX_POSTGRES_URL" \
  -f work/backups/jitendex-postgresql-before-346368.dump
shasum -a 256 work/backups/jitendex-postgresql-before-346368.dump
~~~

RUN-PREFLIGHT-4 — Check live Codex usage status before the run and before each concurrency increase. The current account does not enforce a five-hour window; stop only on an actual quota or authentication boundary.

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

RUN-PREP-4 — Record every reported phase time. A normal 10,000-article increment should take about two to four minutes after this optimization. Investigate PostgreSQL activity and statistics if it exceeds ten minutes.

## RUN-TUNE — Productive online tuning

RUN-TUNE-1 — Use a 30-second ramp, at least 90 steady seconds, and at least 60 completions for productive adjacent-step comparisons. Stop new claims and drain active requests so successful responses are ingested rather than discarded.

RUN-TUNE-2 — Use the production-safe online window command after its no-request dry run passes. Give every window a unique ID.

~~~bash
PYTHONPATH=src .venv/bin/python scripts/run_luna_online_window.py \
  --config config.luna.toml \
  --run-id "$JPDB_RUN_ID" \
  --window-id "run${JPDB_RUN_ID}-c80-1" \
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

## RUN-MON — Required observations

RUN-MON-1 — Every online window records headwords, articles, units, source characters, request latency, tokens, 429s, timeouts, transport failures, validation rejections, retries, splits, claim collisions, stale-lease rejections, database duty cycle, claim and ingestion delay, pool and lock waits, PostgreSQL statistics, peak memory, memory pressure, and swap.

RUN-MON-2 — Live progress uses the shared production query in `jitendex_ru.run_integrity`. Accepted rows alone are not a live throughput metric because final acceptance is deferred.

RUN-MON-3 — `ready`, `leased`, and `retryable` are unfinished. `deterministic_validated` is completed translation work awaiting final acceptance. Only terminal blocked leaves require repair.

RUN-MON-4 — Repair genuine validation failures through normal claim and ingest provenance. Revalidate a saved response after a validator fix; do not ask Luna to translate it again.

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
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  build --run-id "$JPDB_RUN_ID" \
  --output "dist/jitendex-articles-${JPDB_SCOPE_LABEL}-ru-luna-v4.zip"

PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  verify "dist/jitendex-articles-${JPDB_SCOPE_LABEL}-ru-luna-v4.zip"

shasum -a 256 "dist/jitendex-articles-${JPDB_SCOPE_LABEL}-ru-luna-v4.zip"
~~~

RUN-FINISH-3 — Run the full test suite, record the verified export and online window results in [JPDB_LUNA_RUN_HISTORY.md](JPDB_LUNA_RUN_HISTORY.md), and update only RUN-STOP for the following batch. Also add lessons learned to [JPDB_LUNA_RUN_HISTORY.md](JPDB_LUNA_RUN_HISTORY.md) . If there were hiccups, add ideas on mitigating them to the history file. Times too need to be recorded there for future analysis. If the times are unusually long or short, the analysis must be added to the same history file.

## RUN-RECOVER — PostgreSQL recovery

RUN-RECOVER-1 — After any PostgreSQL production write, never return to SQLite. Stop writers and recover PostgreSQL from its audit trail or verified backup.

RUN-RECOVER-2 — Do not delete attempts, translations, audit events, or online window evidence. Preserve failed and interrupted provenance.

### RUN-LOG
Present the progress in a form of compact table, not just prose
RUN-LOG1 when reporting the progress, always show the number current step, e.g. RUN-FINISH-2
RUN-LOG2 report the amount of translated headwords, amount of headwords remaining in jitendex, amount of time passed for the current step and time since the beginning of the batch.
RUN-LOG3 Report the number or run and time since its beginning, as well as the amount of currently active translation processes
