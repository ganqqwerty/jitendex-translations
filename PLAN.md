# Plan: Kaishi-scoped Jitendex translation to Russian

Status: scalar-v1 was completed and retained as run 1. The active
`lexicographer-v2` revision replaces leaf-by-leaf English translation with
sense-level Russian article authorship.

## 0. Lexicographer-v2 correction

The original one-input-leaf/one-output-leaf contract was too literal: it forced
English synonym counts and wording into Russian. In v2 the worker follows R1–R3:
understand the English article, identify the structural and linguistic elements
that must survive, and author Russian definitions primarily from the Japanese
headword, Japanese examples, and metadata. English glosses are evidence only.

Every source `glossary` is one `glossary_set` unit. Its Russian result is a
variable-length list, so redundant English synonyms may be merged and a useful
Russian equivalent may be introduced when Japanese usage supports it. Other
approved leaves remain scalar units. The deterministic assembler preserves the
canonical article and rewrites only glossary content or approved scalar text.
Run-scoped IDs and fingerprints isolate v2 from the preserved scalar-v1 run.

## 1. Goal and decisions

Build a Russian Yomitan term dictionary derived from the pinned Jitendex release, containing only lexical entries selected by the Kaishi 1.5k deck. Translation work will be performed by fresh Terra Medium agents, while deterministic code owns selection, batching, persistence, markup application, validation, and ZIP construction.

The important design decisions are:

1. SQLite is the source of truth for every source snapshot, selection decision, batch, attempt, translation, validation result, and export.
2. A Kaishi item is identified by word, reading, English meaning, and example—not by surface spelling alone. This is necessary to disambiguate homographs and kana-only words.
3. Terra never edits a Yomitan JSON tree or HTML-like markup. It receives a read-only article context and returns translations for whitelisted scalar text units only. The assembler retains all canonical surrounding markup; nothing is flattened or stripped.
4. A fresh Terra Medium agent handles exactly one batch. Agents are not reused, so conversation history cannot accumulate across batches.
5. Translation batching has three hard limits: **12 articles, 48 KiB of serialized input context, and 200 translation units**, whichever is reached first. An article above 16 KiB is always a singleton.
6. Every translated batch receives a separate review pass. Deterministic validation must pass before model review, and both must pass before acceptance.
7. The output is rebuilt from the canonical source snapshot; worker output is never used as a replacement JSON document.

## 2. Inspected inputs and domain findings

### 2.1 Pinned artifacts

| Artifact | Version | Observed size | SHA-256 |
|---|---:|---:|---|
| Jitendex Yomitan ZIP | `2026.07.09.0` | 38,545,572 bytes compressed | `807d911114af9d2154d270702972aafb2b6a6c2dc2400afa98db870d035c1a0b` |
| Kaishi APKG | `v2.4.1` | 108,690,088 bytes | `0bfed7adfb740e49fbe323d05a6899d25942213aa2238749630653e3d11d357e` |

The Kaishi checksum matches the digest published in its official GitHub release metadata. The AnkiWeb download endpoint was unavailable during analysis, so the official GitHub release asset was used.

### 2.2 Jitendex/Yomitan structure

The Jitendex archive is a Yomitan format-3 term dictionary with:

- `index.json` at the ZIP root;
- 217 `term_bank_N.json` files;
- one `tag_bank_1.json`;
- `styles.css`;
- 201 AVIF and 48 SVG assets;
- 433,885 term rows representing 285,976 unique sequence IDs.

Each normal term row has eight positions:

```text
[
  0 expression,
  1 reading,
  2 definitionTags,
  3 deinflectionRules,
  4 score,
  5 glossaryOrStructuredContent,
  6 sequence,
  7 termTags
]
```

Position 5 normally contains a `structured-content` tree. It is JSON, not free-form HTML, but its nodes are rendered as HTML-like elements. Observed tags include `div`, `span`, `ul`, `ol`, `li`, `a`, `ruby`, `rt`, `table`, `tr`, `th`, `td`, and `img`. Important semantic selectors live in `data.content`; examples include:

