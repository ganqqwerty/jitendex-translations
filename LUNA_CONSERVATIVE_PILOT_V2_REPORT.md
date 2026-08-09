# Luna conservative pilot v2 report

Date: 2026-08-09  
Run: 7  
Profile: conservative (`6 articles / 24 KiB / 100 units`, soft caps)  
Transport: `codex-agent` only; no OpenAI API requests

## Outcome

The 57 pilot articles are editorially corrected: all 2,377 pilot units have an
accepted translation after blind Terra review, including all 98 reviewer
replacements. No unit needs adjudication. Accepted output contains the literal
Japanese grammatical labels `-ます` and `-て` where applicable and contains no
`-масу` or `-тэ` transliterations.

The v2 notation change fixed the v1 systematic `note` failure. The note
replacement rate fell from 5.29% (11/208) to 0.00% (0/208).

The conservative profile nevertheless does **not** pass the frozen promotion
protocol. Two different systematic terminology problems surfaced in v2:

- `pos`: Luna rendered `1-dan` and `5-dan` as numbered Russian conjugations
  (`1-е/5-е спряжение`) instead of the Japanese verb classes (`1-дан/5-дан`),
  and twice omitted the noun designation in `noun taking する`;
- `register`: Luna rendered the compact label `kana` as instrumental or as an
  adverbial phrase (`каной`, `обычно каной`) instead of the canonical label
  `кана`.

Blind review replaced all affected candidates in the pilot articles. These
errors therefore do not survive in accepted pilot output, but their candidate
replacement rates exceed the frozen per-role limits and must be addressed in a
new prompt version before another promotion attempt.

## Coverage and deterministic validation

| Measure | Result |
|---|---:|
| Selected pilot articles | 57 |
| Pilot units | 2,377 |
| Translation batches | 41 / 41 complete |
| Accepted translation attempts | 41 |
| Rejected translation attempts retained in audit history | 4 |
| Blind review batches | 30 / 30 complete |
| Independently reviewed units | 2,377 / 2,377 (100%) |
| Review decisions needing adjudication | 0 |
| Pilot units with accepted final translations | 2,377 / 2,377 |
| Accepted `-масу` / `-тэ` occurrences | 0 |
| Accepted literal `-ます` / `-て` occurrences | 23 |

The frozen pilot selection hash is
`9e60b1593b739f62c340b45b545f85ca8a59959e4235cbc0c42528d6c68348a8`.
The source identity and `verify-pilot-batches` checks passed before translation.

## Blind-review replacement rates

| Role | Reviewed | Replaced | Pilot rate | Terra baseline | Maximum allowed | Gate |
|---|---:|---:|---:|---:|---:|---|
| `glossary_set` | 584 | 39 | 6.68% | 8.35% | 10.35% | pass |
| `label` | 114 | 0 | 0.00% | 6.53% | 8.53% | pass |
| `example` | 247 | 1 | 0.40% | 4.97% | 6.97% | pass |
| `pos` | 266 | 27 | **10.15%** | 4.22% | 6.22% | **fail** |
| `register` | 108 | 8 | **7.41%** | 3.61% | 5.61% | **fail** |
| `tooltip` | 586 | 21 | 3.58% | 2.85% | 4.85% | pass |
| `note` | 208 | 0 | **0.00%** | 0.95% | 2.95% | **pass** |
| `xref_gloss` | 264 | 2 | 0.76% | 0.55% | 2.55% | pass |
| **Overall** | **2,377** | **98** | **4.12%** | **4.33%** | — | **pass** |

The one-sided 95% Wilson upper bound for the overall replacement rate is
4.85%. Its difference from the 4.33% Terra baseline is +0.52 percentage
points, within the frozen +1.0-point overall margin. The overall gate passes,
but it cannot override either failed role-specific gate.

## Agent and transport constraints

Exactly three isolated Luna translation agents produced the pilot while the
main thread remained the orchestrator. Three isolated Terra Medium agents
performed the blind review. The agents were prohibited from using the OpenAI
API, web search, the progress database, prior translations, or unrelated
repository files. The main thread alone claimed work and ingested validated
responses.

## Decision

Keep the corrected pilot translations as audit evidence, but do not promote
this v2 profile to the 1,500-term production run. Version the translator prompt
again with explicit canonical mappings for `1-dan`, `5-dan`, `noun taking
する`, and the `kana` register label, then rerun the same frozen pilot and blind
review protocol.
