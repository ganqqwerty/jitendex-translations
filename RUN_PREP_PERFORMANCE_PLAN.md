# RPP — Make RUN-PREP faster

RPP-1 — Status: implemented and disposable-tested. The next approved real RUN-PREP measurement is still required before changing the runbook time estimate.

## RPP-EVIDENCE — What we know

RPP-EVIDENCE-1 — Copying old units in PostgreSQL took about 18 seconds. Loading new units took less than one second.

RPP-EVIDENCE-2 — Reusing translations took about 48 seconds. Updating unit status took about 21 seconds. Updating PostgreSQL statistics took about four seconds.

RPP-EVIDENCE-3 — Database work does not explain the full 18 minutes. The slow part may be Python work, JSON work, batch packing, file writing, checks, or process startup.

RPP-EVIDENCE-4 — `make-batches` loads all selected articles, even though only articles with ready units need new batches. It also turns the same data into JSON many times while testing batch sizes.

## RPP-SAFE — Keep production safe

RPP-SAFE-1 — Do not profile, change, stop, or benchmark RUN-PREP while a real translation run is active.

RPP-SAFE-2 — Do not create a real run only for a speed test. Use test data and a disposable PostgreSQL database until the next real run is approved.

RPP-SAFE-3 — Keep unit IDs, article order, batch IDs, manifest files, hashes, source links, translation history, audit history, and safety checks unchanged.

RPP-SAFE-4 — Keep SQLite working. Put PostgreSQL-only speedups behind the database layer.

## RPP-MEASURE — Measure first

RPP-MEASURE-1 — Save the time for each phase: source check, scope selection, run creation, old-unit copy, new-article parsing, new-unit loading, translation reuse, status update, statistics update, ready-unit loading, article loading, envelope creation, batch packing, manifest writing, database batch loading, and final checks.

RPP-MEASURE-2 — For each phase, record wall time, CPU time, peak memory, input rows, output rows, files written, and bytes written.

RPP-MEASURE-3 — Print progress during long local work. This must show whether the process is busy, waiting for PostgreSQL, or stuck.

RPP-MEASURE-4 — Save the timing JSON under `reports/run_prep/`. Do not use PostgreSQL transaction timestamps to measure phases because one transaction keeps the same timestamp.

## RPP-BATCH — Make batch creation faster

RPP-BATCH-1 — Load ready units first. Get their article IDs. Load only those articles instead of the full selected corpus.

RPP-BATCH-3 — Calculate each article's JSON size once. Reuse that result while packing batches. Check each final manifest against the exact byte limit.

RPP-BATCH-4 — Keep atomic manifest writes. Load batch rows and batch-item rows in bulk with PostgreSQL `COPY`. Add audit rows in one database statement.

RPP-BATCH-5 — Keep batch output exactly the same. Tests must prove that the old and new code produce the same ordered batch IDs, unit groups, manifest bytes, and hashes.

## RPP-EXTRACT — Limit extraction work

RPP-EXTRACT-1 — The timing report must prove that only new articles are parsed. It must also prove that all old accepted units were copied.

RPP-EXTRACT-2 — Process new articles as a stream. Do not keep the full corpus in Python memory.

RPP-EXTRACT-3 — If parsing is still slow, measure JSON parsing, structure checks, context creation, protected-token work, and hashing separately before changing them.

## RPP-TEST — Prove it is correct

RPP-TEST-1 — Make a disposable PostgreSQL test with an old run, unchanged articles, new articles, accepted translations, and enough ready articles for several batches.

RPP-TEST-2 — Compare old and new results: article fingerprints, units, reused translations, status counts, batches, batch items, manifests, audit counts, and safety checks.

RPP-TEST-3 — Run all normal tests and all disposable-PostgreSQL tests. Do not use the new path in production unless both pass.

RPP-TEST-4 — Run a large disposable test with no Luna requests. Record phase times and peak memory.

## RPP-DECIDE — Decide from results

RPP-DECIDE-1 — First get clear measurements and matching output. Do not start with a promised total time.

RPP-DECIDE-2 — Keep a speedup only if its phase becomes at least twice as fast, total RUN-PREP becomes faster, memory stays safe, and all checks pass.

RPP-DECIDE-3 — After disposable tests pass, measure the next approved real RUN-PREP. Use that result to update the runbook.

## RPP-ORDER — Work order

RPP-ORDER-1 — Add saved phase timings and progress messages.

RPP-ORDER-2 — Load only articles that have ready units.

RPP-ORDER-3 — Reduce repeated JSON work while keeping manifests exactly the same.

RPP-ORDER-4 — Load batch data and audit data in bulk.

RPP-ORDER-5 — Run the large disposable test, all tests, and then measure the next approved real run.

## RPP-RESULT — Implemented result

RPP-RESULT-1 — RUN-PREP now saves wall time, CPU time, peak memory, row counts, files, and bytes for its phases. Long extraction prints whether Python is parsing or PostgreSQL is loading. The productive driver saves its JSON under `reports/run_prep/`.

RPP-RESULT-2 — Incremental extraction reports old units copied, new articles parsed, and new units loaded. A restored pre-Run-49 database proved that exactly 10,000 new articles were parsed, 1,655,490 old units were copied, and 36,846 new units were loaded. New-article parsing took 0.75 seconds: JSON 0.073, structure and context 0.580, and hashing 0.076 seconds. New-unit loading took 0.93 seconds.

RPP-RESULT-3 — Batch creation now loads only articles with unbatched ready units and loads their Kaishi evidence in one query. It serializes each article once for packing, then checks every final manifest against exact canonical serialization and byte limits. A parity test proves the optimized and legacy packers produce the same ordered groups and byte-identical manifests.

RPP-RESULT-4 — PostgreSQL batch, batch-item, and audit rows now use three COPY streams. SQLite keeps its existing behavior. The 10,000-article controlled benchmark loaded 834 batches, 10,000 batch items, and 834 audit rows with matching counts.

RPP-RESULT-5 — In [the saved 10,000-article benchmark](reports/run_prep/synthetic-10000.json), cached-size packing improved from 0.604 seconds to 0.168 seconds, or 3.59 times faster. COPY loading improved from 1.069 seconds to 0.0088 seconds, or 120.9 times faster. The optimized end-to-end synthetic extraction took 0.362 seconds, batching took 0.639 seconds, peak memory was 118 MB, and Luna requests were zero.

RPP-RESULT-6 — One full 3.1 GB restore into the production Docker volume exhausted that volume. The incomplete disposable database was removed and Run 49 integrity was rechecked. A second full restore succeeded under `/private/tmp`, outside iCloud, but bind-mounted macOS database I/O made translation reuse exceed seven minutes. That environment was valid for integrity observations but rejected as a speed comparison.

RPP-RESULT-7 — All 115 tests pass normally and with the disposable PostgreSQL tests enabled. PostgreSQL tests cover incremental copy, set-based reuse, COPY batch loading, audit counts, claims, interruption, retries, splits, and connection loss.

RPP-RESULT-8 — Retain the ready-article filter, bulk evidence query, cached-size packing, COPY loading, phase metrics, progress messages, saved report, and benchmark. They pass parity and memory gates, and the measured packing and loading phases exceed the required two-times speedup. Do not change the runbook estimate until the next approved real RUN-PREP records its result.
