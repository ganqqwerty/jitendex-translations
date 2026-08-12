# LCP — Luna throughput experiment and PostgreSQL migration plan

LCP-1 — Status: proposed. Date: 2026-08-12.

## LCP-GOAL — Decision to make

LCP-GOAL-1 — Find the number of simultaneous Luna translators and the startup spacing that produce the highest accepted articles per minute.

LCP-GOAL-2 — Keep the model, medium reasoning, Luna v4 prompt, batch limits, validator, and runner revision fixed. This experiment changes only concurrency and startup spacing.

LCP-GOAL-3 — Run the same experiment again after PostgreSQL is ready. PostgreSQL can remove SQLite writer contention, but Luna may remain the main limit.

## LCP-SAFE — Protect the active translation

LCP-SAFE-1 — Do not run a benchmark, migrate data, change configuration, or start extra workers while the current production translation is active.

LCP-SAFE-2 — Wait until the active run has zero unfinished batches, zero unresolved blocking errors, complete accepted-unit coverage, and a verified export.

LCP-SAFE-3 — Make a verified SQLite backup after the run. Build the benchmark from that copy with a new benchmark run ID and separate inbox, outbox, response, and log directories. Never claim or ingest a production batch.

LCP-SAFE-4 — Keep benchmark results out of production history and exports. The benchmark may reuse representative manifests, but its attempts and translations stay disposable.

## LCP-METRIC — One primary metric

LCP-METRIC-1 — The primary metric is `articles_per_minute = newly completed articles / measured wall-clock minutes`.

LCP-METRIC-2 — An article is completed only when every translatable unit in that article has an accepted translation. Count each article once, at the time its last unit becomes accepted.

LCP-METRIC-3 — Also record accepted units per minute and accepted source characters per minute. These expose a misleading articles-per-minute result caused by an easier workload.

LCP-METRIC-4 — For every stage record concurrency, startup duration, completed articles, accepted units, source characters, request latency, 429s, timeouts, retries, validation rejections, splits, SQLite busy errors or PostgreSQL lock waits, and peak worker memory.

## LCP-CORPUS — Fixed benchmark work

LCP-CORPUS-1 — Freeze enough unaccepted benchmark articles for every stage to remain busy for 20 minutes. Include the normal mix of small and large articles and difficult validation cases.

LCP-CORPUS-2 — Split the corpus into equal shuffled shards balanced by article count, unit count, and serialized bytes. Give each stage a fresh database copy and one shard. Do not reuse accepted state between stages.

LCP-CORPUS-3 — Use the same corpus recipe, runner revision, machine, power state, and network. Run one stage at a time.

## LCP-EXP1 — Find useful concurrency

LCP-EXP1-1 — Use a 60-second smooth startup in every concurrency stage. Launch workers evenly across the minute, then replace each completed request immediately.

LCP-EXP1-2 — Test 40, 80, 120, and 160 simultaneous translators. If the best result is between two steps, test the missing 20-worker midpoint.

LCP-EXP1-3 — Each stage runs for 20 measured minutes after the target concurrency is reached. Discard the startup minute from this phase so every concurrency receives the same steady-state window.

LCP-EXP1-4 — Stop increasing concurrency when articles per minute fails to improve by at least 5%, 429s exceed 1%, timeouts plus transport failures exceed 2%, database busy failures occur, memory pressure becomes red, swap grows continuously, or p95 latency rises by 50% without a throughput gain.

LCP-EXP1-5 — Repeat the best stage and its nearest lower stage once. The concurrency candidate is the faster repeatable result, not a one-off peak.

## LCP-EXP2 — Find startup spacing

LCP-EXP2-1 — At the chosen concurrency, compare startup durations of 0, 30, 60, and 120 seconds. Launch individual workers evenly across the selected duration. Do not launch fixed waves.

LCP-EXP2-2 — After startup, replace every completion immediately. Luna response times already spread steady-state work, so replacement jitter is unnecessary unless the logs show repeated synchronized bursts.

LCP-EXP2-3 — Measure each spacing stage for 20 minutes from the first launch, including startup. This captures both burst failures and the throughput lost to a slow ramp.

LCP-EXP2-4 — Repeat the best spacing and the current burst start once. Choose the spacing with the higher repeatable articles-per-minute result. Prefer the shorter spacing when results differ by less than 2% and error rates are equal.

## LCP-DECISION — Production setting

LCP-DECISION-1 — Use the chosen concurrency and spacing only after both repeats pass with zero missing units, zero duplicate accepted translations, zero source-hash mismatches, zero unrecovered claims, and zero unresolved blocking errors.

LCP-DECISION-2 — Keep one step below any observed service, database, or machine failure boundary. Record the chosen values and raw stage results in the run history before the next production run.

LCP-DECISION-3 — If no tested setting beats concurrency 80 by at least 5%, keep 80. Do not add scheduler complexity without measured throughput.

## LCP-PG — PostgreSQL design

LCP-PG-1 — Migrate only between production runs. The completed SQLite database remains a read-only recovery artifact; there is no live in-place migration and no dual writing.

LCP-PG-2 — Put database operations behind one storage interface before changing SQL. Keep run identity, article and unit identity, attempt history, audit events, leases, immutable accepted translations, foreign keys, checks, and partial unique indexes unchanged.

LCP-PG-3 — Claim one ready batch in a short PostgreSQL transaction with `FOR UPDATE SKIP LOCKED`. The claim, lease, attempt row, and audit event must commit together. Ingestion and retry or split changes must each remain atomic and idempotent.

LCP-PG-4 — Use a bounded connection pool instead of one database connection per translator. Start with pool sizes 16 and 32 during the benchmark and keep the smaller size when articles per minute is equal.

LCP-PG-5 — Use timezone-aware timestamps, explicit transaction boundaries, durable PostgreSQL settings, regular backups, and schema migrations that can be applied to an empty database and to a migrated copy.

## LCP-PG-MIG — Migration and proof

LCP-PG-MIG-1 — After the active run is verified, stop all writers, make a SQLite backup, create an empty PostgreSQL database, bulk-copy every table, and reset generated sequences.

LCP-PG-MIG-2 — Compare every table count, run identity, accepted translation identity, attempt and audit count, source fingerprint, foreign key, and uniqueness constraint. Rebuild a completed dictionary from each database and require equivalent dictionary content.

LCP-PG-MIG-3 — Run claim, ingestion, lease-expiry, retry, split, killed-worker, and PostgreSQL-restart tests on the migrated copy. Require no lost claims and no duplicate accepted translation.

LCP-PG-MIG-4 — Run LCP-EXP1 and LCP-EXP2 against PostgreSQL with the same corpus. This result selects PostgreSQL concurrency, startup spacing, and connection-pool size.

LCP-PG-MIG-5 — Cut over configuration only after parity and benchmark gates pass. Keep SQLite unchanged and read-only until the first PostgreSQL run and export are verified.

LCP-PG-MIG-6 — Before the first PostgreSQL production claim, rollback means restoring the old SQLite configuration. After PostgreSQL accepts production writes, stop on failure and recover PostgreSQL from its audit trail or backup; never silently return to the now-stale SQLite database.

## LCP-RESULT — Small result record

LCP-RESULT-1 — Record the database, concurrency, startup seconds, connection-pool size, articles per minute, units per minute, source characters per minute, p95 request latency, 429 rate, failure rate, validation rejection rate, database wait or busy count, and peak memory for each stage.

LCP-RESULT-2 — End with one production recommendation and the measured percentage improvement over SQLite concurrency 80.