- `sense-group`, `sense`, and `glossary`;
- `part-of-speech-info`, `misc-info`, `field-info`, and `dialect-info`;
- `sense-note`, `info-gloss`, and `lang-source`;
- `xref`, `antonym`, and their visible labels/glosses;
- `example-sentence-a` for Japanese and `example-sentence-b` for English;
- `forms` tables;
- `attribution` and `attribution-footnote`.

The source contains 50,758 paired examples overall. In the current exact Kaishi match, 2,578 Japanese/English example pairs are present. URLs, JMdict sequence IDs, Tatoeba sentence IDs, source names, ruby readings, query links, CSS selectors, table layout, and media paths are structural or provenance data and must not be translated.

Yomitan indexes both the expression and reading fields during normal lookup. Therefore a Kaishi kana word such as `あなた` can legitimately resolve to a Jitendex row such as `貴方 / あなた`; no synthetic alias should be created merely because the expression differs.

### 2.3 Kaishi structure and matching consequences

The official Kaishi APKG contains a Zstandard-compressed Anki SQLite collection. It has 1,501 notes: one welcome note and 1,500 vocabulary notes. The vocabulary note type has 14 fields:

```text
Word
Word Reading
Word Meaning
Word Furigana
Word Audio
Sentence
Sentence Meaning
Sentence Furigana
Sentence Audio
Notes
Pitch Accent
Pitch Accent Notes
Frequency
Picture
```

Only scope and disambiguation data are imported from Kaishi. The output dictionary must not bundle Kaishi media, templates, or deck content and must not claim affiliation with Kaishi.

The 1,500 vocabulary notes reduce to:

- 1,488 unique `(word, reading)` pairs;
- 1,476 unique word spellings;
- 12 exact duplicate pairs used for different Kaishi meanings/examples;
- 12 word spellings intentionally used with different readings.

An exact raw `(Jitendex expression, Jitendex reading)` match currently covers 1,428 of the 1,488 unique pairs and yields 1,444 Jitendex rows. Sixty pairs need a controlled fallback. Most are legitimate kana forms whose Jitendex rows use a kanji expression, for example `ください` → `下さい / ください`. Other cases need normalization or semantic disambiguation, for example:

- Kaishi uses readings such as `なに・なん`, which must be split into alternatives;
- Kaishi has `パン / ぱん`, while Jitendex readings are katakana;
- kana homophones such as `よく`, `そば`, and `つく` have unrelated Jitendex candidates;
- 14 exact pairs already map to multiple Jitendex articles, so exact spelling alone does not always identify the intended lexeme.

The final article count must therefore not be declared until the selection-resolution gate is complete.

### 2.4 Terra batch capacity measured on the real subset

Compact UTF-8 serialization sizes are:

| Corpus | Minimum | Median | p95 | Maximum |
|---|---:|---:|---:|---:|
| All 433,885 Jitendex rows | 247 B | 808 B | 2,670 B | 34,209 B |
| 1,444 exact Kaishi-matched rows | 589 B | 3,165 B | 9,363 B | 34,209 B |

The common Kaishi words have richer, longer entries than a typical Jitendex row. A fixed count such as 25 articles is unsafe even though it appears reasonable from the whole-dictionary median.

The preliminary text-unit extractor finds a median of 17 and a maximum of 127 translatable scalar units per exact-match article. Under the production limits of 12 articles, 48 KiB, 200 units, and singleton treatment above 16 KiB, the current exact subset would form approximately 173 batches:

- median: 9 articles, about 35.6 KiB, 186 units;
- p90: 12 articles, about 41.0 KiB, 198 units;
- maximum: 12 articles, 48,660 bytes, 200 units;
- about 15 singleton batches, including the longest articles.

These limits are deliberately based on observable input/output size, not an undocumented Terra context-window assumption. The first pilot uses half-size batches. Any truncation, missing item, malformed JSON, or output-limit signal causes deterministic splitting and retry.

## 3. Selection policy before translation

