# TOOL — Developer tooling and reproducible setup

TOOL-1 — This file describes every tool used by the active PostgreSQL translation and export workflow. The exact batch procedure is in [JPDB_LUNA_ORCHESTRATION_RUNBOOK.md](JPDB_LUNA_ORCHESTRATION_RUNBOOK.md).

TOOL-2 — Commands assume macOS, a clone of this repository, Docker Desktop, ChatGPT.app, and a shell at the repository root. Store databases, compiler kits, Wine prefixes, and large temporary files outside Documents and iCloud.

## TOOL-REF — Reference workstation

| ID | Tool | Reference version | Required use |
|---|---|---|---|
| TOOL-REF-1 | macOS | 26.5.2 arm64 | Host for ChatGPT, Docker, Wine, and Apple Dictionary |
| TOOL-REF-2 | Git | 2.50.1 | Source control and pinned external-tool checkouts |
| TOOL-REF-3 | uv | 0.11.8 | Python environment from `uv.lock` |
| TOOL-REF-4 | Python | 3.13.5; project minimum 3.12 | Pipeline, tests, runners, and exporters |
| TOOL-REF-5 | Docker Desktop | Docker 29.4.1 | Authoritative PostgreSQL container and volume |
| TOOL-REF-6 | PostgreSQL | 17.10 in `postgres:17-bookworm` | All production state and audit history |
| TOOL-REF-7 | bundled Codex CLI | `codex-cli 0.147.0-alpha.6.5` when last measured | Authenticated Luna request transport |
| TOOL-REF-8 | zstd | 1.5.7 | Modern Anki source extraction |
| TOOL-REF-9 | Wine Stable | 11.0 | Runs the Windows PocketBook compiler on macOS |
| TOOL-REF-10 | xmllint | libxml 2.9.13 | Optional RELAX NG checks |
| TOOL-REF-11 | CodeGraph | 0.9.3 | Structural code search required by `AGENTS.md` |

TOOL-REF-12 — Version output is evidence, not a blanket upgrade instruction. Preserve `uv.lock`, PostgreSQL major version 17, prompt hashes, source hashes, and external compiler hashes during a run.

TOOL-REF-13 — CodeGraph on the reference workstation uses Node.js 24.15.0, npm 11.12.1, and `@colbymchenry/codegraph@0.9.3`. Node is a development-search dependency, not part of dictionary output.

## TOOL-HOST — Install host tools

TOOL-HOST-1 — Install Homebrew separately, then install the command-line dependencies. Docker Desktop and ChatGPT.app are graphical applications and must be opened once so their services and authentication are ready.

~~~bash
brew install uv zstd node
brew install --cask docker
brew install --cask wine-stable
~~~

TOOL-HOST-2 — ChatGPT.app supplies the only production model executable used by the runner. Confirm it exists and the user is signed in before a Luna run.

~~~bash
test -x /Applications/ChatGPT.app/Contents/Resources/codex
/Applications/ChatGPT.app/Contents/Resources/codex --version
~~~

TOOL-HOST-3 — The runner refuses an alternate executable in production. `JITENDEX_TEST_CODEX_EXECUTABLE` works only with explicit SQLite runner-test mode and must never be set in a production shell.

TOOL-HOST-4 — Initialize CodeGraph once in a new worktree. Use its symbol, caller, callee, and impact queries for structural work; use `rg` only for literal text and known files.

~~~bash
npm install --global @colbymchenry/codegraph@0.9.3
codegraph init -i
codegraph status
~~~

TOOL-HOST-5 — The commands also use macOS system tools: `openssl` creates a fresh database password; `shasum` records SHA-256 evidence; `ditto` copies the DDK bundle; `pgrep` proves runner absence; and `awk`, `tee`, `date`, and `unzip` support safe shell operation. They need no separate installation on the reference workstation.

## TOOL-PY — Python environment

TOOL-PY-1 — Create or refresh `.venv` only from the checked-in project and lock file. `mdict-utils==1.3.14`, Pillow, fastjsonschema, psycopg 3.2.9, and pytest are installed through this step.

~~~bash
uv sync --extra test
export PYTHONPATH="$PWD/src"
.venv/bin/python --version
PYTHONPATH=src .venv/bin/translationctl --help
PYTHONPATH=src .venv/bin/pytest -q
~~~

