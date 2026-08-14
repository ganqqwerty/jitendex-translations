# LPR — Luna performance reports

LPR-1 — This directory stores migration evidence, dry harness evidence, and small productive online-window results. It must not store credentials or full translation payloads.

## LPR-SAFE — Safety

LPR-SAFE-1 — Prepare stages with `scripts/prepare_luna_benchmark.py`. The command needs the explicit disposable database flag.

LPR-SAFE-2 — Validate a stage with `scripts/validate_luna_benchmark.py`. The validator cannot claim work or call Luna.

LPR-SAFE-3 — Do not run disposable Luna stages. Productive online windows start only after LCP-READY-1 through LCP-READY-8 and the production runbook preflight pass.

LPR-SAFE-4 — Add `scripts/run_luna_benchmark.py` only after migration parity passes, as required by LCP-ART-5.

## LPR-RESULT — Result contract

LPR-RESULT-1 — `online-result.schema.json` defines productive PostgreSQL window evidence. It records hashes, settings, counters, phases, PostgreSQL waits, collisions, and machine observations without request payloads.

LPR-RESULT-2 — `corpus.schema.json` and `stage.schema.json` define the immutable corpus and stage contracts. Canonical definitions live under `stage-definitions/`.

LPR-RESULT-3 — `stages/` retains local dry-contract evidence only. Do not send Luna requests through the disposable stage harness.

LPR-RESULT-4 — Productive results live under `online/`. The runner refuses disposable databases, benchmark overrides, duplicate window IDs, stale claims, and non-latest production runs.