Selection is a separate audited phase. It must finish before production translation starts.

For each Kaishi note:

1. Normalize text to Unicode NFC.
2. Normalize readings for comparison only: katakana to hiragana, standard-width forms, and explicit splitting of Kaishi alternatives such as `なに・なん`. Preserve original source strings in storage and output.
3. Find candidates using Yomitan lookup semantics:
   - expression equals the Kaishi word with a compatible reading; or
   - reading equals the kana Kaishi word/reading after comparison normalization.
4. Group candidates by Jitendex sequence ID so alternate spellings of one JMdict lexeme do not look like independent meanings.
5. Compare the complete Jitendex English senses and examples with the Kaishi word meaning, Japanese sentence, and English sentence meaning.
6. Auto-accept only a single unambiguous sequence. Put all multi-sequence, no-candidate, reading-alternative, and weak-semantic cases into `selection_review`.
7. Have a Terra resolver propose a sequence with evidence, but require a separate reviewer or human to accept the decision. Store included and excluded candidates with reasons.
8. Include only rows needed to make the selected Kaishi word/reading searchable. Do not include an unrelated homophone merely because its reading is the same.

Selection acceptance criteria:

- all 1,500 notes have a recorded resolution;
- duplicate notes may point to the same article but remain visible in the audit;
- every selected article has at least one supporting Kaishi note;
- every excluded same-reading candidate has a reason;
- a small generated test dictionary proves lookup by both expression and reading before translation begins.

## 4. RE1 — Terra Medium translation prompt

The worker must receive the complete semantic context of each article, but not ownership of its JSON tree. The extractor supplies headword, reading, Kaishi evidence, sense grouping, Japanese examples, English examples, labels, cross-references, and the exact translation units. The output contains translations only.

The following prompt should be stored verbatim as a versioned file, hashed into every attempt, and used with a fresh Terra Medium agent at medium reasoning effort.