TOOL-PY-2 — Do not run production scripts with an unrelated global Python. Use `.venv/bin/python` and `.venv/bin/translationctl` so the lock file controls dependencies.

## TOOL-PG — Authoritative PostgreSQL

TOOL-PG-1 — `compose.postgres.yml` creates `jitendex-postgres` from `postgres:17-bookworm`, publishes it on loopback port 5433 by default, enables `pg_stat_statements`, uses data checksums, and stores data in the named Docker volume `jitendex-postgres-data`.

TOOL-PG-2 — Create a fresh container with a generated password. Do not type a reusable password into shell history.

~~~bash
export POSTGRES_PASSWORD="$(openssl rand -hex 32)"
docker compose -f compose.postgres.yml up -d
unset POSTGRES_PASSWORD
docker inspect jitendex-postgres --format '{{.State.Health.Status}}'
~~~

TOOL-PG-3 — Build the production URL from the running container every time. Never assume the host port is 5432, never print the password, and never write the full URL into reports or command logs.

~~~bash
JITENDEX_DB_PASSWORD="$(docker exec jitendex-postgres printenv POSTGRES_PASSWORD)"
JITENDEX_DB_PORT="$(docker port jitendex-postgres 5432/tcp | awk -F: 'END {print $NF}')"
export JITENDEX_POSTGRES_URL="postgresql://jitendex:${JITENDEX_DB_PASSWORD}@127.0.0.1:${JITENDEX_DB_PORT}/jitendex"
unset JITENDEX_DB_PASSWORD JITENDEX_DB_PORT
~~~

TOOL-PG-4 — Initialize only a new empty database. Existing production databases must not be reinitialized.

~~~bash
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml init-db
~~~

TOOL-PG-5 — Check container health, database identity, extension availability, and disk space before a production write.

~~~bash
docker inspect jitendex-postgres --format '{{.State.Health.Status}}'
docker exec jitendex-postgres psql -U jitendex -d jitendex -v ON_ERROR_STOP=1 -c \
  "SELECT current_database(), current_user, version();"
docker exec jitendex-postgres psql -U jitendex -d jitendex -v ON_ERROR_STOP=1 -c \
  "SELECT extname FROM pg_extension WHERE extname='pg_stat_statements';"
docker exec jitendex-postgres df -h /var/lib/postgresql/data
~~~

TOOL-PG-6 — Docker Desktop's disk image is configured for 264 GB and lives under `~/Library/Containers`, outside iCloud. Keep at least enough free space for PostgreSQL temporary files, one dump, and exporter work. Do not bind-mount PostgreSQL into Documents.

## TOOL-BACKUP — PostgreSQL backup gate

TOOL-BACKUP-1 — Make a unique custom-format dump before run preparation, tag import, migration, or repair. The example writes the final dump to `work/backups`; for very large temporary work, use `/private/tmp` and copy only the validated final dump.

~~~bash
mkdir -p work/backups
JITENDEX_BACKUP_PATH="$PWD/work/backups/jitendex-postgresql-before-PURPOSE.dump"
docker exec jitendex-postgres pg_dump -U jitendex -d jitendex --format=custom \
  > "$JITENDEX_BACKUP_PATH"
docker exec -i jitendex-postgres pg_restore --list < "$JITENDEX_BACKUP_PATH" > /dev/null
shasum -a 256 "$JITENDEX_BACKUP_PATH"
unset JITENDEX_BACKUP_PATH
~~~

TOOL-BACKUP-2 — Record the filename, SHA-256, elapsed time, source run, and reason in [JPDB_LUNA_RUN_HISTORY.md](JPDB_LUNA_RUN_HISTORY.md). A nonempty file is not enough; `pg_restore --list` must succeed.

TOOL-BACKUP-3 — Never restore over production during ordinary recovery. First stop every writer, preserve the failed database and logs, restore into a separate disposable database, verify it, and obtain explicit authorization before replacing production.

## TOOL-SOURCE — Pinned source and terminology tools

TOOL-SOURCE-1 — `config.luna.toml` pins the Jitendex ZIP, Kaishi package, Yomitan schemas, model, prompts, pipeline versions, and batch limits by version and SHA-256. `translationctl acquire` downloads and verifies those artifacts.

