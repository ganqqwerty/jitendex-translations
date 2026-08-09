# Plan: blind Luna Medium reproduction of the Terra lexicographer-v2 run

Date researched: 2026-08-09

## 1. Objective and decision

Translate the exact `lexicographer-v2` dataset again with `gpt-5.6-luna` at
`medium` reasoning effort, determine whether its Russian lexicographic quality
is non-inferior to the completed Terra run, and retain every existing source,
structural, validation, review, audit, build, and Yomitan smoke-test guarantee.

The coordinator should use these defaults:

- Luna is the translator only: `model = gpt-5.6-luna`,
  `reasoning.effort = medium`.
- Keep a fresh, stateless model request for every translation manifest. Send
  **one manifest/chunk per request**. A Batch API input file may contain many
  independent request lines, but each line still contains only one manifest.
- Begin the capacity experiment with a **soft cap of 6 articles, 24 KiB, and
  100 units**. Keep the existing **hard singleton ceiling of 48 KiB and 200
  units**. Do not lower the current hard ceiling to the soft cap.
- Use a fresh Terra Medium reviewer for 100% of the Luna output during this
  experiment. The reviewer sees source evidence and the Luna candidate, but no
  completed Terra translation.
- Create a new run. Never mutate, delete, reuse, or mark as Luna any row from
  run 2, the completed Terra `lexicographer-v2` run.
- Do not start all 27,518 units until the blind pilot passes the gates in
  section 8. If the conservative profile fails, stop and report that Luna did
  not reproduce Terra quality; do not conceal the gap with silent Terra
  translation fallback.

This is deliberately a quality experiment, not a literal-output comparison.
Two good Russian dictionary definitions need not have identical wording.

## 2. Verified model research

The premise that Luna has a smaller context window is not supported by the
current official specifications. Luna and Terra both have a 1,050,000-token
context window and a 128,000-token maximum output. Both support reasoning,
structured outputs, the Responses API, and the Batch API. Luna is the cheaper,
lower-capability tier: OpenAI describes Luna as the cost-sensitive,
high-volume model corresponding roughly to an earlier nano tier, while Terra
roughly corresponds to an earlier mini tier.

| Property | GPT-5.6 Luna | GPT-5.6 Terra |
|---|---:|---:|
| Context window | 1,050,000 tokens | 1,050,000 tokens |
| Maximum output | 128,000 tokens | 128,000 tokens |
| Medium reasoning | Supported | Supported |
| Standard input price, current official page | $0.20 / 1M tokens | $2.00 / 1M tokens |
| Standard cached-input price | $0.02 / 1M tokens | $0.20 / 1M tokens |
| Standard output price | $1.20 / 1M tokens | $12.00 / 1M tokens |

