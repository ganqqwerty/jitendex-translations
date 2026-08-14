# LCPA — Luna performance plan completion audit

LCPA-1 — Date: 2026-08-14. The productive PostgreSQL tuning path is complete through concurrency 100.

LCPA-2 — All unconditional plan work is complete. Database-worker and higher-concurrency experiments remain conditional and were not triggered or authorized.

## LCPA-STATE — Remaining productive work

LCPA-STATE-1 — No unconditional productive work remains. Runs 46 and 47 are accepted, canonicalized, validated, exported, and verified.

LCPA-STATE-2 — Concurrency 100 is the final recommendation. The productive window passed postflight integrity checks and beat concurrency 80 by 15.3%.

LCPA-STATE-3 — LCP-POOL-4, LCP-EXP2-3, LCP-EXP3-1 through LCP-EXP3-3 are conditional. They remain dormant unless a clean online window shows pool waits, synchronized replacement bursts, high database duty, or ingestion delay.

## LCPA-DONE — Completed design and migration work

LCPA-DONE-1 — LCP-1, LCP-GOAL-2 through LCP-GOAL-4, LCP-NOW-1 through LCP-NOW-3, and LCP-SAFE-1 through LCP-SAFE-5 are complete. PostgreSQL is authoritative, runs 46 and 47 contain useful production work, the old SQLite source is read-only, and backups and hashes are recorded in `readiness.md` and run history.

LCPA-DONE-2 — LCP-ARCH-1 through LCP-ARCH-6 and LCP-COMPAT-1 through LCP-COMPAT-10 are complete. `jitendex_ru.database`, backend configuration, connection pooling, error categories, parameter conversion, transaction boundaries, migration isolation, and the SQL portability test provide the evidence.

LCPA-DONE-3 — LCP-SCHEMA-1 through LCP-SCHEMA-7 and LCP-CLAIM-1 through LCP-CLAIM-8 are complete. Numbered PostgreSQL migrations, constraint and trigger parity, identity probes, `FOR UPDATE SKIP LOCKED`, database-time leases, exact lease tokens, atomic ingestion, and recovery tests provide the evidence.

LCPA-DONE-4 — LCP-POOL-1 through LCP-POOL-3 are complete. Production uses one coordinator, a four-connection pool with a finite timeout, and recorded checkout, transaction, claim, ingestion, and pool-wait metrics.

LCPA-DONE-5 — LCP-ART-1 through LCP-ART-6 and LCP-PG-MIG-1 through LCP-PG-MIG-11 are complete. The numbered migrations, one-way migration tool, parity verifier, local-only benchmark tools, production online recorder, read-only SQLite source, PostgreSQL backup, and `migration/database-parity.json` provide the evidence.

## LCPA-DONE2 — Completed online controls

LCPA-DONE2-1 — LCP-OBS-1 through LCP-OBS-5 are complete. Runner events and the online result schema cover backend, workers, progress, claims, ingestion, pool waits, requests, tokens, latency, errors, PostgreSQL waits, memory, configuration, revision, window identity, and complete-result ordered-batch identity.

LCPA-DONE2-2 — LCP-METRIC-1 through LCP-METRIC-6 are implemented. The shared `run_integrity` query defines live headword completion. The recorder also captures article, unit, character, latency, failure, collision, stale-lease, database, and memory measures without treating deferred acceptance as live progress.

LCPA-DONE2-3 — LCP-CORPUS-1, LCP-CORPUS-2, and LCP-CORPUS-6 are active controls. No disposable Luna corpus is used, headwords stay intact, and model, prompt, reasoning, limits, machine, and runner revision stay fixed during the ladder.

LCPA-DONE2-4 — LCP-HARNESS-1 through LCP-HARNESS-7 are complete locally. The wrapper has smooth launch timing, fixed-concurrency windows, productive drain, production preflight, exact interruption recovery, postflight gates, source-hash checks, workload profiles, and a no-request dry mode.

LCPA-DONE2-5 — LCP-EXP0 and LCP-EXP1 are complete. Productive PostgreSQL windows covered 70, 80, 90, and 100. SQLite Luna benchmarking was skipped. The invalid first launch remains incident evidence only.

LCPA-DONE2-6 — LCP-EXP2-1 and LCP-EXP2-2 are complete. There is no startup-spacing matrix, and the fixed ramp is 30 seconds. LCP-EXP2-3 stays conditional.

LCPA-DONE2-7 — LCP-DECISION-1 and LCP-CUT-1 through LCP-CUT-4 are complete. PostgreSQL remains authoritative, SQLite rollback is forbidden after production writes, and recovery uses PostgreSQL audit history or its verified backup.

LCPA-DONE2-8 — LCP-READY-1 through LCP-READY-8 and LCP-ORDER-1 through LCP-ORDER-6 are complete. `readiness.md`, the parity report, recovery evidence, tests, user consent, and `online/run46-online-dry-v4.json` provide the proof.

LCPA-DONE2-9 — LCP-USAGE-2 through LCP-USAGE-4 are complete. There is no assumed five-hour timer, live service status remains authoritative, quota stops increases with exact recovery, and billing never changes automatically.

## LCPA-BLOCK — External boundary

LCPA-BLOCK-1 — LCP-USAGE-3 stopped the first run-46 concurrency-80 window before measurement. The service reported no allowance until 2026-08-18 23:00 Europe/Zurich. The quota incident is preserved in `online/run46-c80-1-quota-incident.json`; it added no new translation and left zero claims and zero leases.

LCPA-BLOCK-2 — There is no active blocker. Work stops at verified Run 47 by user instruction. Run 48 and concurrency 110 require new authorization.