~~~bash
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml acquire
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml import-sources
~~~

TOOL-SOURCE-2 — Run `acquire` and `import-sources` only for a new database or an explicitly approved source refresh. Do not change a source URL, version, or hash while a run is active.

TOOL-SOURCE-3 — Import the approved Russian tag workbook only after a PostgreSQL backup. Resolve the current Jitendex snapshot ID without guessing it.

~~~bash
JITENDEX_SNAPSHOT_ID="$(docker exec jitendex-postgres psql -U jitendex -d jitendex -Atc \
  "SELECT id FROM source_snapshot WHERE kind='jitendex' ORDER BY id DESC LIMIT 1")"
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  import-approved-tags --csv terminology/jitendex-tags-ru.csv \
  --snapshot-id "$JITENDEX_SNAPSHOT_ID"
unset JITENDEX_SNAPSHOT_ID
~~~

TOOL-SOURCE-4 — A repeated unchanged tag import must be a no-op. It must reconcile exactly 236 identities and must not create terminology replacement history for provenance-only changes.

TOOL-SOURCE-5 — `prepare_luna_run.py` can extend only the same `jitendex_snapshot_id` as its source run. Run 59 already covers every article in snapshot `2026.07.09.0`. A newly imported Jitendex snapshot needs an explicitly designed cross-snapshot continuation; do not point the same-snapshot driver at it and assume it will include new articles.

## TOOL-LUNA — Model dispatch tools

TOOL-LUNA-1 — `scripts/prepare_luna_run.py` performs source preflight, same-snapshot scope selection, incremental extraction, accepted-translation reuse, batch creation, parity checks, and timing reports. It makes zero model requests.

TOOL-LUNA-2 — `scripts/run_luna_online_window.py` is the normal production entry point. It refuses SQLite, disposable database names, duplicate window IDs, active runners, missing ready work, non-latest runs, and benchmark override variables.

TOOL-LUNA-3 — `scripts/run_codex_batches.py` claims PostgreSQL leases and launches one bundled Codex process per active worker. Each process uses `exec --ephemeral --ignore-user-config --ignore-rules`, a read-only sandbox, `/private/tmp`, the pinned model and reasoning, a generated output schema, JSON events, and a 180-second request timeout.

TOOL-LUNA-4 — The coordinator records input, cached-input, and output tokens; request IDs; latency; finish state; validation issues; retries; splits; transport failures; and audit events. Response ingestion occurs only after lease ownership and deterministic validation pass.

TOOL-LUNA-5 — Production concurrency is 100. Concurrency 110 was clean but about four percent slower by headword throughput. Do not tune model, prompt, reasoning, batch limits, validator, runner revision, and concurrency in the same window.

TOOL-LUNA-6 — The online wrapper writes summaries to `reports/luna_performance/online/WINDOW.json` and event logs to `work/luna_performance/online/WINDOW.jsonl`. Window IDs are lowercase letters, numbers, and hyphens, 3–64 characters, and are never reused.

## TOOL-DIAG — Diagnostic helpers

TOOL-DIAG-1 — `scripts/snapshot_postgresql_metrics.py` captures one JSON snapshot of PostgreSQL counters, locks, waits, pool state, and database timing. The online wrapper captures equivalent before, during, and after evidence automatically; use the standalone helper only for a diagnosed database issue.

~~~bash
PYTHONPATH=src .venv/bin/python scripts/snapshot_postgresql_metrics.py \
  --postgres-url-env JITENDEX_POSTGRES_URL \
  --output work/postgresql-metrics.json
~~~

TOOL-DIAG-2 — `scripts/verify_database_parity.py` was used to prove the one-time SQLite-to-PostgreSQL migration. It compares a named historical SQLite database with PostgreSQL and can compare their exports. It is not a production-batch gate now, and passing it never makes SQLite writable or authoritative.

TOOL-DIAG-3 — Files named `repair_*`, `recover_*`, or `run_luna_tag_translation.py` are incident-specific or historical. Do not include them in a normal batch. Read their matching run-history incident and inspect the current database before considering one.

## TOOL-EXPORT — Dictionary exporters