Sources: [GPT-5.6 Luna model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
[GPT-5.6 Terra model page](https://developers.openai.com/api/docs/models/gpt-5.6-terra),
and [GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6).
Prices are time-sensitive; the coordinator must re-open those pages and record
the date and prices before production.

For identical token usage at the prices above, Luna costs 90% less than Terra
for both uncached input and output. OpenAI's Batch API gives a further 50%
discount and a 24-hour completion window, making it suitable for this offline
corpus once the synchronous pilot works. See the
[Batch API guide](https://developers.openai.com/api/docs/guides/batch).

Do not estimate context or spend with `characters / 4`. OpenAI explicitly says
that local character estimates are inaccurate for exact request sizing. Use the
input-token-count endpoint with the complete request—including the developer
prompt, manifest, response schema, and message framing—before dispatch. See
[Counting tokens](https://developers.openai.com/api/docs/guides/token-counting).

### Consequence for chunking

The batch should be reduced, if at all, to reduce the lower-tier model's
attention burden and contract-error rate—not because Luna has a smaller
technical context window. Multiple existing manifests could fit technically,
but combining them creates a larger ordered JSON contract, weakens failure
isolation, repeats work on retry, and makes quality attribution harder. The
production rule is therefore one manifest per independent Luna request.

## 3. Exact local baseline

These figures were measured from `work/progress.sqlite3` and the actual run-2
manifests, not inferred from the older design document.

### Dataset that must be reproduced

- Source selection: 1,704 Jitendex articles selected by the completed Kaishi
  resolution.
- Pipeline: `lexicographer-v2`, schema version 2.
- Translation units: 27,518.
- Run-2 source manifests: 242 translation batches.
- Total serialized translation-manifest bytes: 9,733,826.
- Terra v2 prompt size: 4,047 bytes.
- Total run-2 prompt plus manifest bytes, counting the prompt once per batch:
  10,713,200. This is a byte measurement, not a token count.
- Accepted Terra response files: 242 files and 7,254,037 total bytes; median
  32,184 bytes, p95 41,268 bytes, maximum 44,697 bytes. These are workload
  observations, not output-token limits.

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
| **Total** | **27,518** |

### Article-size measurements

When each article is serialized alone with the real schema and terminology:

| Measure | Minimum | Median | p95 | Maximum |
|---|---:|---:|---:|---:|
| Bytes | 1,793 | 5,126 | 13,604 | 34,780 |
| Units | 3 | 13 | 38 | 96 |

Fifteen articles exceed 24 KiB; two exceed 32 KiB. No article exceeds 100
units. A 24-KiB value can therefore only be a soft grouping cap. The current
`make_batches` implementation treats `max_bytes` and `max_units` as hard
limits, so naively changing `max_bytes` to 24 KiB would fail before translation.

### Repacking simulation

The following profiles were simulated over all 1,704 real article envelopes in
source order. An article above a profile's soft cap becomes a singleton but may
use the existing 48-KiB/200-unit hard ceiling.

| Profile | Soft articles / bytes / units | Resulting batches | Median articles | Median bytes | Median units | Prompt + manifest bytes with current prompt |
|---|---|---:|---:|---:|---:|---:|
| Terra/current | 12 / 48 KiB / 200 | 242 | 8 | 45,397 | 125 | 10,713,200 |
| Expanded Luna candidate | 9 / 36 KiB / 150 | 319 | 6 | 33,142 | 91 | 11,062,703 |
| Balanced Luna candidate | 8 / 32 KiB / 140 | 353 | 5 | 29,192 | 81 | 11,217,029 |
| Conservative Luna candidate | 6 / 24 KiB / 100 | 483 | 4 | 21,055 | 58 | 11,807,099 |
| Diagnostic fallback | 4 / 16 KiB / 75 | 751 | 2 | 13,604 | 37 | 13,023,551 |

The conservative profile nearly doubles the number of requests but increases
prompt-plus-manifest bytes by only about 10.2% relative to the current layout.
The token-count endpoint must still provide the actual input-token totals.

### Terra quality baseline for non-inferiority

Run 2 completed all 242 translation batches after 242 accepted and 11 rejected
translation attempts: a 95.65% batch-attempt acceptance rate. Deterministic
issues were resolved and no blocking issue remains.

The independent Terra review accepted 26,327 units and replaced 1,191, for an
overall replacement rate of **4.33%**. The role-specific baselines are:

| Role | Reviewed | Replaced | Replacement rate |
|---|---:|---:|---:|
| `glossary_set` | 5,580 | 466 | 8.35% |
| `label` | 1,056 | 69 | 6.53% |
| `example` | 3,176 | 158 | 4.97% |
| `pos` | 4,172 | 176 | 4.22% |
| `register` | 1,108 | 40 | 3.61% |
| `tooltip` | 8,992 | 256 | 2.85% |
| `note` | 1,784 | 17 | 0.95% |
| `xref_gloss` | 1,650 | 9 | 0.55% |

The final run contains 27,518 accepted units, all independently reviewed, zero
unresolved validation issues, and a verified Yomitan build. That complete gate,
not exact string equality with Terra, is Luna's target.

## 4. Invariants: what must not change

The coordinator must preserve all of the following:

1. The pinned Jitendex `2026.07.09.0` and Kaishi `v2.4.1` source snapshots and
   their checksums.
2. The accepted selection decisions and the exact 1,704 selected articles.
3. `extractor-v2`, `lexicographer-v2`, schema version 2, the same terminology
   map, structural fingerprints, protected tokens, and translation-unit roles.
4. The semantic method R1-R3: understand the whole article, identify what the
   assembler preserves, then author Russian from the Japanese term, Japanese
   examples, restrictions, and linguistic metadata. English is secondary
   evidence; `glossary_set` is not translated synonym by synonym.
5. The variable-length `glossary_set` contract: 1-12 distinct plain Russian
   definitions. Every other role returns one plain Russian string.
6. Exact ordered unit coverage and exact copies of every batch ID, manifest
   hash, unit ID, source hash, and protected token.
7. Workers return translations only. They never rewrite the Yomitan article
   tree, markup, ruby, links, tables, media, attribution, IDs, or source data.
8. Strict deterministic response validation before review, independent review
   before acceptance, deterministic assembly from the canonical source, archive
   schema validation, reproducible build verification, and the existing Yomitan
   lookup/layout smoke suite.
9. Runs 1 and 2 and all Terra request/response/review artifacts remain intact
   as immutable history.

## 5. Required implementation work before any Luna call

Use CodeGraph first for the structural changes below, then use literal search
only for hard-coded model names and prompt-version strings.

### 5.1 Parameterize model identity and reasoning effort

The current code would falsely record Luna work as Terra:

- `src/jitendex_ru/batch.py` hard-codes `gpt-5.6-terra` in `claim`.
- `src/jitendex_ru/review.py` hard-codes `gpt-5.6-terra` for adjudication
  attempts.

Add configuration such as:

```toml
[models.translation]
id = "gpt-5.6-luna"
reasoning_effort = "medium"

[models.review]
id = "gpt-5.6-terra"
reasoning_effort = "medium"
```

Pass the effective model and effort through claim/dispatch and persist them on
every attempt. Do not infer a model from a worker ID. Keep the historical
selection rule involving `terra-adjudicator-*` unchanged unless selection is
separately redesigned; it represents accepted historical actors and is not
part of this translation experiment.

Add attempt usage/audit fields (individual columns or one validated
`usage_json`) for:

- model ID and reasoning effort;
- transport (`responses-sync`, `batch-api`, or `codex-agent`);
- API request ID or Batch `custom_id`/job ID;
- input, cached-input, output, and total tokens;
- finish/status reason and latency;
- price snapshot/date and computed cost, preferably in a separate immutable
  cost report so changing prices never rewrites raw usage.

### 5.2 Scope claims to a run and kind

The current `claim` command selects the oldest ready batch globally. Add and
require `--run-id` and `--kind translation|review`, or require a specific batch
ID supplied from a run-scoped query. This prevents pilot profiles or an old
retry from being dispatched under the wrong model.

### 5.3 Separate soft grouping caps from hard article ceilings

Introduce explicit configuration:

```toml
[batch]
soft_max_articles = 6
soft_max_bytes = 24576
soft_max_units = 100
singleton_threshold_bytes = 16384
hard_max_article_bytes = 49152
hard_max_article_units = 200
```

Packing behavior:

1. Reject an article only when its single-article envelope exceeds the hard
   article ceiling.
2. If it exceeds any soft cap, emit it as one singleton.
3. Otherwise group articles until the first soft cap would be exceeded.
4. Keep deterministic source order, identity hashing, and retry splitting.

Add tests for the 34,780-byte article class so a lower Luna grouping cap cannot
reject valid source data.

### 5.4 Create new versioned prompts and a new run

Add:

- `prompts/translate_luna_v1.txt` containing section 6 verbatim;
- `prompts/review_terra_luna_blind_v1.txt` containing section 7 verbatim;
- a Luna config derived from the current config but with version names
  `translate-luna-v1` and `review-terra-luna-blind-v1` and the chosen batch
  profile.

The changed prompt hashes and limits must create a new run through the existing
run-identity mechanism. Never pass `--run-id 2` to extraction or batching.
Record the returned run ID and use it explicitly thereafter; do not assume it
will be 3.

### 5.5 Prefer a tool-free API request for genuine blindness

The strongest independence guarantee is a Responses API request that contains
only the Luna developer prompt and one source manifest, has no tools or file
access, does not send `previous_response_id`, and sets reasoning context to the
current turn. This prevents Luna from browsing the shared workspace, database,
`work/outbox`, `dist`, or the accepted Terra translations.

The current coordinator environment's child-agent model allow-list may not
expose Luna even though the API model supports it. Perform one preflight call
and verify the returned model ID. If a fresh Codex child agent is used instead,
it must be created without forked conversation history, receive only the
assigned manifest and response path, and be explicitly denied repository
exploration. Because child agents share a filesystem, that is a weaker
isolation guarantee than a tool-free API call.

For API transport:

- pilot synchronously with `/v1/responses`;
- use strict structured output for the schema in section 6;
- set `reasoning.effort = medium` explicitly;
- send no tools and no prior response state;
- after the synchronous pilot passes, optionally submit production through
  `/v1/batch`, one independent Responses request per JSONL line;
- map Batch results by unique `custom_id = attempt_id`, never by response
  order;
- represent a submitted Batch job in durable state. Do not let the current
  30-minute lease expire and redispatch while OpenAI may still be processing a
  job. A Batch submission may take up to 24 hours.

### 5.6 Test the migration

At minimum add tests proving:

- a Luna translation claim records `gpt-5.6-luna` and medium effort;
- a review claim records `gpt-5.6-terra` and medium effort;
- a claim cannot cross run or batch kind;
- soft-cap oversized articles become valid singletons;
- hard-cap oversized articles fail before dispatch;
- schema-2 `glossary_set` arrays and scalar strings still validate exactly as
  before;
- a wrapped API response is extracted to the exact worker JSON payload and
  then passes through the existing ingestion validator;
- Batch results are matched by attempt ID and cannot be ingested twice;
- raw usage and effective model ID are audited;
- runs 1 and 2 remain byte-for-byte and row-count unchanged by run creation.

## 6. Luna translator prompt (`translate-luna-v1`)

Store the following text verbatim and hash it into the run and every attempt.
The manifest is a separate input after this prompt.

```text
You are a professional author of a Russian learner's dictionary of Japanese.

Use only the supplied batch. You have no prior translation of these articles. Do not search for, request, or infer any previous translation, and do not inspect repository files or databases.

GOAL
Return a complete schema-version-2 Russian translation payload for every input unit. The Japanese headword, reading, Japanese examples, restrictions, and linguistic metadata are primary evidence. English definitions and example translations are secondary evidence for understanding; do not translate English synonyms mechanically.

ARTICLE METHOD
For each article:
1. Understand the complete article, its Japanese senses, usage, examples, restrictions, register, domain, transitivity, and other grammatical information.
2. Respect the preservation_inventory. The deterministic assembler, not you, preserves sense structure, Japanese text, examples, forms tables, ruby, links, media, cross-references, and attribution.
3. Author concise, idiomatic Russian dictionary wording supported by the Japanese evidence.

TRANSLATION RULES
- Keep separate Japanese senses separate. Within one glossary_set, do not preserve the number or order of English synonyms.
- glossary_set target_text is an array of 1-12 distinct plain Russian definitions. Merge redundant English wording. Add an equivalent only when the Japanese term, example, or metadata supports it. Never invent a sense.
- Every non-glossary_set target_text is one non-empty plain Russian string.
- Use natural Russian lexicographic style. For verbs, choose correct aspect or an aspectual pair and correct government. Explain particles, counters, honorifics, constructions, and culture-specific concepts when a one-word equivalent would mislead.
- Translate examples idiomatically from Japanese while preserving meaning, tense, aspect, polarity, modality, participants, and politeness. English is only a comprehension aid.
- Preserve register, domain, restriction, transitivity, grammar, numbers, placeholders, and every protected token exactly.
- Every target must contain appropriate Russian Cyrillic wording except for protected Japanese, identifiers, URLs, proper names, or other tokens that must remain exact.
- Do not emit English-shaped paraphrases, repeated near-synonyms, romaji, unsupported explanations, markup, Markdown, tags, code fences, JSON fragments inside strings, or reasoning.
- If Japanese and English evidence conflict, follow Japanese, set confidence to low, and state the conflict briefly in review_reason.

OUTPUT CONTRACT
- Return exactly one translation for every input unit, in input order. No omissions, duplicates, additions, or reordering.
- Copy batch_id, manifest_sha256, unit_id, and source_sha256 byte-for-byte.
- confidence is high, medium, or low. Use review_reason = null for high. For medium or low, give one concise, non-empty quality warning.
- Return strict JSON only, with no prose before or after it.

OUTPUT SHAPE
{
  "schema_version": 2,
  "batch_id": "copy exactly",
  "manifest_sha256": "copy exactly",
  "translations": [
    {
      "unit_id": "copy exactly",
      "source_sha256": "copy exactly",
      "target_text": "plain Russian string for scalar roles OR an array of 1-12 distinct plain Russian strings for glossary_set",
      "confidence": "high | medium | low",
      "review_reason": null
    }
  ]
}

Before returning, silently check: all units are present once and in order; R1-R3 were applied; glossary sets are authored rather than synonym-mapped; every protected token is exact; every target has the correct string/array type and Russian wording; identifiers and hashes are copied exactly; the result is valid JSON.
```

Why this differs from the Terra prompt:

- It preserves every semantic and structural rule but states each once, in a
  fixed priority order.
- It makes blindness explicit.
- It makes Cyrillic output, type correctness, ordered coverage, and confidence
  behavior explicit because those caused deterministic retries in run 2.
- It adds no Terra output or few-shot translation, so Luna cannot imitate or
  leak the prior translation.
- It follows OpenAI's GPT-5.6 guidance to begin with the working prompt, remove
  repetition, preserve requirements that encode product quality, and evaluate
  on representative tasks rather than assuming a prompt change helps.

## 7. Blind Terra review prompt

Use this for the experiment's independent review pass. The reviewer may know
that the candidate came from Luna but must not see run-2 target text or use it
as a reference.

```text
You are an independent senior editor of a Russian learner's dictionary of Japanese.

Review only the supplied source evidence and candidate. Do not search for or inspect any previous Terra translation, accepted run, output database, outbox, or built dictionary. Judge the candidate as Russian lexicography, not by string similarity to another translation.

Apply R1-R3 independently: understand the article; identify the Japanese examples, sense boundaries, forms, linguistic metadata, restrictions, cross-references, and preserved structures; then judge the Russian wording primarily against the Japanese headword, reading, Japanese evidence, and metadata. English definitions are secondary evidence only.

For glossary_set, reject mechanical one-for-one English synonym translation, repeated Russian equivalents, English-shaped wording, unsupported senses, missing Japanese sense coverage, bad aspect or government, and an unjustified number of definitions. A correct candidate may have fewer or more definitions than english_gloss_evidence. For examples, verify the Russian sentence from Japanese rather than merely comparing it with English.

Return exactly one ordered review per unit. decision is accept, replace, or needs_adjudication. For replace, replacement_target is a complete plain Russian string for a scalar unit or a complete array of 1-12 distinct Russian strings for glossary_set. Otherwise replacement_target is null. Give a concise reason for replace or needs_adjudication. Copy all IDs and hashes exactly, preserve protected tokens, emit no markup, and return strict schema-version-2 JSON only.
```

## 8. Blind pilot and capacity experiment

### 8.1 Freeze the comparison protocol first

Before generating any Luna output, save and hash:

- the Luna prompt;
- the blind reviewer prompt;
- all three candidate batch profiles;
- the deterministic pilot article IDs and stratification method;
- the scoring rubric and pass/fail thresholds below;
- the model IDs, reasoning effort, and price snapshot.

Do not tune thresholds after seeing Luna results.

### 8.2 Prove dataset identity

Create the Luna run, extract units, but do not translate. Require:

- exactly 1,704 distinct articles;
- exactly 27,518 units;
- the exact role counts in section 3;
- zero difference from run 2 in the multiset
  `(article_id, json_pointer, role, source_sha256)` in either direction.

Unit IDs are run-scoped and therefore should differ. Source identity must not.
Use the SQL in section 12.

### 8.3 Exact token audit

For every candidate request, call the official input-token-count endpoint with
the complete request body. Record minimum, median, p95, p99, maximum, and total
input tokens for each profile. After pilot responses exist, record output
tokens from actual API usage. Set any production output limit from the measured
pilot distribution with documented headroom; do not derive it from bytes and do
not leave it unlimited.

No request may approach the model's context or output limit. A practical gate
is at least 4x headroom between the largest measured request and each official
limit. Given the measured byte sizes this should be easy, but the token endpoint
is the authority.

### 8.4 Pilot sample

Select a deterministic stratified pilot of at least 1,500 units. Include at
least 100 units of every role and oversample the high-replacement roles
`glossary_set`, `label`, `example`, and `pos`. The selected articles must also
include:

- all 15 articles above 24 KiB, including the 34,780-byte maximum;
- the 96-unit maximum article;
- small, median, p95, and maximum article sizes;
- single- and multi-sense entries;
- Japanese examples and English aids;
- protected tokens, Japanese substrings, numbers, and identifiers;
- restrictions, register/domain labels, transitivity, forms tables, notes,
  xrefs/antonyms, kana-only lookup cases, and culture-specific explanations.

Use the same pilot articles for every profile. Generate fresh Luna output for
each profile; never continue a conversation or reuse reasoning from another
profile.

### 8.5 Profiles to compare

Run in this order:

1. Conservative: 6 articles / 24 KiB / 100 units soft caps.
2. Balanced: 8 articles / 32 KiB / 140 units soft caps.
3. Current-size control: 12 articles / 48 KiB / 200 units.

The 9/36/150 profile is optional if balanced and current-size results straddle
the quality gate. The 4/16/75 profile is diagnostic only if the conservative
profile fails; it is not an automatic production escape hatch.

### 8.6 Blind evaluation

For every profile:

1. Run existing deterministic ingestion unchanged.
2. Have fresh Terra Medium reviewers review 100% of pilot units with the prompt
   in section 7. Reviewers see no prior Terra target.
3. Classify every replacement reason as contract/format, semantic accuracy,
   missing or invented sense, Russian lexicographic quality, example accuracy,
   terminology, protected-token/structure, or other.
4. After Luna outputs and decisions are frozen, run a secondary randomized,
   anonymized comparison on at least 200 high-risk units between the final
   accepted run-2 wording and the Luna candidate. The evaluator sees source
   evidence and candidates A/B in randomized order. Exact wording difference is
   not a defect; score semantic correctness, natural Russian, sense coverage,
   learner usefulness, and structural compliance.
5. Keep model, reviewer, profile, token, latency, and cost data separate so the
   coordinator can explain a quality/cost tradeoff rather than only a pass/fail.

### 8.7 Gates

A profile passes only if all of the following hold:

- 100% unit coverage after allowed fresh-request retries; no silent omissions,
  duplicates, wrong IDs, changed hashes, missing protected tokens, invalid
  strings/arrays, or unparseable JSON.
- First-attempt deterministic batch acceptance is at least 95%, close to the
  Terra baseline of 95.65%.
- Zero critical semantic or structural defect in the fully reviewed pilot. A
  critical defect is an invented/missing Japanese sense, wrong polarity or
  participant relation, corrupted protected token, structural rewrite, or
  misleading example that survives review.
- The one-sided 95% confidence interval for
  `Luna overall replacement rate - 4.33%` has an upper bound no greater than
  +1.0 percentage point.
- Each role's observed replacement rate is no more than its Terra baseline in
  section 3 plus 2.0 percentage points. A role that misses this gate fails even
  if high-volume tooltips hide it in the overall average.
- In the anonymized high-risk comparison, Luna has no unresolved critical
  defect and is judged acceptable/equivalent-or-better on at least 95% of
  samples.
- Exact token totals and projected standard and Batch API costs are recorded.

Choose the largest passing profile because it minimizes repeated prompt
overhead and orchestration. If the current-size control passes, it is acceptable
to keep 12/48/200; the research shows context size itself does not require a
reduction. If only the conservative profile passes, production uses 6/24/100
with oversize singletons. If the conservative profile fails, stop and report
that Luna Medium has not demonstrated Terra-equivalent quality.

## 9. Production workflow after the pilot passes

### Phase A: freeze and create the production run

1. Commit the code, tests, Luna prompt, reviewer prompt, configs, pilot report,
   and chosen profile. A suitable commit message is:

   ```text
   feat: isolate Luna translation runs to test Terra-quality output at lower cost

   Parameterize model auditing and add soft batch caps so Luna Medium can process the identical lexicographer-v2 corpus without seeing Terra outputs. This preserves source selection, independent review, and release gates while making token usage and cost attributable to the actual model.
   ```

2. Re-run the full test suite.
3. Create a fresh production run with the final prompt and limits. Do not reuse
   a pilot run whose prompt or limits changed.
4. Run the dataset-identity SQL gate again.
5. Generate all translation manifests and record their hashes.
6. Count exact input tokens and produce a preflight cost forecast before any
   production submission.

Until the editable virtual environment is repaired, invoke the CLI from this
checkout as:

```sh
PYTHONPATH=src .venv/bin/python -m jitendex_ru.cli --config config.luna.toml COMMAND
```

The currently installed `.venv/bin/translationctl` entry point does not import
this checkout correctly, so the coordinator must either reinstall the editable
package deliberately or use the command above.

### Phase B: translate

1. Claim only translation batches from the explicit Luna production run.
2. Dispatch at most one manifest in each fresh Luna request.
3. Verify the API response reports `gpt-5.6-luna`; reject and do not ingest a
   response from another model.
4. Extract only the strict worker payload, write it to the attempt's response
   path, and call the existing `ingest-response` command.
5. On deterministic failure, mark the attempt rejected and retry with a fresh
   Luna request. Never give the new request the failed target text.
6. Preserve the existing third-failure deterministic split behavior. A
   single-unit exhaustion remains blocked for adjudication.
7. Monitor a rolling window of at least 1,000 reviewed units. Pause production
   if overall or per-role replacement rates breach the chosen profile's gate,
   if a critical defect appears, or if token/cost usage exceeds the forecast by
   more than 15% without explanation.

For synchronous pilot calls, respect the account's current rate limits and use
bounded concurrency with retry-after/backoff. Do not assume a rate-limit tier.
For Batch API production, use durable submitted-job state, unique attempt IDs,
idempotent result ingestion, and the documented 24-hour completion window.

### Phase C: independent review

1. Generate review batches with the existing source-plus-candidate envelope and
   existing review caps.
2. Dispatch every review to a fresh `gpt-5.6-terra` Medium reviewer using the
   blind prompt in section 7.
3. Reviewers receive Luna candidates but never run-2 Terra targets.
4. Ingest `accept` and `replace` decisions through the existing validator.
5. Send `needs_adjudication` to a fresh senior reviewer or human. Record the
   effective model and actor; do not auto-accept.

Keeping Terra as the independent reviewer is intentional: this experiment asks
whether Luna can replace Terra as translator without weakening the already
successful editorial gate. Replacing the reviewer with Luna would be a separate
cost experiment with correlated-error risk.

### Phase D: release gates

Require all of the following before calling the Luna result successful:

- `units = accepted_units = independently_reviewed_units = 27,518`;
- zero unresolved blocking validation issues;
- zero batch-membership mismatch;
- exactly 1,704 built articles;
- canonical structural fingerprints unchanged except approved translated
  leaves and deterministic `lang: en` to `lang: ru` changes;
- pinned Yomitan schema validation passes for every bank;
- two clean rebuilds have identical ZIP SHA-256;
- selection lookup has zero misses;
- the clean-profile Yomitan smoke suite passes expression, reading, inflection,
  kana-only, multiple-reading, xref, ruby, example, table, link, and long-entry
  checks;
- licensing and attribution checks remain present;
- a final quality report contains model/effort, prompt hashes, batch profile,
  request/attempt counts, deterministic failures, review rates by role,
  critical-defect count, exact token usage, price snapshot, and total cost.

Build to a new filename such as
`dist/jitendex-kaishi-ru-lexicographer-v2-luna.zip`. Never overwrite the verified
Terra archive.

## 10. Cost accounting

Before production, compute all four forecasts from measured tokens:

```text
standard_luna_translation = 0.20 * input_M + 1.20 * output_M
batch_luna_translation    = 0.50 * standard_luna_translation
standard_terra_review     = 2.00 * review_input_M + 12.00 * review_output_M
batch_terra_review        = 0.50 * standard_terra_review
```

Those coefficients reflect the official pages on 2026-08-09 and must be
replaced if the pages change. Add retry and rejected-attempt usage; do not price
only accepted responses. Keep translation and review costs separate so the
user can see the savings attributable to Luna. Report cached tokens from actual
usage rather than assuming the repeated prompt was cached.

The expected direction is clear—Luna's per-token translation price is one tenth
of Terra's at the researched rates—but the final dollar amount must come from
exact token usage. Smaller batches increase repeated prompt input; the measured
6/24/100 byte overhead is about 10.2%, which is far below the 10x price
difference, but bytes are not billable tokens.

## 11. Stop conditions and risks

| Risk | Mandatory response |
|---|---|
| Luna child-agent model is unavailable | Use verified tool-free Responses/Batch API access; never relabel Terra output as Luna. |
| Effective model differs from `gpt-5.6-luna` | Reject the response and stop dispatch until routing is fixed. |
| Luna can browse run-2 outputs | Stop; switch to tool-free requests containing only prompt + manifest. |
| New run differs from the run-2 source-unit multiset | Stop before translation and fix run creation/extraction. |
| 24-KiB cap rejects a large article | Fix soft-vs-hard batching; do not drop or truncate the article. |
| Conservative pilot misses a quality gate | Stop full production and report Luna as not yet non-inferior. |
| Overall score passes but a role regresses | Fail the profile; high-volume easy roles may not mask glossary/example errors. |
| Malformed or truncated output | Reject deterministically, retry fresh, then split under existing policy. |
| Reviewer sees the prior Terra target | Discard that evaluation and rerun blind. |
| Batch job exceeds its durable deadline | Reconcile job status before retry; never submit duplicate live attempts. |
| Cost forecast is exceeded by more than 15% | Pause, reconcile retries/reasoning/caching/usage, and get approval before continuing. |
| Release gate or Yomitan smoke test fails | Do not publish or overwrite the Terra artifact. |

## 12. Coordinator checklist and SQL

Use this compact checklist as the execution state machine:

- [ ] Model and pricing pages rechecked; model access preflight returns
  `gpt-5.6-luna`.
- [ ] CodeGraph-guided implementation and tests complete.
- [ ] Model/effort/transport/usage auditing is no longer hard-coded.
- [ ] Run- and kind-scoped claim is enforced.
- [ ] Soft grouping caps and hard singleton ceilings are separate.
- [ ] Prompts and evaluation protocol are hashed and frozen.
- [ ] New Luna run created; returned run ID recorded as `:luna_run`.
- [ ] Source identity, counts, and role inventory equal run 2.
- [ ] Exact token counts and pilot cost approved.
- [ ] All pilot profiles evaluated blind; largest passing profile selected.
- [ ] Fresh production run created if the pilot changed any prompt or limit.
- [ ] One manifest per fresh Luna request; no previous translation exposed.
- [ ] 100% blind Terra review complete.
- [ ] Full deterministic release gates and clean Yomitan smoke pass.
- [ ] Luna artifact and quality/cost report written under new filenames.
- [ ] Runs 1 and 2 and the Terra archive remain unchanged.

Dataset equality queries, replacing `:luna_run` with the returned run ID:

```sql
SELECT COUNT(DISTINCT article_id) AS articles,
       COUNT(*) AS units
FROM translation_unit
WHERE run_id = :luna_run;

SELECT role, COUNT(*) AS units
FROM translation_unit
WHERE run_id = :luna_run
GROUP BY role
ORDER BY role;

SELECT COUNT(*) AS missing_from_luna
FROM (
  SELECT article_id, json_pointer, role, source_sha256
  FROM translation_unit WHERE run_id = 2
  EXCEPT
  SELECT article_id, json_pointer, role, source_sha256
  FROM translation_unit WHERE run_id = :luna_run
);

SELECT COUNT(*) AS extra_in_luna
FROM (
  SELECT article_id, json_pointer, role, source_sha256
  FROM translation_unit WHERE run_id = :luna_run
  EXCEPT
  SELECT article_id, json_pointer, role, source_sha256
  FROM translation_unit WHERE run_id = 2
);
```

Expected results are `articles = 1704`, `units = 27518`, the role counts in
section 3, and both difference counts equal to zero.