```text
You are a professional Japanese-to-Russian lexicographer translating Jitendex dictionary articles for a Russian Yomitan dictionary.

TASK
Translate every translation unit in the supplied batch into natural, concise, accurate Russian. Each article includes its Japanese headword and reading, complete read-only sense context, relevant Japanese and English examples, cross-references, and Kaishi evidence. Use all of that evidence together. The Japanese term and Japanese example are primary evidence for meaning and usage; the English gloss/example is the source text to translate and disambiguate.

DICTIONARY QUALITY RULES
1. Translate as a dictionary article, not as continuous prose.
2. Preserve every sense distinction, restriction, register, domain, transitivity, animacy, negation, modality, and ordering represented by the source. Do not merge, split, invent, broaden, omit, or reorder meanings.
3. Use conventional concise Russian lexicographic style:
   - verbs in the infinitive; choose Russian aspect or an aspectual pair when needed for accuracy;
   - natural noun/adjective/adverb equivalents, with short clarification in parentheses only when the source contains or requires that distinction;
   - compact, consistent grammar/register/domain labels from the supplied terminology map;
   - no romaji and no unnecessary repetition of a Japanese headword already shown by the dictionary.
4. Translate each Japanese example into idiomatic Russian while preserving the Japanese sentence's tense, aspect, polarity, modality, participant relations, level of politeness, and the sense demonstrated. Use the English example as evidence, not as a reason to ignore the Japanese.
5. For particles, counters, honorifics, fixed expressions, or culture-specific terms, give a concise Russian explanation rather than a misleading one-word equivalent.
6. Translate visible English glosses, POS/register/domain labels, sense notes, explanations, tooltips, cross-reference/antonym labels and glosses, and English example translations when they appear as translation units.
7. Do not translate source names, brands, licence names, URLs, identifiers, JMdict/Tatoeba, attribution tokens, or Japanese text. Such values should normally not be translation units; if one appears inside a unit, preserve every item listed in protected_tokens exactly.
8. Do not copy an English phrase into target_text unless it is a protected proper name or token. Preserve numbers and placeholders exactly unless normal Russian typography requires surrounding punctuation to change.
9. If Japanese and English evidence conflict, translate the meaning supported by Japanese, set confidence to "low", and state the conflict briefly in review_reason. Do not silently repair, delete, or add a sense.

STRUCTURE AND SAFETY RULES
1. The input context is read-only. Never reproduce or rewrite an article tree.
2. Return exactly one result for every input unit, in the same order, with no missing, duplicate, or additional unit IDs.
3. Copy batch_id, manifest_sha256, unit_id, and source_sha256 exactly. Never invent or alter an identifier or hash.
4. target_text is the translated replacement for one text leaf only. Do not reproduce, remove, or generate HTML, Markdown, tags, JSON fragments, ruby markup, links, comments, or a code fence inside target_text. All original surrounding Yomitan/HTML-like markup remains in the canonical article tree and will be preserved by the deterministic assembler. If source text and literal inline markup cannot be separated safely, mark the unit low-confidence instead of rewriting that markup.
5. Preserve each protected token byte-for-byte in target_text. Do not translate or normalize Japanese substrings listed as protected.
6. Do not include reasoning in target_text. Put only a short quality warning in review_reason when confidence is medium or low.
7. Return strict JSON only, using the exact output shape below. Do not add prose before or after it.

INPUT SHAPE
{
  "schema_version": 1,
  "batch_id": "...",
  "manifest_sha256": "...",
  "target_language": "ru",
  "terminology": {"source label": "approved Russian label"},
  "articles": [
    {
      "article_id": "...",
      "source_sha256": "...",
      "term": "Japanese headword",
      "reading": "Japanese reading",
      "sequence": 123,
      "kaishi_evidence": [
        {
          "word": "...",
          "reading": "...",
          "meaning_en": "...",
          "sentence_ja": "...",
          "sentence_en": "..."
        }
      ],
      "read_only_context": {
        "sense_groups": "complete normalized context for all senses",
        "examples": "Japanese and English examples paired to senses",
        "cross_references": "Japanese targets and English explanations"
      },
      "units": [
        {
          "unit_id": "...",
          "source_sha256": "...",
          "role": "glossary | example | pos | register | note | label | tooltip | xref_gloss | other_approved_role",
          "source_text": "English text to translate",
          "protected_tokens": ["tokens that must remain exact"],
          "local_context": "sense and example context needed for this unit"
        }
      ]
    }
  ]
}

OUTPUT SHAPE
{
  "schema_version": 1,
  "batch_id": "copy exactly",
  "manifest_sha256": "copy exactly",
  "translations": [
    {
      "unit_id": "copy exactly",
      "source_sha256": "copy exactly",
      "target_text": "Russian text-node replacement; surrounding source markup is preserved separately",
      "confidence": "high | medium | low",
      "review_reason": null
    }
  ]
}

Before returning, silently verify that every input unit appears exactly once, in order, every protected token is present unchanged, every target is a Russian text-node replacement containing no newly generated markup, and the response is valid JSON.
```

### Prompt input preparation rules

- `read_only_context` is a compact semantic projection, not the raw structured-content tree. It retains sense boundaries and examples but drops CSS/layout noise.
- A unit is an approved scalar `content` or `title` leaf with an RFC 6901 JSON Pointer stored in SQLite. The pointer is not sent back by the model; `unit_id` resolves it. Its surrounding structured-content/HTML-like nodes remain in the immutable source tree and are never discarded.
- Japanese examples and English translations are paired in the same context object.
- Repeated controlled labels use a versioned Russian terminology map. Glosses and examples are not globally deduplicated because the same English words can require different Russian translations in different Japanese contexts.
- Attribution and redirect nodes are excluded from translation units.
- Mixed text is masked or accompanied by `protected_tokens`; ambiguous mixed-content nodes are quarantined for review.

## 5. RE2 — SQLite-backed swarm plan

### Phase 0: bootstrap and reproduce the analysis

1. Download the two pinned artifacts and verify SHA-256 before extraction.
2. Save source URL, release, checksum, extractor version, and configuration in a `source_snapshot` row.
3. Pin copies of the upstream Yomitan index and term-bank schemas used for validation.
4. Run the small expression/reading lookup smoke test.