TOOL-EXPORT-1 — Every exporter starts from accepted Run 59 rows in PostgreSQL and the approved 236-row tag catalog. Every output is non-overwriting, records a database export row, contains a deterministic manifest, and requires its matching verifier.

TOOL-EXPORT-2 — Set the external-tool root outside Documents and iCloud.

~~~bash
export JITENDEX_EXPORT_TOOL_ROOT="${HOME}/Library/Application Support/jitendex-translations/export-tools"
mkdir -p "$JITENDEX_EXPORT_TOOL_ROOT"
~~~

### TOOL-YOMITAN — Yomitan

TOOL-YOMITAN-1 — Yomitan needs no external compiler. The build validates banks against the pinned upstream schemas and replaces embedded tags, tag-bank names, descriptions, and term references from PostgreSQL.

~~~bash
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  build --run-id 59 \
  --output dist/jp-ru-kolobok-400k-yomitan.zip
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  verify dist/jp-ru-kolobok-400k-yomitan.zip
~~~

TOOL-YOMITAN-2 — After the clean-profile test, copy `dist/yomitan-smoke-template.json` to a new report, insert the verified archive hash, mark only checks actually observed, and identify the tested Yomitan version and profile in `notes`. The notes must also confirm embedded part-of-speech, field, dialect, and tag-bank hover text. Then record the report in PostgreSQL.

~~~bash
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  record-yomitan-smoke reports/yomitan-smoke-run59-tags-ru-v1.json \
  --actor DEVELOPER_NAME
~~~

TOOL-YOMITAN-3 — `record-yomitan-smoke` accepts only a fully passing report tied to a verified archive hash. It records an audit event and closes the run lifecycle state, so never run it before the manual UI work is complete.

### TOOL-GD — GoldenDict

TOOL-GD-1 — GoldenDict needs no external compiler. It emits a reproducible StarDict 2.4.2 package with HTML, aliases, links, CSS, media, Russian tag badges, and Russian hover text.

~~~bash
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  export-goldendict --run-id 59 \
  --output dist/jp-ru-kolobok-400k-goldendict.zip
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  verify-goldendict dist/jp-ru-kolobok-400k-goldendict.zip
~~~

### TOOL-MDICT — MDict

TOOL-MDICT-1 — MDict uses the Python dependency `mdict-utils==1.3.14`. It emits unencrypted MDict 2.0 MDX and MDD files and needs no host compiler.

~~~bash
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  export-mdict --run-id 59 \
  --output dist/jp-ru-kolobok-400k-mdict.zip
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  verify-mdict dist/jp-ru-kolobok-400k-mdict.zip
~~~

### TOOL-PB — PocketBook

TOOL-PB-1 — PocketBook uses Markismus `LanguageFilesPocketbookConverter` at commit `3bb444c7a5b1a011e0fca9e99fba0e7ae025e36f`. The pinned `converter.exe` SHA-256 is `9eda24d32a9bb76697c8c0ca713d6299c7881ade76bfb317b9ac7bf95d06936f`. The production build uses the bundled `jaK` language directory.

TOOL-PB-2 — Reproduce the compiler checkout and verify it before use.

~~~bash
git clone https://github.com/Markismus/LanguageFilesPocketbookConverter.git \
  "$JITENDEX_EXPORT_TOOL_ROOT/LanguageFilesPocketbookConverter"
git -C "$JITENDEX_EXPORT_TOOL_ROOT/LanguageFilesPocketbookConverter" \
  checkout 3bb444c7a5b1a011e0fca9e99fba0e7ae025e36f
shasum -a 256 \
  "$JITENDEX_EXPORT_TOOL_ROOT/LanguageFilesPocketbookConverter/converter.exe"
~~~

TOOL-PB-3 — On macOS use the real Wine binary, not Homebrew's graphical launcher, and keep the Wine prefix outside the repository.

~~~bash
export PATH="/Applications/Wine Stable.app/Contents/Resources/wine/bin:$PATH"
export WINEPREFIX="$JITENDEX_EXPORT_TOOL_ROOT/wine-prefix"
wine --version
~~~

TOOL-PB-4 — Build and verify with the pinned hash.

