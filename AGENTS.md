# Repository instructions

## Project focus

This repository extends the Russian Jitendex/Yomitan dictionary by processing successive dictionary batches with Luna, validating the translations, storing accepted results in the database, and exporting updated Yomitan dictionaries.

The only important ongoing work is processing the next dictionary batches with Luna. Treat older models, pilots, comparison experiments, and one-off scripts as project archaeology; do not investigate them deeply unless the current Luna workflow is blocked or the user explicitly asks.

- Follow the [JPDB Luna orchestration runbook](JPDB_LUNA_ORCHESTRATION_RUNBOOK.md) for the exact batch-processing procedure.
- Use the [Luna clean v1 translation prompt](prompts/translate_luna_clean_v1.txt) for Luna translation batches.

## Dictionary demo sites

- All dictionary demo sites maintained by this repository are intentionally public.
- Publishing dictionary data to these sites is pre-authorized. Do not request additional consent before deploying dictionary-data updates to them.
