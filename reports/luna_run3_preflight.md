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

## Frozen pilot selection

- Selection artifact: `protocols/luna_pilot_articles_v1.json`
- Selection SHA-256 (canonical payload): `9e60b1593b739f62c340b45b545f85ca8a59959e4235cbc0c42528d6c68348a8`
- Articles: `57`
- Units: `2,377`
- Articles over 24 KiB included: `15` (all)
- Role counts: glossary set `584`, label `114`, example `247`, POS `266`, tooltip `586`, note `208`, xref gloss `264`, register `108`

The selector deterministically includes minimum/median/p95/maximum serialized sizes, the maximum-unit article, single- and multi-sense entries, Japanese examples, protected tokens, numbers/identifiers, kana-only entries, forms, xrefs, antonyms, sense notes, language-source notes, and culture/domain metadata. High-risk roles use a frozen 110-unit target; all other roles use 100.

## Independent profile runs

The frozen pilot was materialized in three distinct runs so attempts, translations, retries, and review decisions cannot collide between profiles.

| Profile | Run | Batches | Articles | Units | Batch gate |
|---|---:|---:|---:|---:|---|
| Conservative 6 / 24 KiB / 100 | 4 | 41 | 57 | 2,377 | pass |
| Balanced 8 / 32 KiB / 140 | 5 | 37 | 57 | 2,377 | pass |
| Current control 12 / 48 KiB / 200 | 6 | 35 | 57 | 2,377 | pass |

Every profile independently passes the run-2 source identity gate. Batch verification found zero missing or extra articles, duplicate units, membership mismatches, soft-cap violations in grouped batches, or hard-cap violations in singleton batches.

## Remaining gate before translation

No translation manifest has been sent. Production and pilot dispatch remain blocked on exact official input-token counts for the complete request bodies. The authenticated Codex transport reports aggregate tokens after execution but does not expose the required input/cached-input/output audit or the input-token-count endpoint. An API credential or equivalent audited Responses transport is required before the pilot can proceed without weakening the frozen protocol.

The `audit-input-tokens` command is implemented against `POST /v1/responses/input_tokens`. It constructs the same tool-free, stateless request body intended for dispatch, including the Luna prompt, separate manifest input, medium/current-turn reasoning configuration, and strict schema. The command currently fails closed with `OPENAI_API_KEY is required for exact input-token counting`; it has not emitted estimated counts or sent a manifest.