### Phase 1: import Kaishi scope

1. Extract the APKG.
2. Decompress `collection.anki21b` with Zstandard.
3. Read Anki `notes.flds`, splitting on U+001F.
4. Import the 1,500 vocabulary notes and their four disambiguating fields: word, reading, word meaning, Japanese/English sentence. Retain the Anki note ID and a source hash.
5. Do not copy audio, pictures, templates, or other media into the project output.

### Phase 2: ingest Jitendex and resolve scope

1. Parse term banks in numeric bank order and entries in array order.
2. Store each source entry as immutable JSON with `(snapshot, bank_number, entry_ordinal)` and SHA-256 identity.
3. Generate candidate mappings with the policy in section 3.
4. Resolve every candidate to included/excluded with evidence and reviewer identity.
5. Freeze a selection manifest. Any later selection change creates a new manifest/version; it must not mutate an active run invisibly.

### Phase 3: extract safe translation units

1. Traverse only selected articles.
2. Whitelist visible English leaves by semantic role, including glossary items, POS/register/domain labels and tooltips, sense notes, info glosses, English example B, reference labels, xref/antonym glosses, and forms labels.
3. Exclude Japanese example A, ruby/rt, Japanese form tables and link targets, redirect glossaries, attributions, source names, IDs, URLs, `data.*`, paths, style/layout values, and all unclassified strings.
4. Store each unit with article ID, JSON Pointer, role, source text/hash, protected tokens, byte count, and estimated token count.
5. Create a structural fingerprint of every source article with approved leaf values replaced by sentinels.
6. Quarantine an article if a string cannot be classified safely.

### Phase 4: terminology and pilot

1. Prepare a controlled Russian map for repeated labels and POS/register/domain terminology.
2. Select a stratified pilot covering small, median, p95, and maximum articles; multiple senses; examples; xrefs; notes; tables; mixed tokens; and kana fallback selection.
3. Use **half-size pilot batches: at most 6 articles, 24 KiB context, and 100 units**.
4. Duplicate several difficult pilot articles across two independent Terra agents to expose prompt ambiguity.
5. Review all pilot output and adjust only the versioned prompt, extractor whitelist, and terminology. A changed prompt or extractor invalidates unaccepted pilot output and creates a new run version.

### Phase 5: production translation swarm

At most three subagents run concurrently because the root orchestrator occupies the fourth available slot.

For every wave:

1. The orchestrator atomically claims up to three ready batches from SQLite.
2. For each batch, spawn a **fresh** agent with:
   - model `gpt-5.6-terra`;
   - reasoning effort `medium`;
   - no forked conversation history;
   - the versioned prompt path and one immutable batch manifest path.
3. Each agent handles one batch only and writes one strict response to its unique outbox path. It never edits SQLite or source JSON.
4. The orchestrator validates and imports the response in one transaction.
5. The agent is not reused. The next batch gets a new agent with an empty context.
6. Spawn the next wave only after the previous outputs have been persisted or marked retryable.

Production packing stops before adding the item that would exceed any limit:

```text
MAX_ARTICLES = 12
MAX_CONTEXT_UTF8_BYTES = 49_152
MAX_TRANSLATION_UNITS = 200
SINGLETON_ARTICLE_THRESHOLD = 16_384 bytes
```

The byte count includes the prompt-specific article envelopes and read-only context, not just English source strings. Save the actual serialized byte and token counts on the batch row. If a response is truncated, incomplete, malformed, or approaches an output ceiling, split the batch deterministically in half; if necessary, retry as a singleton. Never increase a cap during a run.

### Phase 6: deterministic validation and retry

Reject before import if any of the following is true:

- invalid output JSON or wrong schema version;
- batch ID or manifest hash mismatch;
- missing, duplicate, reordered, or extra unit IDs;
- source hash mismatch;
- non-string target, empty target, HTML/Markdown/tag-looking output, or control characters;
- protected token lost or modified;
- target lacks expected Cyrillic without an allowed proper-name reason;
- an unapproved amount of English remains;
- high-risk unit reports medium/low confidence without a review issue.

