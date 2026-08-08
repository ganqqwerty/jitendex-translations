# Luna run 3 preflight

Date: 2026-08-09

## Model route

- Transport preflight: bundled Codex CLI `0.147.0-alpha.6.5`
- Requested model: `gpt-5.6-luna`
- Requested reasoning effort: `medium`
- Isolation: ephemeral session, `/private/tmp`, read-only sandbox, ignored user config and project rules, no repository input
- Result: `LUNA_PREFLIGHT_OK`
- Corpus data sent: none

The older shell-default Codex CLI `0.142.0` rejected Luna and was not used.

## Run creation and source identity

- Returned Luna run ID: `3`
- Articles: `1,704`
- Translation units: `27,518`
- Missing source identities relative to run 2: `0`
- Extra source identities relative to run 2: `0`
- Identity tuple: `(article_id, json_pointer, role, source_sha256)`

Role inventory:

| Role | Units |
|---|---:|
| `tooltip` | 8,992 |
| `glossary_set` | 5,580 |
| `pos` | 4,172 |
| `example` | 3,176 |
| `note` | 1,784 |
| `xref_gloss` | 1,650 |
| `register` | 1,108 |
| `label` | 1,056 |

## Historical invariants

Run-scoped fingerprints were captured after the schema-only audit migration and before run 3 creation, then recomputed afterward.

| Run | Before | After | Result |
|---|---|---|---|
| 1 | `4eb07f65ba5f5aed44a3a6de232170721591f78af9f8614d1814fa9665816140` | `4eb07f65ba5f5aed44a3a6de232170721591f78af9f8614d1814fa9665816140` | unchanged |
| 2 | `227a2aff3c2a6ec825ab3b98d6c0f980b480b031c352dbc6a837a7ac38461c66` | `227a2aff3c2a6ec825ab3b98d6c0f980b480b031c352dbc6a837a7ac38461c66` | unchanged |

The fingerprints cover the run row and every run-owned `translation_unit`, `run_article`, `batch`, `batch_item`, `attempt`, `translation`, `review`, `validation_issue`, `export`, and `export_file` row.

## Conservative manifests

- Soft profile: 6 articles / 24 KiB / 100 units
- Hard article ceiling: 48 KiB / 200 units
- Manifests created: `487`
- Singleton manifests: `70`
- Median articles: `4`
- Median serialized bytes: `20,824`
- Maximum serialized bytes: `35,108`
- Median units: `58`

The live result differs from the earlier 483-manifest simulation by four manifests. No expected count was forced; the current database, serializer, prompt/config hashes, and deterministic packing implementation are authoritative.

## Remaining gate before translation

No translation manifest has been sent. Production and pilot dispatch remain blocked on exact official input-token counts for the complete request bodies. The authenticated Codex transport reports aggregate tokens after execution but does not expose the required input/cached-input/output audit or the input-token-count endpoint. An API credential or equivalent audited Responses transport is required before the pilot can proceed without weakening the frozen protocol.
