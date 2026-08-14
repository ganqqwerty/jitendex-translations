# README — Колобок 400k translation pipeline

README-1 — This repository builds `Колобок 400k`, a Russian dictionary derived from Jitendex. The deterministic pipeline covers acquisition, imports, audit state, translation, validation, and reproducible exports for Yomitan, GoldenDict, MDict, PocketBook, and Apple Dictionary.

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

## README-EX — Rich dictionary exporters

README-EX-1 — The PocketBook, Apple Dictionary, and MDict exporters start from the
same localized structured article model. They retain lists, tables, ruby,
examples, links, media, semantic classes, tags, tooltips, and attribution when
the target can express them. Read [JITENDEX_EXPORTER_PLAN.md](JITENDEX_EXPORTER_PLAN.md)
and the contracts under `reports/exporters/` before release work.

README-EX-2 — PocketBook requires an external, hashed `converter.exe` and a pinned
`jaK` or `jaR` language directory. On non-Windows hosts it also requires Wine.
The package remains experimental until the device gates in
`reports/exporters/pocketbook-capabilities.md` pass.

```sh
translationctl export-pocketbook --run-id ID --output dist/jitendex-ru-pocketbook.zip \
  --compiler /path/to/converter.exe --compiler-sha256 SHA256 \
  --language-dir /path/to/jaK
translationctl verify-pocketbook dist/jitendex-ru-pocketbook.zip
```

README-EX-3 — Apple Dictionary requires the archived Dictionary Development Kit
`build_dict.sh`. A matching RELAX NG schema and hash are optional command inputs
but required to close the release gate. The exporter does not install the bundle.

```sh
translationctl export-apple-dictionary --run-id ID \
  --output dist/jitendex-ru-apple-dictionary.zip \
  --build-tool /path/to/build_dict.sh --build-tool-sha256 SHA256 \
  --schema /path/to/AppleDictionarySchema.rng --schema-sha256 SHA256
translationctl verify-apple-dictionary dist/jitendex-ru-apple-dictionary.zip
```

README-EX-4 — MDict uses the pinned `mdict-utils` writer to emit deterministic,
unencrypted MDict 2.0 MDX and MDD files. The package is marked experimental until
the real-client matrix in `reports/exporters/mdict-capabilities.md` passes.

| ID | Format | Export | SHA-256 |
|---|---|---|---|
| README-STATE-1 | Yomitan `tags-ru-v1` | 78 | `063893f6d9453de4fec184b17860ea7e7608f9875a667e45d6046029e7736723` |
| README-STATE-2 | GoldenDict | 79 | `c3180d533c3f472eed1e1d91004591117d9d40701aa4e25d19a2dbaaade923a0` |
| README-STATE-3 | MDict | 80 | `2dd86064af2fbd62d4e40ad2a24a8b1f19b7e229260acc0a2d998b2ddc3de36d` |
| README-STATE-4 | PocketBook | 81 | `be97c6bd3d3b49ec24bd08fe2e7ad45343994fa3d2832e295208daefdd2664ee` |
| README-STATE-5 | Apple Dictionary | 82 | `1b1116b61db7369621de8cf443f42de26d1ad39c03715f0aeaed4d0ecfd42b64` |

```sh
translationctl export-mdict --run-id ID --output dist/jitendex-ru-mdict.zip
translationctl verify-mdict dist/jitendex-ru-mdict.zip
```

README-EX-5 — Every exporter writes a deterministic ZIP manifest, loss ledger,
capability profile, source and tool hashes, attribution, and installation note.
Any omitted rich-content feature fails the build.

README-STATE-8 — Every current `Колобок 400k` archive credits Yuri Katkov as co-author of the Russian edition. The five archives use the Latin base name `jp-ru-kolobok-400k` and are published in release `run59-tags-ru-v1`.

## README-DB — Database schema

README-DB-1 — The current SQLite schema is version 7. `init-db` creates it, and normal database initialization upgrades older frequency tables in place.

README-DB-2 — Frequency provenance has three layers. `frequency_source` pins each active source snapshot and rank limit. `frequency_term` stores one row per exact normalized term. `frequency_article` maps that exact term to every matching Jitendex article.

README-DB-3 — Frequency ranks are not identities and may repeat. `frequency_term` is keyed by `(source, source_sha256, term)`. `frequency_article` is keyed by `(source, source_sha256, term, article_id)`. This preserves tied ranks and makes every article mapping traceable to its headword.

README-DB-4 — The version-7 migration preserves version-6 terms and mappings while adding the term to each article mapping. Back up the production database and run SQLite integrity and foreign-key checks before continuing a release.

README-DB-5 — Use [JPDB_LUNA_ORCHESTRATION_RUNBOOK.md](JPDB_LUNA_ORCHESTRATION_RUNBOOK.md) for operational commands. The combined six-list top-40k scope is a one-off supplement described in [FREQUENCY_TOP40K_TRANSLATION_PLAN.md](FREQUENCY_TOP40K_TRANSLATION_PLAN.md); normal releases continue by JPDB frequency.

## README-DEMO — Public demos

README-DEMO-1 — The [project home page](https://ganqqwerty.github.io/jitendex-translations/) introduces the Russian dictionary and links to its current downloads.

README-DEMO-2 — The [frequency analysis](https://ganqqwerty.github.io/jitendex-translations/frequency/) shows the source-list coverage used to plan translation scopes.

README-DEMO-3 — The [translation comparison](https://ganqqwerty.github.io/jitendex-translations/comparison/) shows public samples from the completed dictionary batches.
