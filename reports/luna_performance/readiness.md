# LCPR — PostgreSQL online-tuning readiness

LCPR-1 — Status: complete. Date: 2026-08-14. Productive PostgreSQL tuning selected concurrency 100. The disposable Luna matrix and SQLite benchmark remain cancelled.

## LCPR-GATE — Local gates

LCPR-GATE-1 — LCP-READY-1 passes. PostgreSQL run 45 is complete with 306,368 articles, 1,588,646 accepted units, zero unfinished work, and verified export SHA-256 `9dd8e4c0569a6ab419fe89fcddcc20a831f12d7aad386c159ad19990d31bf072`.

LCPR-GATE-2 — LCP-READY-2 passes. All 113 tests pass normally. All 113 also pass with the disposable PostgreSQL recovery database enabled.

LCPR-GATE-3 — LCP-READY-3 passes. The full migration verifier reports 26 equal table counts and hashes, 45 equal order-independent run fingerprints, 15 safe insert-and-rollback identity probes, zero unvalidated constraints, four immutable-history triggers, and equal dictionary ZIP SHA-256 `fa30ecf36ca420c90168b8cd7028364405cbb153564dfacfabdb19f4e81c7861`.

LCPR-GATE-4 — LCP-READY-4 passes. Concurrent claim, exact interruption, killed child, restart, replay, retry, split, expiry, and lost-connection recovery tests pass.

LCPR-GATE-5 — LCP-READY-5 passes locally. The final production-safe online window command passed dry mode against run 46 with zero claims, zero Luna calls, zero leases, zero missing units, zero duplicate translations, and zero unresolved blocking errors.

LCPR-GATE-6 — LCP-READY-6 passes. PostgreSQL is 17.10, psycopg is 3.2.9, schema version is 9, pool maximum is four, and `pg_stat_statements` is enabled. The zero-claim PostgreSQL backup SHA-256 is `2bce06bcff99ee6a7a672d0540a4f4f146d6f2715ab0602d776f8c5f1703e4d2`.

LCPR-GATE-7 — LCP-READY-7 passes through this report. LCP-READY-8 records the user's 2026-08-13 approval for productive PostgreSQL online tuning. The next run still performs RUN-PREFLIGHT before changing scope or sending Luna requests.

## LCPR-RUN — Productive path

LCPR-RUN-1 — Runs 46 and 47 are complete. Run 47 stops at 326,368 frozen articles and verified export 54. No later run is authorized.

LCPR-RUN-2 — Clean online windows use a 30-second smooth ramp, at least 90 steady seconds, and at least 60 completed steady-window requests. Fixed duration makes 70, 80, and 90 comparable; the lower completion floor does not favor higher concurrency.

LCPR-RUN-3 — Normal boundaries drained active requests. Concurrency 100 passed; the user stopped the ladder before 110.

LCPR-RUN-4 — Each run-46 window is expected to complete roughly 180 to 280 requests depending on concurrency and latency. The ladder stops early when useful work, live allowance, safety, or throughput gates say to stop.

LCPR-RUN-5 — SQLite comparison and startup-spacing matrices are skipped. Database-worker experiments are skipped unless measured database duty cycle or ingestion delay limits replacements.

## LCPR-USAGE — Allowance and cost

LCPR-USAGE-1 — The current account does not enforce a five-hour window. Live dashboard or `/status` information is authoritative before the run and every increase.

LCPR-USAGE-2 — Official documentation remains general guidance because usage can depend on plan, model, task, context, reasoning, tools, retrieval, and caching: [Codex pricing and usage limits](https://learn.chatgpt.com/docs/pricing#what-are-the-usage-limits-for-my-plan).

LCPR-USAGE-3 — The runner uses the ChatGPT-authenticated bundled Codex route. Expected incremental API charge is zero while that route remains unchanged. The workflow never switches to API-key billing or buys credits automatically.

LCPR-USAGE-4 — The first concurrency-80 launch hit an actual usage boundary before measurement and was recovered. A later user instruction explicitly authorized proceeding without using that boundary as the readiness gate.

## LCPR-STOP — Increase and safety gates

LCPR-STOP-1 — Do not increase when headwords per minute improves by less than 5%, 429s exceed 1%, timeouts plus transport failures exceed 2%, p95 latency rises by 50% without throughput gain, or the window has fewer than 60 completed requests.

LCPR-STOP-2 — Do not increase after any database failure, claim collision, stale-lease rejection, unresolved blocking error, red memory pressure, or continuous swap growth.

LCPR-STOP-3 — Every drained window requires zero claimed attempts, zero leased batches, zero unaccounted units, and zero duplicate translations. Emergency interruption must requeue every exact lease.

LCPR-STOP-4 — An actual quota warning or authentication boundary stops increases. Keep completed work, mark the window incomplete, drain or gracefully interrupt, and resume later at the last proven safe concurrency.

## LCPR-EVIDENCE — Files

LCPR-EVIDENCE-1 — Full parity is `reports/luna_performance/migration/database-parity.json`, SHA-256 `fb01974c23d58352c062b5d6ee2f9ca6b0c9510d82b80054ea8cf4084d7dac25`.

LCPR-EVIDENCE-2 — The successful online dry result for the final runner revision is `reports/luna_performance/online/run46-online-dry-v4.json`, SHA-256 `658b8a7d736d0368ce5caffcb3c8bef413f1e3fcbd4fb57e9ea6bf35bee36d32`.

LCPR-EVIDENCE-3 — Productive window results will be stored under `reports/luna_performance/online/`. They contain IDs, hashes, settings, counts, timings, and monitoring data, not credentials or translation payloads.

LCPR-EVIDENCE-4 — The invalid pre-measurement quota launch and its exact-lease recovery are recorded in `reports/luna_performance/online/run46-c80-1-quota-incident.json`. It is not usable for tuning.

LCPR-EVIDENCE-5 — The final productive results are `run46-c70-1.json`, `run46-c90-1.json`, and `run47-c100-1.json`. Their SHA-256 values are `d9575e4fd8f117d8068be403ea3566955564d3a63da15fd0ce10bccae228a109`, `12dc95c73e6be691ab9a4a623403dea8ff896fb98c23dc2c58950718345a2a95`, and `5859b2672f8d84ad4dc8b5c59918f60d3d9b07cac3668a541df9c835cd7ccdd8`.
