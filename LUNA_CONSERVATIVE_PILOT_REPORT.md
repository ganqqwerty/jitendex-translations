# Luna conservative pilot report

Date: 2026-08-09  
Run: 4  
Profile: conservative (`6 articles / 24 KiB / 100 units`, soft caps)  
Transport: `codex-agent` only; no OpenAI API requests

## Decision

The conservative profile **fails** the frozen non-inferiority protocol and must
not advance to balanced/current-size pilots or production.

The decisive failure is the role-specific `note` gate: 11 of 208 reviewed note
units were replaced (5.29%). The permitted maximum is 2.95%, equal to the Terra
baseline of 0.95% plus the frozen 2.0 percentage-point margin.

This is a systematic defect rather than random wording variance. Ten of the
eleven note replacements concern inconsistent handling of Japanese grammatical
form labels such as `-ます` and `-て`; the remaining replacement concerns the
Russian naming of a Japanese form.

Post-pilot inspection found that the blind reviewers applied both directions:
some replaced `-масу`/`-тэ` with `-ます`/`-て`, while others replaced Japanese
script with Cyrillic transcription. The frozen v1 prompts did not define a
canonical notation. Version 2 therefore standardizes Japanese script (`-ます`,
`-て`) in both the translator and reviewer prompts. The historical v1 gate
result remains recorded, but it should be interpreted as a terminology-policy
failure rather than evidence of a general semantic weakness.

## Coverage and deterministic validation

| Measure | Result |
|---|---:|
| Selected pilot articles | 57 |
| Pilot units | 2,377 |
| Translation batches | 41 / 41 complete |
| Translation attempts accepted | 41 / 41 (100%) |
| Blind review batches | 30 / 30 complete |
| Independently reviewed units | 2,377 / 2,377 (100%) |
| Review decisions needing adjudication | 0 |
| Membership mismatches | 0 |
| Duplicate units | 0 |
| Missing or extra pilot articles | 0 |
| Soft-cap violations | 0 |
| Hard-cap violations | 0 |

The pilot selection hash is
`9e60b1593b739f62c340b45b545f85ca8a59959e4235cbc0c42528d6c68348a8`.
The `verify-pilot-batches` gate passed for run 4.

## Replacement rates

| Role | Reviewed | Replaced | Pilot rate | Terra baseline | Maximum allowed | Gate |
|---|---:|---:|---:|---:|---:|---|
| `glossary_set` | 584 | 32 | 5.48% | 8.35% | 10.35% | pass |
| `label` | 114 | 0 | 0.00% | 6.53% | 8.53% | pass |
| `example` | 247 | 6 | 2.43% | 4.97% | 6.97% | pass |
| `pos` | 266 | 2 | 0.75% | 4.22% | 6.22% | pass |
| `register` | 108 | 0 | 0.00% | 3.61% | 5.61% | pass |
| `tooltip` | 586 | 8 | 1.37% | 2.85% | 4.85% | pass |
| `note` | 208 | 11 | **5.29%** | 0.95% | 2.95% | **fail** |
| `xref_gloss` | 264 | 1 | 0.38% | 0.55% | 2.55% | pass |
| **Overall** | **2,377** | **60** | **2.52%** | **4.33%** | — | pass |

The one-sided 95% Wilson upper bound for the overall replacement rate is
3.11%. Its difference from the 4.33% Terra baseline is -1.22 percentage
points, below the frozen +1.0-point overall margin. The overall gate therefore
passes, but it cannot mask the `note` regression.

## Editorial findings

The 60 replacements comprise:

- 32 `glossary_set` corrections, principally Russian government,
  lexicographic naturalness, terminology, and sense precision;
- 11 `note` corrections, principally Japanese form-label handling;
- 8 `tooltip` terminology corrections;
- 6 example corrections, including participant relation, result-versus-purpose
  meaning, and natural Russian phrasing;
- 2 `pos` terminology corrections;
- 1 `xref_gloss` mahjong terminology correction.

No `needs_adjudication` decision remains. Potentially serious candidate errors
identified during review were replaced and therefore did not survive the
independent editorial pass. This does not cure the frozen per-role failure.

## Audit limitations under the no-API constraint

Exactly three isolated Luna translation-agent tasks produced the pilot, while
the main thread retained orchestration and ingestion. Three separately spawned
Terra Medium reviewer agents performed the blind review. Neither translators
nor reviewers were allowed to inspect run-2 targets, the database, built
artifacts, or unrelated repository files.

The Codex-agent transport does not expose billable input/output token usage or
an API response model identifier. Consequently:

- OpenAI API token-count and cost gates were not run;
- external API cost was zero, but Codex-agent compute usage is unavailable;
- attempts record the configured model and effort, while
  `effective_model_id` cannot be independently verified from an API response.

These limitations are recorded rather than filled with estimates. They provide
an additional reason not to claim that the full original API experiment passed.

## Audit artifact note

One rejected review attempt remains recorded with `invalid_json` after a
reviewer response accidentally began with a literal `+`. The same batch was
requeued, validated, and fully reviewed on the next attempt. The issue is kept
as immutable rejected-attempt history and is not a defect in an accepted unit.

## Stop condition

Section 8.7 and section 11 of `LUNA_TRANSLATION_PLAN.md` require a profile to
fail when any role exceeds its baseline plus two percentage points. Because the
conservative profile fails that rule, the coordinator stops here and does not
translate the balanced or current-size profiles, start the 27,518-unit
production run, or overwrite any Terra artifact.