Retries keep the same immutable source units and record a new attempt. Maximum normal attempts: three. After that, split the batch or open an issue; never silently skip it.

### Phase 7: independent quality review

Every accepted translation candidate receives a second Terra Medium review by a fresh agent that did not produce it. Reviewer inputs contain source context and candidate Russian text, so review batches use tighter caps: **6 articles, 48 KiB combined source/target context, and 120 units**.

The reviewer checks:

- Japanese term/reading and intended Kaishi lexeme;
- every English gloss and the full sense boundary;
- Japanese example against both English source and Russian candidate;
- Russian aspect, government, register, terminology, and naturalness;
- omissions, additions, merged senses, false friends, and inconsistent repeated labels.

The reviewer returns unit-level `accept`, `replace`, or `needs_adjudication`. Corrections are persisted as a new reviewed version, never as an overwrite. Low-confidence, resolver-ambiguous, giant, and validation-warning entries require adjudication; a human review is recommended before public release.

### Phase 8: safe application and Yomitan build

1. Re-open the canonical source entry and verify its hash.
2. Resolve accepted unit IDs to stored JSON Pointers.
3. Replace only whitelisted scalar values with reviewed plain text.
4. Deterministically change `lang: "en"` to `lang: "ru"` only on nodes whose complete visible content was translated. Terra does not make this structural edit.
5. Recompute the structural fingerprint. It must match the source except for approved leaf values and the explicit `en` → `ru` language changes.
6. Translate `tag_bank` notes. If visible tag identifiers are localized, update the tag-bank name and every ASCII-space-delimited tag reference through one controlled mapping and verify referential integrity; preserve technical category fields.
7. Set `index.json.targetLanguage` to `ru`, give the derivative a distinct title/revision, and retain Jitendex/JMdict/Tatoeba attribution and CC BY-SA terms.
8. Copy `styles.css` unchanged. Copy only the media dependency closure referenced by selected entries, preserving exact paths and bytes.
9. Re-chunk selected rows deterministically into sequential `term_bank_N.json` files with stable ordering and a conservative per-file size.
10. Build a reproducible ZIP with `index.json` at its root.

### Phase 9: final verification

- Parse and validate every emitted JSON file against the pinned Yomitan schemas.
- Confirm the expected selected article and unit counts against SQLite.
- Confirm every accepted target hash is present at its intended pointer.
- Confirm all unapproved values, Japanese strings, ruby/rt pairs, links, IDs, layout, examples, and sense ordering match source.
- Verify every media path exists and no unreferenced Kaishi asset is included.
- Import into a clean Yomitan profile and smoke-test a stratified lookup list, including expression matches, reading matches, inflected verbs, kana-only words, multiple readings, xrefs, ruby, examples, tables, and long entries.
- Render or screenshot representative entries and compare source/target layout.
- Refuse release while any selected unit is unaccepted or any blocking issue is open.

## 6. SQLite progress model

Use `work/progress.sqlite3` with:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 10000;
```

Core tables and purpose:

| Table | Purpose and critical identity |
|---|---|
| `source_snapshot` | Input URLs, versions, hashes, schema/prompt/extractor versions |
| `kaishi_note` | Note ID, word, reading, meanings/examples, source hash |
| `article` | Immutable source entry keyed by snapshot/bank/ordinal; raw JSON hash |
| `selection_candidate` | Every Kaishi-to-article/sequence candidate and match evidence |
| `selection_decision` | Included/excluded decision, actor, reason, review status |
| `translation_unit` | Article, JSON Pointer, role, source/hash, protected tokens, status |
| `batch` | Manifest hash, hard-size measurements, state, lease, attempt count |
| `batch_item` | Deterministic ordered unit membership; each unit belongs to one batch |
| `attempt` | Worker/model/prompt hash, lease token, request/response paths, outcome |
| `translation` | Candidate target, confidence, source/target hashes, accepted version |
| `review` | Independent reviewer decision and replacement target if any |
| `validation_issue` | Validator, severity, code, details, resolution/waiver |
| `audit_event` | Append-only record of imports, claims, retries, decisions, and exports |
| `export` / `export_file` | Output manifest, file hashes, validation and smoke-test report |

Important constraints:

- source and manifest hashes are unique and immutable;
- one accepted reviewed translation per unit per run version;
- no unit can be in two production batches;
- no completed batch can be repacked;
- an output is accepted only if its complete item set and all hashes match;
- updates to source, prompt, terminology, extractor, limits, or selection create a new run/snapshot version.

Batch state machine:

```text
ready -> leased -> submitted -> deterministic_validated
      -> model_reviewed -> complete

