# README — Jitendex Russian translation pipeline

README-1 — This repository implements the deterministic part of the workflow in
[`PLAN.md`](PLAN.md): pinned acquisition, SQLite-backed imports and audit state,
Jitendex selection, safe scalar-unit extraction, immutable worker
manifests, strict response validation, independent review ingestion, and a
reproducible Yomitan ZIP build.

README-2 — The active `lexicographer-v2` pipeline treats the English Jitendex article as
evidence, not as text to translate. Terra first understands the article and its
preservation inventory, then authors Russian wording from the Japanese term,
examples, and linguistic metadata. English synonyms inside one sense are sent
as a single `glossary_set`; the response may contain a different number of
Russian definitions. The assembler changes only that glossary content and
scalar Russian labels/examples while retaining tables, Japanese examples,
ruby, links, sense structure, media, and attribution.

README-3 — Runs are isolated in the same SQLite database. `run.pipeline_version`, prompt
hashes, run-scoped unit IDs, and `run_article` fingerprints keep v2 units,
batches, attempts, reviews, and exports separate from the completed scalar-v1
results. Do not delete run 1 when starting v2.

README-4 — Requires Python 3.12+, `zstd` for modern Anki packages, and the two pinned
source artifacts. Install locally with:

```sh
python -m pip install -e '.[test]'
cp config.example.toml config.toml
translationctl --config config.toml init-db
translationctl --config config.toml acquire
translationctl --config config.toml import-sources
```

README-5 — Run `translationctl --help` for the complete staged workflow. Worker and review
agents only read manifests from `work/inbox` and write strict JSON to outbox
paths; they never edit the database or source JSON.

README-6 — The normal sequence after import is `resolve-scope`, review the unresolved JSON
from `report scope`, `apply-resolutions`, `extract-units`, `make-batches`, then
repeat `claim`/`ingest-response`. After all translation batches pass,
`make-review-batches` starts the independent review pass. `validate`, `build`,
and `verify` close the release gate. A third failed attempt is split
deterministically; a single-unit failure is blocked for adjudication.

README-7 — `claim --batch-id ID` can reserve a specific ready batch for a focused pilot.

README-8 — `acquire` also downloads the two Yomitan JSON schemas from an immutable upstream
commit and verifies their configured SHA-256 values. `verify` validates every
emitted bank against those pinned copies.

## README-GD — GoldenDict export

README-GD-1 — `export-goldendict --run-id ID --output dist/jitendex-ru-goldendict.zip`
builds the accepted database run as a reproducible StarDict 2.4.2 bundle. Run
`verify-goldendict PATH` before release.

README-GD-2 — Extract the ZIP into one folder. Add that folder as a GoldenDict
dictionary source and rescan dictionaries. The bundle contains HTML articles,
reading aliases, internal links, CSS, and referenced media.

README-GD-3 — The exporter converts AVIF graphics to PNG for compatibility with
older GoldenDict renderers. SVG glyphs remain SVG so they stay sharp.

## README-DB — Database schema

README-DB-1 — The current SQLite schema is version 7. `init-db` creates it, and normal database initialization upgrades older frequency tables in place.

README-DB-2 — Frequency provenance has three layers. `frequency_source` pins each active source snapshot and rank limit. `frequency_term` stores one row per exact normalized term. `frequency_article` maps that exact term to every matching Jitendex article.

README-DB-3 — Frequency ranks are not identities and may repeat. `frequency_term` is keyed by `(source, source_sha256, term)`. `frequency_article` is keyed by `(source, source_sha256, term, article_id)`. This preserves tied ranks and makes every article mapping traceable to its headword.

README-DB-4 — The version-7 migration preserves version-6 terms and mappings while adding the term to each article mapping. Back up the production database and run SQLite integrity and foreign-key checks before continuing a release.

README-DB-5 — Use [JPDB_LUNA_ORCHESTRATION_RUNBOOK.md](JPDB_LUNA_ORCHESTRATION_RUNBOOK.md) for operational commands. The combined six-list top-40k scope is a one-off supplement described in [FREQUENCY_TOP40K_TRANSLATION_PLAN.md](FREQUENCY_TOP40K_TRANSLATION_PLAN.md); normal releases continue by JPDB frequency.
