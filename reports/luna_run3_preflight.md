# RPT-LUNA3 — Luna run 3 preflight

RPT-LUNA3-1 — Date: 2026-08-09

## RPT-LUNA3-MODEL — Model route

RPT-LUNA3-MODEL-1 — Transport preflight: bundled Codex CLI `0.147.0-alpha.6.5`

RPT-LUNA3-MODEL-2 — Requested model: `gpt-5.6-luna`

RPT-LUNA3-MODEL-3 — Requested reasoning effort: `medium`

RPT-LUNA3-MODEL-4 — Isolation: ephemeral session, `/private/tmp`, read-only sandbox, ignored user config and project rules, no repository input

RPT-LUNA3-MODEL-5 — Result: `LUNA_PREFLIGHT_OK`

RPT-LUNA3-MODEL-6 — Corpus data sent: none

RPT-LUNA3-MODEL-7 — The older shell-default Codex CLI `0.142.0` rejected Luna and was not used.

## RPT-LUNA3-RUN — Run creation and source identity

RPT-LUNA3-RUN-1 — Returned Luna run ID: `3`

RPT-LUNA3-RUN-2 — Articles: `1,704`

RPT-LUNA3-RUN-3 — Translation units: `27,518`

RPT-LUNA3-RUN-4 — Missing source identities relative to run 2: `0`

RPT-LUNA3-RUN-5 — Extra source identities relative to run 2: `0`

RPT-LUNA3-RUN-6 — Identity tuple: `(article_id, json_pointer, role, source_sha256)`

RPT-LUNA3-RUN-7 — Role inventory:

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

## RPT-LUNA3-INVAR — Historical invariants

RPT-LUNA3-INVAR-1 — Run-scoped fingerprints were captured after the schema-only audit migration and before run 3 creation, then recomputed afterward.

| Run | Before | After | Result |
|---|---|---|---|
| 1 | `4eb07f65ba5f5aed44a3a6de232170721591f78af9f8614d1814fa9665816140` | `4eb07f65ba5f5aed44a3a6de232170721591f78af9f8614d1814fa9665816140` | unchanged |
| 2 | `227a2aff3c2a6ec825ab3b98d6c0f980b480b031c352dbc6a837a7ac38461c66` | `227a2aff3c2a6ec825ab3b98d6c0f980b480b031c352dbc6a837a7ac38461c66` | unchanged |

RPT-LUNA3-INVAR-2 — The fingerprints cover the run row and every run-owned `translation_unit`, `run_article`, `batch`, `batch_item`, `attempt`, `translation`, `review`, `validation_issue`, `export`, and `export_file` row.

## RPT-LUNA3-MANIFEST — Conservative manifests

RPT-LUNA3-MANIFEST-1 — Soft profile: 6 articles / 24 KiB / 100 units

RPT-LUNA3-MANIFEST-2 — Hard article ceiling: 48 KiB / 200 units

RPT-LUNA3-MANIFEST-3 — Manifests created: `487`

RPT-LUNA3-MANIFEST-4 — Singleton manifests: `70`

RPT-LUNA3-MANIFEST-5 — Median articles: `4`

RPT-LUNA3-MANIFEST-6 — Median serialized bytes: `20,824`

RPT-LUNA3-MANIFEST-7 — Maximum serialized bytes: `35,108`

RPT-LUNA3-MANIFEST-8 — Median units: `58`

RPT-LUNA3-MANIFEST-9 — The live result differs from the earlier 483-manifest simulation by four manifests. No expected count was forced; the current database, serializer, prompt/config hashes, and deterministic packing implementation are authoritative.

## RPT-LUNA3-PILOT — Frozen pilot selection

RPT-LUNA3-PILOT-1 — Selection artifact: `protocols/luna_pilot_articles_v1.json`

RPT-LUNA3-PILOT-2 — Selection SHA-256 (canonical payload): `9e60b1593b739f62c340b45b545f85ca8a59959e4235cbc0c42528d6c68348a8`

RPT-LUNA3-PILOT-3 — Articles: `57`

RPT-LUNA3-PILOT-4 — Units: `2,377`

RPT-LUNA3-PILOT-5 — Articles over 24 KiB included: `15` (all)

RPT-LUNA3-PILOT-6 — Role counts: glossary set `584`, label `114`, example `247`, POS `266`, tooltip `586`, note `208`, xref gloss `264`, register `108`

RPT-LUNA3-PILOT-7 — The selector deterministically includes minimum/median/p95/maximum serialized sizes, the maximum-unit article, single- and multi-sense entries, Japanese examples, protected tokens, numbers/identifiers, kana-only entries, forms, xrefs, antonyms, sense notes, language-source notes, and culture/domain metadata. High-risk roles use a frozen 110-unit target; all other roles use 100.

## RPT-LUNA3-PROFILE — Independent profile runs

RPT-LUNA3-PROFILE-1 — The frozen pilot was materialized in three distinct runs so attempts, translations, retries, and review decisions cannot collide between profiles.

| Profile | Run | Batches | Articles | Units | Batch gate |
|---|---:|---:|---:|---:|---|
| Conservative 6 / 24 KiB / 100 | 4 | 41 | 57 | 2,377 | pass |
| Balanced 8 / 32 KiB / 140 | 5 | 37 | 57 | 2,377 | pass |
| Current control 12 / 48 KiB / 200 | 6 | 35 | 57 | 2,377 | pass |

RPT-LUNA3-PROFILE-2 — Every profile independently passes the run-2 source identity gate. Batch verification found zero missing or extra articles, duplicate units, membership mismatches, soft-cap violations in grouped batches, or hard-cap violations in singleton batches.

## RPT-LUNA3-GATE — Remaining gate before translation

RPT-LUNA3-GATE-1 — No translation manifest has been sent. Production and pilot dispatch remain blocked on exact official input-token counts for the complete request bodies. The authenticated Codex transport reports aggregate tokens after execution but does not expose the required input/cached-input/output audit or the input-token-count endpoint. An API credential or equivalent audited Responses transport is required before the pilot can proceed without weakening the frozen protocol.

RPT-LUNA3-GATE-2 — The `audit-input-tokens` command is implemented against `POST /v1/responses/input_tokens`. It constructs the same tool-free, stateless request body intended for dispatch, including the Luna prompt, separate manifest input, medium/current-turn reasoning configuration, and strict schema. The command currently fails closed with `OPENAI_API_KEY is required for exact input-token counting`; it has not emitted estimated counts or sent a manifest.