leased/submitted -> retryable -> ready
any state -> blocked (with an open issue)
```

Claims use `BEGIN IMMEDIATE`, a random lease token, and a lease expiry. Heartbeats conditionally extend only the matching worker/token lease. Expired work is returned to `ready` only if it has no accepted output. This gives safe resume after interruption and prevents duplicate acceptance even if two workers finish the same expired batch.

## 7. RE3 — tools and operating instructions

### 7.1 Required tools

| Tool | Use |
|---|---|
| Python 3.12+ standard library | ZIP/JSON/SQLite/hash processing and CLI orchestration |
| `sqlite3` | Inspection, migrations, integrity checks, progress reporting |
| `zstd` | Decompress modern Anki `collection.anki21b` |
| `unzip` / Python `zipfile` | Source extraction and deterministic output ZIP |
| `jsonschema` or an equivalent pinned validator | Validate Yomitan index and term-bank schemas |
| Yomitan in a clean browser profile | Real import, lookup, and render smoke tests |
| CodeGraph | Structural search/refactoring once implementation code exists |

Do not introduce an Anki runtime dependency merely to extract four note fields; the APKG collection is already SQLite after Zstandard decompression.

### 7.2 Planned repository layout

```text
PLAN.md
prompts/
  translate_terra_v1.txt
  review_terra_v1.txt
schemas/
  worker-input-v1.schema.json
  worker-output-v1.schema.json
  pinned-yomitan/
src/jitendex_ru/
  acquire.py
  import_kaishi.py
  import_jitendex.py
  resolve_selection.py
  extract_units.py
  batch.py
  validate_response.py
  apply_translations.py
  build_dictionary.py
  cli.py