~~~bash
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  export-pocketbook --run-id 59 \
  --output dist/jp-ru-kolobok-400k-pocketbook.zip \
  --compiler "$JITENDEX_EXPORT_TOOL_ROOT/LanguageFilesPocketbookConverter/converter.exe" \
  --compiler-sha256 9eda24d32a9bb76697c8c0ca713d6299c7881ade76bfb317b9ac7bf95d06936f \
  --language-dir "$JITENDEX_EXPORT_TOOL_ROOT/LanguageFilesPocketbookConverter/jaK"
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  verify-pocketbook dist/jp-ru-kolobok-400k-pocketbook.zip
~~~

### TOOL-APPLE — Apple Dictionary

TOOL-APPLE-1 — Sign in to Apple Developer Downloads and obtain `Additional Tools for Xcode 26.6`. Its DMG SHA-256 is `d7138cebe372b3bf9a4a06669036f6ee75cbe246dcc990e1b71fc98eca241004`. A paid developer membership is not required.

TOOL-APPLE-2 — Mount the DMG and copy `Utilities/Dictionary Development Kit` to the external-tool root with `ditto`. The pinned `build_dict.sh` SHA-256 is `96c60abedd89f1932bf5a54fe65ed03f739423b0434a1afe9e0cec9aae124ffc`.

~~~bash
ditto "/Volumes/Additional Tools/Utilities/Dictionary Development Kit" \
  "$JITENDEX_EXPORT_TOOL_ROOT/Dictionary Development Kit"
shasum -a 256 \
  "$JITENDEX_EXPORT_TOOL_ROOT/Dictionary Development Kit/bin/build_dict.sh"
~~~

TOOL-APPLE-3 — The shipped schema is `documents/DictionarySchema/AppleDictionarySchema.rng`; its hash is `dacdb7713f1a73f47be8446184f58de8fc1a13c0d2f8b822b37c35b137bd63cf`. It includes obsolete remote `thaiopensource.com` modules that are not shipped. Do not install replacement checker modules silently. The verified export therefore uses the real pinned DDK compiler without the optional `--schema` arguments and remains experimental.

TOOL-APPLE-4 — Build and verify the native bundle archive.

~~~bash
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  export-apple-dictionary --run-id 59 \
  --output dist/jp-ru-kolobok-400k-apple-dictionary.zip \
  --build-tool "$JITENDEX_EXPORT_TOOL_ROOT/Dictionary Development Kit/bin/build_dict.sh" \
  --build-tool-sha256 96c60abedd89f1932bf5a54fe65ed03f739423b0434a1afe9e0cec9aae124ffc
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  verify-apple-dictionary dist/jp-ru-kolobok-400k-apple-dictionary.zip
~~~

## TOOL-CLIENT — Manual client gates

TOOL-CLIENT-1 — Yomitan release requires a clean Chrome profile, fresh extension installation, archive import, and hover checks for embedded part-of-speech, field, dialect, and tag-bank badges.

TOOL-CLIENT-2 — GoldenDict release requires extraction into one directory, adding that directory as a dictionary source, rescanning, and checking Russian badges, hover text, links, images, tables, and ruby.

TOOL-CLIENT-3 — PocketBook release requires a real device test. MDict requires a real MDX/MDD client. Apple Dictionary requires installing the `.dictionary` bundle under `~/Library/Dictionaries`, testing Dictionary.app and contextual Look Up, and inspecting light and dark rendering. Structural archive verification alone does not close these gates.

TOOL-CLIENT-4 — The detailed open gates and current evidence are in `reports/exporters/pocketbook-capabilities.md`, `reports/exporters/mdict-capabilities.md`, and `reports/exporters/apple-dictionary-capabilities.md`. Update those contracts when a real client gate changes.

## TOOL-SAFE — Operational safety

TOOL-SAFE-1 — Never put database passwords, the full PostgreSQL URL, Apple credentials, authentication codes, or model-session data in Git, reports, terminal transcripts, or issue text.

TOOL-SAFE-2 — Never overwrite a verified archive. Use a new revision suffix or output name, verify it, record its SHA-256 and export ID, and preserve the old archive.

TOOL-SAFE-3 — Never delete attempts, translations, validation issues, audit events, split parents, online-window JSON, or failed provenance to make a run look clean.

TOOL-SAFE-4 — Never use SQLite for a production continuation, never run two Luna coordinators, and never start a model window before the dry-run and claimed-lease checks pass.
