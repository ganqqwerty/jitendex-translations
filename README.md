# README — Jitendex Russian translation pipeline

README-1 — This repository translates the frozen Jitendex dictionary into Russian with Luna, stores every attempt and accepted result in PostgreSQL, and builds verified Yomitan, GoldenDict, MDict, PocketBook, and Apple Dictionary archives.

README-2 — PostgreSQL is authoritative. SQLite files and old pilot scripts are migration evidence only. Never direct production writes back to SQLite.

README-3 — Run 59 completed the frozen Jitendex `2026.07.09.0` snapshot: 433,885 articles, 431,545 headwords, and 2,053,045 accepted translation units. There is no untranslated work in this snapshot.

## README-START — Start here

README-START-1 — A new developer should read these files in this order: [developer tooling](DEVELOPER_TOOLING.md), [Luna operations](JPDB_LUNA_ORCHESTRATION_RUNBOOK.md), [completed-run history](JPDB_LUNA_RUN_HISTORY.md), and [exporter plan](JITENDEX_EXPORTER_PLAN.md).

README-START-2 — Bootstrap Python from the checked-in lock file. Python 3.12 or newer works; the reference workstation uses Python 3.13.

~~~bash
git clone REPOSITORY_URL jitendex-translations
cd jitendex-translations
uv sync --extra test
export PYTHONPATH="$PWD/src"
PYTHONPATH=src .venv/bin/pytest -q
~~~

README-START-3 — Start Docker PostgreSQL and export `JITENDEX_POSTGRES_URL` exactly as shown in [TOOL-PG](DEVELOPER_TOOLING.md). Every `translationctl`, runner, verifier, and exporter command needs that environment variable.

README-START-4 — Confirm the current state before changing anything.

~~~bash
docker ps --filter name=jitendex-postgres
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml report progress
git status --short
~~~

## README-MAP — Important files

| ID | Path | Purpose |
|---|---|---|
| README-MAP-1 | `config.luna.toml` | Authoritative PostgreSQL, model, prompt, source, schema, and batch configuration |
| README-MAP-2 | `prompts/translate_luna_v4.txt` | Pinned Luna translation prompt; changing it changes provenance |
| README-MAP-3 | `terminology/jitendex-tags-ru.csv` | Exact authority for 236 Russian tag labels and tooltips |
| README-MAP-4 | `scripts/prepare_luna_run.py` | Timed, no-Luna creation of the next same-snapshot production run |
| README-MAP-5 | `scripts/run_luna_online_window.py` | Production-safe concurrency window, monitoring, drain, and evidence writer |
| README-MAP-6 | `scripts/run_codex_batches.py` | Isolated bundled-Codex dispatcher and deterministic response ingester |
| README-MAP-7 | `src/jitendex_ru/` | Database, selection, extraction, validation, acceptance, and exporter code |
| README-MAP-8 | `reports/luna_performance/online/` | Immutable per-window performance summaries |
| README-MAP-9 | `work/luna_performance/online/` | Per-event runner logs for online windows |
| README-MAP-10 | `dist/` | Final non-overwriting dictionary archives |

## README-ARCH — Translation contract

README-ARCH-1 — The active pipeline is `lexicographer-v2`. Luna receives the Japanese term, structured Jitendex evidence, examples, metadata, protected tokens, and one immutable batch manifest. English is evidence, not text to translate.

README-ARCH-2 — The runner invokes `gpt-5.6-luna` at medium reasoning through the bundled ChatGPT Codex executable. Each model request runs ephemerally in a read-only temporary workspace and receives a generated output schema that fixes batch IDs, unit IDs, and source hashes.

README-ARCH-3 — Only the coordinator talks to PostgreSQL. It claims a lease, launches one isolated request, records usage, validates the response, ingests accepted fields, and deterministically retries or splits failures. Workers never edit source files or the database.

README-ARCH-4 — Successful responses may change only translatable glossary sets and scalar labels or examples. The assembler preserves Japanese text, article structure, lists, tables, ruby, links, media, tags, attribution, and protected tokens.

README-ARCH-5 — Approved tag terminology is applied during export instead of rewriting historical Luna responses. Missing, duplicate, incomplete, or colliding tag identities stop the build.

## README-STATE — Verified Run 59 releases

| ID | Format | Export | SHA-256 |
|---|---|---|---|
| README-STATE-1 | Yomitan `tags-ru-v1` | 66 | `c157b41f3fc99a52d4099c8384e87c8e0ec8813e87c93f988a801c3e9fc63a58` |
| README-STATE-2 | GoldenDict | 67 | `f81e9c8d41139a8cee09b5333587ef723797b12580e5e3e5db8a2714efe589e0` |
| README-STATE-3 | MDict | 70 | `9d766506f0aeeb0580f6dcf1679a2bde2faffb9586fa73397a201375e54bc7e0` |
| README-STATE-4 | PocketBook | 71 | `348be94570d633078158babd87a5719c13542b201768960e5758e36f00ebb31d` |
| README-STATE-5 | Apple Dictionary | 72 | `3bedac203b1591184563b6cda2d348d6e21ee041d5b97b910e8723d11c72e3dc` |

README-STATE-6 — Export 65 is the immutable pre-tag-unification Yomitan checkpoint. Export records 68 and 69 are reproducibility evidence, not release archives.

README-STATE-7 — PocketBook, MDict, and Apple Dictionary pass structural archive verification but remain experimental until their real-client gates in `reports/exporters/` pass. The Yomitan clean-profile hover test is also still manual.

## README-TEST — Verification

README-TEST-1 — Run the full suite before a production preparation, after code changes, and before a release commit.

~~~bash
PYTHONPATH=src .venv/bin/pytest -q
~~~

README-TEST-2 — Two PostgreSQL recovery tests skip unless `JITENDEX_TEST_POSTGRES_URL` points to a disposable database. Never point that variable at the production `jitendex` database.

README-TEST-3 — Every release archive must pass its matching `verify*` command with the production database URL exported. A ZIP hash without a matching verified database export record is not a release.

## README-OLD — Historical material

README-OLD-1 — Old SQLite plans, pilots, comparison models, benchmarks, and one-off scripts are project archaeology. Use them only when the active PostgreSQL workflow is blocked or a task explicitly asks for them.

README-OLD-2 — [JPDB_LUNA_RUN_HISTORY.md](JPDB_LUNA_RUN_HISTORY.md) records completed outcomes and incidents. Do not copy commands from old incidents when the current runbook gives a newer procedure.

## README-DEMO — Public demos

README-DEMO-1 — The [translation comparison](https://ganqqwerty.github.io/jitendex-translations/) and [frequency analysis](https://ganqqwerty.github.io/jitendex-translations/frequency/) are intentionally public dictionary demos.