tests/
work/                  # ignored; resumable DB and agent inbox/outbox
dist/                  # final ZIP and reports
```

### 7.3 One orchestration CLI

Expose all mutations through an idempotent CLI so agents never improvise shell/database writes:

```text
translationctl acquire --config config.toml
translationctl import-sources
translationctl resolve-scope
translationctl report scope
translationctl extract-units
translationctl make-batches --max-articles 12 --max-bytes 49152 --max-units 200
translationctl claim --worker-id ...
translationctl ingest-response work/outbox/<attempt>.json
translationctl validate --run-id ...
translationctl make-review-batches
translationctl ingest-review work/review-outbox/<attempt>.json
translationctl build --output dist/jitendex-kaishi-ru.zip
translationctl verify dist/jitendex-kaishi-ru.zip
translationctl report progress
```

Every mutating command runs in a transaction, writes an audit event, and is safe to repeat. `report` and `verify` are read-only.

### 7.4 Test strategy

- Unit tests for Anki field extraction, normalization, candidate grouping, JSON Pointer application, tag remapping, and deterministic batching.
- Golden structural-content fixtures for glosses, examples, xrefs, antonyms, notes, forms tables, redirects, ruby, and media.
- Property test: applying arbitrary approved plain-text translations changes only whitelisted leaves.
- Corruption tests: missing IDs, duplicate units, wrong hashes, HTML output, altered protected tokens, expired leases, and truncated JSON must fail closed.
- Reproducibility test: two builds from the same accepted DB state have identical file hashes and ZIP hash.
- End-to-end test: import the ZIP into Yomitan and exercise expression and reading lookups.

## 8. Risk controls

### RS1: degraded translation quality

Mitigations:

- full Japanese term/reading, complete English senses, Japanese examples, English examples, and Kaishi evidence accompany every article;
- sense grouping is explicit and cannot be reordered by the worker;
- controlled Russian terminology is shared across all batches;
- optional Russian JMdict glosses keyed by sequence may be included as secondary reference, never as a substitute for translating Jitendex examples/notes;
- stratified pilot with duplicated difficult entries before production;
- one fresh agent per batch and strict context caps;
- confidence/review-reason capture;
- independent review of 100% of output and adjudication for risky cases;
- cross-batch consistency reports for repeated labels and common translations;
- release blocked on unresolved errors.

### RS2: HTML/structured-markup problems

Mitigations:

- Terra translates scalar text-node values only; it never returns an article tree or rewrites markup. The assembler patches those values into the canonical tree, preserving all surrounding structured-content/HTML-like nodes;
- JSON Pointers, structural fingerprints, and source hashes bind every unit to the canonical source;
- tags, keys, arrays, `data.*`, hrefs, paths, CSS, ruby/rt, IDs, tables, and node order remain under deterministic code control;
- `lang` changes are narrow and scripted;
- output schema, upstream Yomitan schema, dependency-closure, and render/import validation all fail closed;
- no raw string concatenation builds JSON or HTML; serializers perform escaping.

### Additional risks

| Risk | Mitigation |
|---|---|
| Wrong Kaishi/Jitendex homograph | Semantic sequence-resolution gate using meanings and examples; reviewed decisions |
| Terra context/output overflow | Fresh single-batch agents; 12/48 KiB/200 caps; singleton giants; split-and-retry |
| Interrupted run or duplicate worker | SQLite WAL, atomic leases, idempotent manifests, unique accepted-output constraint |
| Source drift | Pinned releases/hashes; immutable snapshots; no reuse across changed snapshots |
| Licence/attribution loss | Preserve Jitendex, JMdict, Tatoeba attribution and CC BY-SA 4.0 in index/release; identify derivative clearly |
| False Kaishi affiliation | Use deck only as scope evidence; do not ship its assets or claim endorsement |
| Inconsistent labels | Versioned controlled terminology and deterministic tag mapping |

## 9. Definition of done for the implementation phase

The implementation is complete only when:

1. every Kaishi vocabulary note has an audited selection resolution;
2. every selected translatable unit has one accepted, independently reviewed Russian value;
3. no blocking validation issue remains;
4. deterministic and model quality reports are stored with the export;
5. the ZIP validates against pinned Yomitan schemas and imports into a clean Yomitan profile;
6. expression- and reading-based lookup smoke tests pass;
7. representative layouts, examples, ruby, links, and long articles render correctly;
8. source attribution and derivative licensing are present;
9. the build is reproducible from the SQLite snapshot and accepted outputs.

## 10. Primary references

- [Pinned Jitendex release asset](https://github.com/stephenmk/stephenmk.github.io/releases/download/2026.07.09.0/jitendex-yomitan.zip)
- [Kaishi 1.5k on AnkiWeb](https://ankiweb.net/shared/info/1196762551)
- [Official Kaishi repository and releases](https://github.com/donkuri/kaishi)
- [Yomitan dictionaries documentation](https://yomitan.wiki/dictionaries/)
- [Yomitan format-3 term-bank schema](https://github.com/yomidevs/yomitan/blob/master/ext/data/schemas/dictionary-term-bank-v3-schema.json)
- [Yomitan dictionary index schema](https://github.com/yomidevs/yomitan/blob/master/ext/data/schemas/dictionary-index-schema.json)
- [Yomitan dictionary lookup implementation](https://github.com/yomidevs/yomitan/blob/master/ext/js/dictionary/dictionary-database.js)
- [JMdict Yomitan project, including Russian builds](https://github.com/yomidevs/jmdict-yomitan)
