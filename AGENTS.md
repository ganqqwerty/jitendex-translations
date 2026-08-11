# AG — Repository instructions

## AG-FOCUS — Project focus

AG-FOCUS-1 — This repository extends the Russian Jitendex/Yomitan dictionary by processing successive dictionary batches with Luna, validating the translations, storing accepted results in the database, and exporting updated Yomitan dictionaries.

AG-FOCUS-2 — The only important ongoing work is processing the next dictionary batches with Luna. Treat older models, pilots, comparison experiments, and one-off scripts as project archaeology; do not investigate them deeply unless the current Luna workflow is blocked or the user explicitly asks.

AG-FOCUS-3 — Follow the [JPDB Luna orchestration runbook](JPDB_LUNA_ORCHESTRATION_RUNBOOK.md) for the exact batch-processing procedure.

AG-FOCUS-4 — Use [JPDB Luna run history](JPDB_LUNA_RUN_HISTORY.md) only for completed-run results, prior incidents, and verified archive hashes.

AG-FOCUS-5 — Use the [Luna clean v1 translation prompt](prompts/translate_luna_clean_v1.txt) for Luna translation batches.

## AG-SITES — Dictionary demo sites

AG-SITES-1 — All dictionary demo sites maintained by this repository are intentionally public.

AG-SITES-2 — Publishing dictionary data to these sites is pre-authorized. Do not request additional consent before deploying dictionary-data updates to them.

## AG-DOC — Documentation



AG-DOC-1 — Give every title and heading a short, stable ID, such as `GDLN-TR`.

AG-DOC-2 — Give every paragraph or point an ID, such as `GDLN-TR-2`.

AG-DOC-3 — Do not use normal bullet or numbered lists. Use one identified paragraph per point.

AG-DOC-4 — Do not use HTML anchors. Refer to the visible ID.

AG-DOC-5 — Never renumber an existing ID. Give new text a new ID.

AG-DOC-6 — Do not add documentation IDs to files under `prompts/`; changing them changes prompt provenance. New prompts MUST follow the convention.

AG-DOC-7 Use simple langauge. Be short.

## IDX Index of important files

[README](README.md), [Luna runbook](JPDB_LUNA_ORCHESTRATION_RUNBOOK.md), [Luna run history](JPDB_LUNA_RUN_HISTORY.md), [Luna prompt](prompts/translate_luna_clean_v1.txt), [tag replacement plan](JITENDEX_TAG_REPLACEMENT_PLAN.md), and [Luna run 3 preflight](reports/luna_run3_preflight.md).
