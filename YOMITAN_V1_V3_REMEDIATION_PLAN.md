# YRP — Yomitan V1–V3 remediation and release plan

## YRP-STATUS — Status and purpose

YRP-STATUS-1 — This plan was written on 2026-08-17 from `main` at commit `eab8ed4`.

YRP-STATUS-2 — This plan covers the three Yomitan export questions called V1, V2, and V3. It preserves enough evidence, design decisions, commands, gates, and publication steps to resume the work without the original conversation.

YRP-STATUS-3 — V1 asks which English text remains inside the Russian dictionary and which text is unfinished localization.

YRP-STATUS-4 — V2 asks why Yomitan update replaced `Колобок 400k` with English Jitendex and how dictionary identity and updates must work.

YRP-STATUS-5 — V3 asks which Jitendex ties remain in metadata and which ties are required attribution rather than product identity.

YRP-STATUS-6 — The target release is `Колобок 400k` version `1.0.1`. This is a repair release with no corpus expansion.

YRP-STATUS-7 — The plan ends only after the corrected archives, update index, release notes, download page, and public release are published.

## YRP-EXEC — Execution status on main

YRP-EXEC-1 — `LOCAL PASS COMPLETE` as of 2026-08-20 on `main`. This pass used the main thread and local Python tooling only. It did not spawn agents and did not call the Codex CLI.

YRP-EXEC-2 — `DONE` for YRP-V1A and YRP-CODE-1–2. `yomitan_remediation.py` localizes redirects, the long forms tooltip, and structurally identified `<form> only` labels. The full 433,885-article source snapshot must match 136,668 redirects, 4,307 tooltips, and 4,307 total short restrictions. Of those restrictions, 74 were still broken in the published v1.0 archive; the other 4,233 had been localized earlier inside `apply_article()`. Build and verification results expose the counters or issue counts.

YRP-EXEC-3 — `PARTIAL` for YRP-V1B and YRP-CODE-3–5. The released v1.0 ZIP now has a reproducible archive audit, worker validation rejects adjacent mixed alphabets, and the canonicalizer accepts a hash-locked approved remediation manifest with immutable history and idempotence checks. The database-target audit with source text and local context, semantic review, approval of the 172 findings, and production application remain pending.

YRP-EXEC-4 — `PARTIAL` for YRP-V1D. The scanner follows visible glossary scalars plus `content` and `title`, ignores structural keys, and blocks raw V1 templates and adjacent Cyrillic/Latin tokens. The full `MUST_PRESERVE`/`REVIEW` classifier, checked-in approval record, role-aware residual-English gate, and `lang: en` role gate remain pending.

YRP-EXEC-5 — `PARTIAL` for YRP-V2A. The Yomitan title is now the exact stable `Колобок 400k`; version `1.0.1` lives in release metadata and the independent revision. Unit and integration tests reject the old versioned title. A real Yomitan upgrade simulation remains in YRP-SMOKE.

YRP-EXEC-6 — `PARTIAL` for YRP-V2B. Operational metadata is generated from an explicit Kolobok allowlist, upstream updater fields are discarded, and builds omit all updater fields until publication. Code can generate the staged owned `yomitan.json` from archive metadata and tests require exact owned URLs. Schema validation, HTTPS fetches, deployed asset hashes, and enabling the updater remain publication gates.

YRP-EXEC-7 — `PARTIAL` for YRP-V2C. New revisions start with the frozen Kolobok compilation date and Kolobok release identity; they no longer copy the upstream Jitendex revision. Comparison with the last published Kolobok revision remains pending until release freeze.

YRP-EXEC-8 — `PARTIAL` for YRP-V2D and YRP-DOC-7. README and the public-site source now warn v1.0 users not to press Yomitan's update button and to install v1.0.1 manually after publication. The warning is not public until the site commit is pushed and Pages succeeds.

YRP-EXEC-9 — `PARTIAL` for YRP-V3A. Build code rejects foreign operational Jitendex URLs and uses the stable Kolobok title, product ID, versioned output ID, and independent revision. Final site links, release filenames, state IDs, and immutable release history need final artifacts and therefore remain pending.

YRP-EXEC-10 — `DONE` for the code-level part of YRP-V3B. Explicit metadata generation preserves upstream attribution, Jitendex/JMdict/Tatoeba names, Stephen Kraus, creator and license text, while operational updater fields are not copied. Internal resource paths, acquisition input URLs, package names, and comparison labels were not renamed.

YRP-EXEC-11 — `PARTIAL` for YRP-VERSION. `DICTIONARY_VERSION` is `1.0.1`, `PRODUCT_ID` and `PRODUCT_NAME` are unchanged, and the Yomitan title is stable. `COMPILATION_DATETIME_UTC` intentionally remains at the v1.0 value until content and code freeze, as required by YRP-VERSION-2.

YRP-EXEC-12 — `DONE` for the local pre-change archive audit. `reports/yomitan_localization/run59-v1.0-before.json` records Run 59, archive SHA-256 `24c0164f6d645f6426bef5b09f5dfdc46952cf132aed6d8bc033800f9ff7824b`, 433,885 articles, 136,668 raw redirects, 4,307 raw tooltips, 74 raw short restrictions, and 172 mixed-token occurrences with exact ZIP members and JSON pointers.

YRP-EXEC-13 — `DONE` for the currently executable automated test gate. The full suite collected 163 tests: 161 passed and two documented existing tests skipped. No test failed.

YRP-EXEC-14 — `NOT STARTED` for YRP-DATA. No production database write, backup, semantic review, candidate acceptance, or history mutation was attempted. These steps require an approved remediation manifest and the production safety sequence in YRP-DATA.

YRP-EXEC-15 — `BLOCKED BY YRP-DATA` for YRP-BUILD. The new lexical gate intentionally prevents a release build while mixed-alphabet defects remain in accepted translations. No v1.0.1 archive or export record was created.

YRP-EXEC-16 — `NOT STARTED` for YRP-SMOKE. Clean-profile import, rendering, and updater behavior require final archives and Yomitan client work.

YRP-EXEC-17 — `UNREACHABLE IN THIS PASS` for YRP-PUB. No release, upload, push, Pages deployment, or public endpoint change was performed.

YRP-EXEC-18 — `COMMIT MESSAGE` for this pass is `Fix Yomitan localization and isolate updates from upstream`. The impact is that future Russian exports cannot retain the known English UI templates or silently direct users to an English Jitendex download; production text defects now fail closed until approved remediation.

YRP-EXEC-19 — `.idea/` remains untouched and untracked as required by YRP-COMMIT-2.

YRP-EXEC-20 — `IN PROGRESS` as of 2026-08-21. The production continuation still runs on `main` without worker agents or the Codex CLI. Run 59 has zero active batches, zero active attempts, zero unresolved blocking errors, and 2,053,045 accepted translations for 2,053,045 units.

YRP-EXEC-21 — `DONE` for the database-level pre-change audit. Unicode-aware detector `yomitan-visible-text-v2` scanned every accepted target and found 295 mixed-alphabet occurrences in 288 units. The report is `reports/yomitan_localization/run59-v1.0.1-before.json` with SHA-256 `4dbc55a9427adf175c98c7175c43e5eb8cc3e4adab95ee9a58755e09f8e5bf56`.

YRP-EXEC-22 — `DONE` for remediation review and approval. `terminology/yomitan-v1.0.1-approved-remediation.json` contains 288 hash-locked changes and has SHA-256 `4d77c055656e9c6e59825cbee6a68de541cafbdb05a57d514459e4992a3d9e15`. The separate before/after approval record has SHA-256 `d67037ca7d528334aa59b94dc215af0f50297a2c3fb07837d2f2249e5b3c9372`.

YRP-EXEC-23 — `DONE` for the pre-write backup. `work/backups/jitendex-postgresql-before-yomitan-v1.0.1.dump` is a validated PostgreSQL custom-format dump, is 4.6 GB, and has SHA-256 `8285e75871536c1f2a0debd4534ccafa1a556d0303a85bd98d29cedc041c0bb7`. The dump is not committed.

YRP-EXEC-24 — `FIXED` for PostgreSQL integrity evidence. `run_history_fingerprint()` now normalizes backend-native timestamps and includes `translation_canonicalization_history`; the previous implementation failed before producing a PostgreSQL fingerprint. The pre-change Run 59 fingerprint is `222f939fdea6c279300fd0a97302e214e4f0be5880952bcd3417c3d60822c0f1` with zero canonicalization-history rows.

YRP-EXEC-25 — `DONE` for the pre-write automated test gate. The suite collected 164 tests: 162 passed and two documented existing tests skipped.

YRP-EXEC-26 — `DONE` for production canonicalization. The first transaction changed 2,447 targets: 288 from `approved_yomitan_v1_0_1_remediation` and 2,159 from the existing `approved_jitendex_tag_catalog` final-run rule. The second transaction changed zero targets. Canonicalization history contains exactly 2,447 immutable rows.

YRP-EXEC-27 — `DONE` for post-change data gates. The database audit scanned all 2,053,045 accepted targets and found zero mixed-alphabet or raw-template findings. Validation reports zero blocking issues, zero batch-membership mismatches, and unchanged accepted coverage of 2,053,045/2,053,045.

YRP-EXEC-28 — `DONE` for Run 59 integrity comparison. The post-change fingerprint is `352420963a88cc1d14875fdcd1a0c32ff1e61c3407f18f8a8b458629c9a3386b`. `run`, `run_article`, `translation_unit`, `batch`, `batch_item`, `attempt`, `review`, `validation_issue`, and all existing export tables are byte-identical to the pre-change fingerprint. Only `translation` and the new `translation_canonicalization_history` rows changed.

YRP-EXEC-29 — `FIXED` after the first full materialization preflight. Moving all form-restriction localization into the counted build pass correctly exposed 4,307 source `<form> only` labels, not only the 74 labels left broken by the legacy partial pass. The pinned build count now covers all 4,307 transformations while YRP-BASELINE-3 continues to describe the 74 v1.0 residual defects.

YRP-EXEC-30 — `DONE` for the corrected full Yomitan preflight at commit `391becc`. Export 88 built all 433,885 articles into 370 ZIP members with 136,668 redirects, 4,307 tooltips, and 4,307 short restrictions localized. Independent verification validated 131 banks, found zero localization issues, and confirmed ZIP SHA-256 `bad9acfcfa5ae5e59d1cc4071e0f2ce898a084b3e26c7d0d7f667497e913bb18`. This is a preflight artifact, not the frozen release.

YRP-EXEC-31 — `IN PROGRESS` for the permanent lexical gate. A role-aware database scan confirmed that common English function words in Russian targets are intentional grammar quotations or product names. A stricter residual pass found a small set of genuine misses, including `proceedings`, `пу anything`, `Filipino marshal art`, `corn flour`, `Windows error screen`, and three raw `English:` language labels. These findings require an additional approved manifest pass before release freeze.

YRP-EXEC-32 — `APPROVED` for the residual lexical repair. Detector `yomitan-visible-text-v3` scanned all 2,053,045 accepted targets and selected 27 exact target rows for correction while preserving reviewed brands, taxa, romanized Japanese, grammar quotations, JMdict, Tatoeba, Jitendex, author names, and license identifiers. The lexical audit SHA-256 is `e3447fb4d9e4ba31e0b6c8f3b643b2e26cfde781b17288d3ac2c335002f37775`; the 27-row hash-locked manifest is `terminology/yomitan-v1.0.1-approved-lexical-remediation.json` with SHA-256 `07746f61422324adc5bfd6d5fadb9a12cdc14fba76ca0af8e81883f98bdf0f26`; the separate approval record has SHA-256 `3292a446ff44a69622669889555184c1edd31b777fd40e87bf6718f5cabcf455`.

YRP-EXEC-33 — `DONE` for reviewed image-attribution chrome. The structured build pass now changes all 444 attribution connectors from `by` to `автор`, all 60 generic `Photo` labels to `Фото`, and the one generic `Unknown author` label to `неизвестный автор`. Creator names, original work titles, source links, and license identifiers remain unchanged.

YRP-EXEC-34 — `DONE` for the second production canonicalization. The first transaction applied exactly 27 approved lexical repairs and the second applied zero. Run 59 now has 2,474 immutable canonicalization-history rows: the earlier 2,447 structured/mixed repairs plus these 27 lexical repairs. The final detector reports zero findings across all 2,053,045 accepted targets; validation again reports zero blocking issues and zero batch-membership mismatches.

YRP-EXEC-35 — `DONE` for the final post-data fingerprint. The Run 59 fingerprint is `fa853b11f545436647f3ef1d2c3ad28b64fed5d8644ae459c2185f272cf93eaf`. Article scope, source units, attempts, batches, batch items, reviews, and validation issues are unchanged. Translation history grew only by the approved 27 rows; export tables also contain the separately recorded preflight export 88.

YRP-EXEC-36 — `DONE` for staged owned-update mode. `translationctl build --enable-yomitan-updates` writes the complete Kolobok-owned update tuple, and `translationctl verify --require-yomitan-updates` fails unless that tuple is present and exact. Ordinary preflight builds continue to omit updater fields. The hosted index generator now accepts either staged form and still derives all canonical fields from the archive.

## YRP-SOURCE — Source of truth

YRP-SOURCE-1 — The authoritative database is PostgreSQL configured by `config.luna.toml`. Do not repair the old SQLite database and do not return production writes to SQLite.

YRP-SOURCE-2 — Run 59 is the completed full-corpus run with 433,885 Jitendex articles and 431,545 translated headwords.

YRP-SOURCE-3 — The current Yomitan release archive is `dist/jp-ru-kolobok-400k-v1.0-yomitan.zip`.

YRP-SOURCE-4 — Its verified SHA-256 is `24c0164f6d645f6426bef5b09f5dfdc46952cf132aed6d8bc033800f9ff7824b`.

YRP-SOURCE-5 — Its current release identity is recorded in `README-STATE-1`, `README-STATE-8`, `README-STATE-9`, and `HIST-TAGS-RU-V1-9`.

YRP-SOURCE-6 — Its current `index.json` title is `Колобок 400k v1.0`, target language is `ru`, and revision is `2026.07.09.0-jp-ru-kolobok-400k-v1.0-tags-ru-v1`.

YRP-SOURCE-7 — Its current `indexUrl`, `downloadUrl`, and `url` still point to Jitendex. These fields are the confirmed cause of V2.

YRP-SOURCE-8 — The audit counted every visible string in all 433,885 term rows. Two independent Luna agents then checked the structural and semantic classifications.

## YRP-BASELINE — Confirmed V1 baseline

| ID | Class | Current count | Required action |
|---|---|---:|---|
| YRP-BASELINE-1 | `redirected from …` | 136,668 | Translate deterministically |
| YRP-BASELINE-2 | `valid only for these forms and/or readings` | 4,307 | Translate deterministically |
| YRP-BASELINE-3 | `<form> only` restriction labels | 74 | Translate deterministically |
| YRP-BASELINE-4 | Correct `only` uses | 7 | Preserve |
| YRP-BASELINE-5 | Archive rows with adjacent Cyrillic and Latin letters inside a token | 154 | Review and repair accepted translations |
| YRP-BASELINE-6 | Alphabet transitions inside those mixed tokens | 179 | Reach zero after approved repair |
| YRP-BASELINE-7 | ASCII-only glossary values | 932 | Preserve as acronyms, codes, or formulas |
| YRP-BASELINE-8 | `JMdict` attribution labels | 296,172 | Preserve |
| YRP-BASELINE-9 | `Tatoeba` attribution content | 41,045 plus 3,801 separator forms | Preserve |
| YRP-BASELINE-10 | `graphic-attribution` blocks | 444 | Classify field by field |
| YRP-BASELINE-11 | ` by ` connectors inside image attribution | 332 | Localize without changing author identity |
| YRP-BASELINE-12 | `Photo` image labels | 60 | Localize or show bilingually |
| YRP-BASELINE-13 | Tag-bank rows | 8 | Visible text is already Russian |

YRP-BASELINE-14 — The 136,668 redirect strings represent 135,709 unique source forms. `redirected from 社会情報學` is one confirmed example.

YRP-BASELINE-15 — The 74 broken short restrictions include `３０ only`, `ＡＮＤ only`, `Ｈ only`, and `Ω only`.

YRP-BASELINE-16 — The seven correct `only` uses include `read-only member`, `download-only member`, and `IF-AND-ONLY-IF`. They must not be changed by a global replacement.

YRP-BASELINE-17 — Confirmed mixed-alphabet defects include `гikun`, `Хокурiku`, `emphатично`, `мекури-карутa`, `листoед`, `пурсерa`, `некрасивaя`, `Джимy`, `вывелa`, and `гuy`.

YRP-BASELINE-18 — The sentence `Мы вчера вечером, выпив, ходили по всему городу и вовсю кут losили.` occurs twice and must become normal Russian text.

YRP-BASELINE-19 — No fully English `example-sentence-b` translation was found. Latin text in translated examples is mostly a brand, acronym, URL, program name, or quoted language material.

YRP-BASELINE-20 — No visible tag-bank label or description contains untranslated English prose.

## YRP-CLASS — Permanent classification rules

YRP-CLASS-1 — `MUST_TRANSLATE` contains normal English prose in a Russian definition, cross-reference gloss, note, label, tooltip, register, part-of-speech description, or translated example.

YRP-CLASS-2 — `MUST_TRANSLATE` contains fixed UI templates such as `redirected from`, `valid only for these forms and/or readings`, and restriction labels ending in `only`.

YRP-CLASS-3 — `MUST_TRANSLATE` contains broken hybrid words that join Cyrillic and Latin letters without an intentional separator.

YRP-CLASS-4 — `MUST_PRESERVE` contains `Jitendex`, `JMdict`, `Tatoeba`, author names, usernames, URLs, and exact license identifiers.

YRP-CLASS-5 — `MUST_PRESERVE` contains brands, product names, scientific taxa, acronyms, formulas, standard codes, keyboard chords, and quoted source-language forms.

YRP-CLASS-6 — `MUST_PRESERVE` contains Japanese `example-sentence-a`, ruby text, readings, and headword forms even when those strings contain Latin brand names.

YRP-CLASS-7 — `MUST_PRESERVE` contains internal Yomitan category and rule codes such as `popular`, `archaism`, `v1`, `v5`, `adj-i`, and `vs`.

YRP-CLASS-8 — `REVIEW` contains an isolated English word in otherwise Russian prose when the word may be a term, brand, quotation, or missed translation.

YRP-CLASS-9 — `REVIEW` contains romanized Japanese terms such as `kyūjitai`, `jukujikun`, `gikun`, and `ateji`. The romanization may remain, but its spelling must be consistent and must not mix alphabets.

YRP-CLASS-10 — `REVIEW` contains image descriptions and source work titles. Russian display text may be added, but creator identity, source link, original title, and license must remain recoverable.

## YRP-V1A — Fix deterministic structural text

YRP-V1A-1 — Do not send the 141,049 fixed templates to Luna. Their meaning is stable and the Japanese variable part must remain byte-for-byte unchanged.

YRP-V1A-2 — Add a build-time localization pass beside tag localization in `src/jitendex_ru/build_dictionary.py` or a small dedicated module imported by it.

YRP-V1A-3 — The redirect rule must match only a complete visible string shaped as `redirected from {source-form}`.

YRP-V1A-4 — The redirect rule must preserve `{source-form}` exactly, including old kanji, compatibility ideographs, kana, fullwidth Latin text, digits, punctuation, and whitespace semantics.

YRP-V1A-5 — Choose one approved Russian template before implementation. The recommended display is `вариант написания: {source-form}` because it describes the user-visible relation without implying a web redirect.

YRP-V1A-6 — Record the approved redirect template as a versioned constant and cover it with exact tests.

YRP-V1A-7 — Replace the exact tooltip `valid only for these forms and/or readings` with `допустимо только для этих форм и/или чтений`.

YRP-V1A-8 — Generalize `_localize_mixed_form_restrictions()` so a complete `<form> only` label becomes `только <form>` when the node is a Jitendex form restriction.

YRP-V1A-9 — Do not require Japanese characters in `<form>`. Accept Japanese, Greek, digits, and fullwidth Latin forms when the surrounding structural identity proves that the text is a restriction label.

YRP-V1A-10 — Do not replace `only` in `lang-source` quotations, normal definitions, brand names, or terms such as `IF-AND-ONLY-IF`.

YRP-V1A-11 — Change `lang: en` to `lang: ru` only on leaves whose visible prose was localized. Preserve `lang: ja` on the variable Japanese form.

YRP-V1A-12 — Return counters for redirect replacements, long-tooltip replacements, and short-restriction replacements from the build.

YRP-V1A-13 — Store those counters in the export audit event and expose them in `build()` and `verify()` results.

YRP-V1A-14 — Make `verify()` independently rerun the check and fail if any raw `redirected from`, raw long tooltip, or unapproved restriction `only` remains.

YRP-V1A-15 — Require source transformation counts of 136,668 redirects, 4,307 long tooltips, and 4,307 short restrictions for this pinned Jitendex snapshot. The short-restriction total includes the 4,233 Japanese-form labels already repaired by the legacy v1.0 build path and the 74 residual numeric, Greek, and fullwidth-Latin defects. A source snapshot change must require a reviewed baseline change rather than silently accepting new counts.

## YRP-V1B — Audit and repair accepted translations

YRP-V1B-1 — Do not patch mixed-alphabet defects directly inside the ZIP. The accepted database translation and its provenance are the source of the exported text.

YRP-V1B-2 — Add a deterministic post-translation audit command that scans accepted targets by role and emits JSON with run ID, article ID, unit ID, JSON pointer, role, source text, current target, target SHA-256, detected token, and issue code.

YRP-V1B-3 — Detect an adjacent Cyrillic-to-Latin or Latin-to-Cyrillic transition inside one token. Hyphenated forms such as `JIT-компилятор`, `3D-принтер`, and `USB-концентратор` must not trigger this rule.

YRP-V1B-4 — Add exact issue codes for mixed alphabet, suspicious unprotected English, raw UI template, and unexpected English-language markup.

YRP-V1B-5 — Write the first full report under `reports/yomitan_localization/` with the release version, run ID, source snapshot hash, archive hash, detector version, and per-class counts.

YRP-V1B-6 — Batch only the `REVIEW` rows for Luna semantic classification. Give Luna the source English, current Russian target, role, protected tokens, and local structured context.

YRP-V1B-7 — Ask Luna for a classification, proposed corrected target, confidence, and short reason. Luna output is a proposal and is not automatically accepted.

YRP-V1B-8 — Review every proposed target that changes meaning, a proper name, a scientific name, a quoted source form, or an attribution field.

YRP-V1B-9 — Produce an approved remediation manifest keyed by run ID, unit ID, source SHA-256, previous target SHA-256, and canonical target text.

YRP-V1B-10 — Extend the existing final canonicalization workflow to consume the approved remediation manifest after verifying every identity and hash.

YRP-V1B-11 — Record every change in `translation_canonicalization_history` with a new canonicalizer version and mapping source such as `approved_yomitan_v1_0_1_remediation`.

YRP-V1B-12 — Never overwrite history without first inserting the previous text, previous hash, canonical text, canonical hash, mapping identity, and canonicalizer version.

YRP-V1B-13 — Make the remediation canonicalizer fail closed on an unknown unit, source mismatch, previous-target mismatch, duplicate unit, unaccepted translation, or missing manifest row.

YRP-V1B-14 — Run the canonicalizer twice. The first run must report the approved changed count. The second run must report zero changes.

YRP-V1B-15 — Extend `validate_response.py` so future Luna responses cannot introduce adjacent mixed alphabets in a token.

YRP-V1B-16 — Replace the current broad allowance of up to two unprotected ASCII words with role-aware residual checks. A residual word in a definition must be protected, allowlisted, or sent to review.

YRP-V1B-17 — Preserve the narrow rules for taxa, acronyms, brands, URLs, keyboard chords, quoted grammar tokens, and source-language quotations.


## YRP-V1D — Build a permanent lexical release gate

YRP-V1D-1 — Add a post-export scanner that traverses only user-visible `content`, `title`, and glossary scalar values while retaining the closest selectors and JSON pointer.

YRP-V1D-2 — Do not scan structural values such as `tag`, `data.content`, `href`, `path`, `src`, CSS, media filenames, or Yomitan rule codes as visible prose.

YRP-V1D-3 — Classify every Latin-bearing visible leaf as `MUST_TRANSLATE`, `MUST_PRESERVE`, or `REVIEW` using explicit rules and allowlists.

YRP-V1D-4 — Fail the release on any `MUST_TRANSLATE` result.

YRP-V1D-5 — Require a checked-in approval record for every `REVIEW` result. The approval record must include the exact string or stable identity and a reason.

YRP-V1D-6 — Report `MUST_PRESERVE` counts so a large unexpected change is visible even when it is legal.

YRP-V1D-7 — Require zero visible nodes with `lang: en` in Russian translation roles. Allow English only in explicit source quotation and attribution roles.

YRP-V1D-8 — Require zero adjacent mixed-alphabet transitions in translated roles.

YRP-V1D-9 — Require zero raw V1 UI templates.

YRP-V1D-10 — Require the eight tag-bank rows to match the approved Russian catalog exactly while leaving category codes unchanged.

YRP-V1D-11 — Make the scanner usable against both a ZIP and materialized database rows so pre-build and post-build results can be compared.

## YRP-V2A — Define stable Yomitan identity

YRP-V2A-1 — Yomitan has no separate opaque dictionary ID in this format. The installed title is used to find and delete the current dictionary during an update.

YRP-V2A-2 — Use the stable installed title `Колобок 400k` for Yomitan releases. Do not place the release version in the Yomitan title.

YRP-V2A-3 — Put `1.0.1` in `revision`, `description`, release notes, archive filename, and manifest metadata.

YRP-V2A-4 — Other formats may keep their current versioned display rules if their clients do not use the title as update identity.

YRP-V2A-5 — Update the Yomitan verifier. It must require the exact stable title, not merely search for `v1.0.1` inside the title.

YRP-V2A-6 — Add an upgrade test that starts with an installed stable title and imports a newer archive whose revision changes but whose title does not.

YRP-V2A-7 — Add a test that rejects a future Yomitan archive whose title accidentally includes a version or changes the stable product name.

## YRP-V2B — Create an owned update channel

YRP-V2B-1 — Host the Kolobok update index on the public project site, not on Jitendex infrastructure.

YRP-V2B-2 — Use an owned URL such as `https://ganqqwerty.github.io/jp-ru-kolobok-dictionary/yomitan.json` after confirming the final Pages path.

YRP-V2B-3 — Set `url` to `https://ganqqwerty.github.io/jp-ru-kolobok-dictionary/`.

YRP-V2B-4 — Set `indexUrl` to the owned `yomitan.json` URL.

YRP-V2B-5 — Set `downloadUrl` to the versioned asset for the current release or to an owned stable release asset. It must never point to `stephenmk` or another upstream Jitendex release.

YRP-V2B-6 — Keep `isUpdatable: true` only when the owned index and owned download URL are already deployed and verified.

YRP-V2B-7 — If the owned endpoint cannot be deployed for `1.0.1`, remove `isUpdatable`, `indexUrl`, and `downloadUrl` from the archive. Shipping no updater is safer than shipping a foreign updater.

YRP-V2B-8 — Generate the hosted update index from the same release metadata source as the archive. Do not maintain a second hand-written revision.

YRP-V2B-9 — The hosted index must include the exact stable title, current revision, source language `ja`, target language `ru`, project URL, owned download URL, author, description, and attribution required by the pinned Yomitan schema.

YRP-V2B-10 — Validate the hosted index with the pinned Yomitan index schema before publication.

YRP-V2B-11 — Fetch the hosted index over HTTPS during the release gate and compare its canonical fields with the archive `index.json`.

YRP-V2B-12 — Fetch the hosted download URL during the release gate and require its SHA-256 to equal the verified release archive.

YRP-V2B-13 — Add a metadata allowlist that rejects `jitendex.org`, `stephenmk`, and `jitendex-yomitan.zip` in operational fields while permitting those words in attribution text.

## YRP-V2C — Use an independent revision

YRP-V2C-1 — Stop copying the upstream Jitendex revision as the prefix of the Kolobok revision.

YRP-V2C-2 — Generate a monotonic Kolobok revision from the release compilation timestamp and product version.

YRP-V2C-3 — The recommended shape is `YYYY.MM.DD.N-jp-ru-kolobok-400k-v1.0.1-tags-ru-v1`.

YRP-V2C-4 — Store the revision in one release metadata source and use it for the archive, hosted update index, reports, and release notes.

YRP-V2C-5 — Add comparison tests for an older revision, the same revision, and a newer revision using Yomitan-compatible comparison behavior.

YRP-V2C-6 — Fail the build if the new revision is not greater than the last published Kolobok revision.

## YRP-V2D — Handle users of broken v1.0

YRP-V2D-1 — The installed v1.0 archive cannot be repaired remotely. It asks `https://jitendex.org/static/yomitan.json`, which is controlled by upstream Jitendex.

YRP-V2D-2 — Do not advise v1.0 users to press Yomitan's update button. That action can replace Kolobok with English Jitendex.

YRP-V2D-3 — Publish a prominent upgrade notice that v1.0 users must manually download and import v1.0.1 once.

YRP-V2D-4 — Tell users to remove an accidentally installed English Jitendex copy if the old update button already replaced Kolobok.

YRP-V2D-5 — After manual v1.0.1 installation, future updates may use the owned Kolobok index.

YRP-V2D-6 — Test the notice with a clean Yomitan profile and with a profile containing the broken v1.0 archive.

## YRP-V3A — Remove operational Jitendex identity

YRP-V3A-1 — Replace Jitendex operational URLs in `index.json` with owned Kolobok URLs.

YRP-V3A-2 — Remove the upstream Jitendex revision prefix from the Kolobok revision.

YRP-V3A-3 — Keep the stable Yomitan title `Колобок 400k` and product ID `jp-ru-kolobok-400k`.

YRP-V3A-4 — Publish only branded release asset names such as `jp-ru-kolobok-400k-v1.0.1-yomitan.zip`.

YRP-V3A-5 — Do not publish old `jitendex-articles-*` build names as current user downloads. They may remain local historical artifacts.

YRP-V3A-6 — Update the project site, structured data, download buttons, release links, sizes, version text, and latest-release link to v1.0.1.

YRP-V3A-7 — Update README current-state IDs with new export IDs, hashes, compilation time, filenames, and release tag. Do not renumber existing IDs; add new IDs.

YRP-V3A-8 — Add a new immutable history section to `JPDB_LUNA_RUN_HISTORY.md` with the incident, repair design, database backup hash, canonicalization report hash, export IDs, archive hashes, tests, smoke results, and publication URLs.

## YRP-V3B — Preserve required Jitendex attribution

YRP-V3B-1 — Keep `Jitendex` in the description that states Kolobok is a derivative Russian dictionary based on Jitendex.

YRP-V3B-2 — Keep Stephen Kraus in the author field and keep Yuri Katkov as co-author of the Russian edition.

YRP-V3B-3 — Keep the upstream Jitendex, JMdict, and Tatoeba license and attribution text.

YRP-V3B-4 — Keep `JMdict` and `Tatoeba` article attribution labels and their source links.

YRP-V3B-5 — Keep internal resource paths such as `jitendex/graphics/...` and `jitendex/HanaMinA/...` unless a separate migration proves every reference can be rewritten safely. These paths are resource namespaces, not update identity.

YRP-V3B-6 — Keep source acquisition configuration for the pinned upstream `jitendex-yomitan.zip`. It is an input source and must not be confused with the output download URL.

YRP-V3B-7 — Keep internal Python package and database names such as `jitendex_ru`, `jitendex_snapshot_id`, and `jitendex_tag`. Renaming them is unrelated archaeology and is outside this release.

YRP-V3B-8 — Keep comparison-site labels such as `Original Jitendex (English)` where the page really compares source Jitendex with Kolobok.

## YRP-CODE — Planned code changes

YRP-CODE-1 — Add a dedicated structured-text localization module or extend `apply_translations.py` with tested deterministic rules for redirects and form restrictions.

YRP-CODE-2 — Add export counters and independent V1 verification to `build_dictionary.py`.

YRP-CODE-3 — Add the visible-text audit command and report writer under `src/jitendex_ru/` and expose it through `translationctl`.

YRP-CODE-4 — Add mixed-alphabet and role-aware English validation to `validate_response.py`.

YRP-CODE-5 — Extend `canonicalize.py` to consume the approved v1.0.1 remediation manifest and write immutable history.

YRP-CODE-6 — Split stable Yomitan title from versioned native-format titles in `attribution.py` or a new release metadata module.

YRP-CODE-7 — Make Yomitan metadata generation explicit. Do not copy operational update fields from upstream `index.json`.

YRP-CODE-8 — Add generation and validation of the hosted Kolobok `yomitan.json` update index.

YRP-CODE-9 — Add tests to `tests/test_pipeline.py`, `tests/test_validate_response.py`, `tests/test_canonicalize.py`, and focused new test files as needed.

YRP-CODE-10 — Update README, the Luna run history, the public site, and the Pages workflow inputs without changing prompt provenance under `prompts/`.

## YRP-TEST — Required automated tests

YRP-TEST-1 — Test one normal redirect, one compatibility-ideograph redirect, one kana redirect, one numeric redirect, and one fullwidth-Latin redirect.

YRP-TEST-2 — Test the exact long restriction tooltip.

YRP-TEST-3 — Test Japanese, numeric, Greek, and fullwidth-Latin `<form> only` restrictions.

YRP-TEST-4 — Test that `read-only member`, `download-only member`, and `IF-AND-ONLY-IF` are unchanged.

YRP-TEST-5 — Test that the deterministic localization pass is idempotent.

YRP-TEST-6 — Test that the verifier rejects every raw V1 template.

YRP-TEST-7 — Test that adjacent mixed alphabets fail validation while `JIT-компилятор` and `3D-принтер` pass.

YRP-TEST-8 — Test protected brands, taxa, acronyms, URLs, grammar quotations, and source-language quotations.

YRP-TEST-9 — Test remediation manifest identity, previous hash, immutable history, duplicate rejection, and second-run zero changes.

YRP-TEST-10 — Test the stable Yomitan title and independent monotonic revision.

YRP-TEST-11 — Test that operational metadata rejects Jitendex update URLs but permits Jitendex in attribution and description.

YRP-TEST-12 — Test that the hosted index and archive metadata agree.

YRP-TEST-13 — Test that all eight visible tag-bank rows remain exactly Russian while their category codes remain unchanged.

YRP-TEST-14 — Run the full project test suite and require only documented existing skips.

## YRP-DATA — Production data procedure

YRP-DATA-1 — Stop all translation and review workers before the first production write.

YRP-DATA-2 — Resolve and export the authoritative PostgreSQL URL. Confirm Docker's published port rather than assuming port 5432.

YRP-DATA-3 — Create a PostgreSQL backup before importing the approved remediation manifest.

YRP-DATA-4 — Validate the backup, compute its SHA-256, and record its path and hash in the run history.

YRP-DATA-5 — Generate the pre-change audit report from Run 59 and require the documented baseline counts.

YRP-DATA-6 — Run Luna semantic review only on the audit queue that needs judgment.

YRP-DATA-7 — Approve the final remediation manifest and compute its SHA-256.

YRP-DATA-8 — Apply the remediation canonicalizer in one transaction.

YRP-DATA-9 — Run the canonicalizer again and require zero changes.

YRP-DATA-10 — Run Run 59 integrity and source-identity reports. Require the same article scope, source hashes, unit count, and accepted coverage except for approved target hashes.

YRP-DATA-11 — Run validation and require zero unresolved blocking issues.

YRP-DATA-12 — Generate a post-change audit report and require zero mixed-alphabet defects in translated roles.

## YRP-VERSION — Release identity update

YRP-VERSION-1 — Set `DICTIONARY_VERSION` to `1.0.1`.

YRP-VERSION-2 — Set `COMPILATION_DATETIME_UTC` once, after content and code are frozen and before final reproducibility builds.

YRP-VERSION-3 — Keep `PRODUCT_ID` as `jp-ru-kolobok-400k` and `PRODUCT_NAME` as `Колобок 400k`.

YRP-VERSION-4 — Use `jp-ru-kolobok-400k-v1.0.1` as the versioned base filename for release archives and native-format payloads.

YRP-VERSION-5 — Use stable `Колобок 400k` as the Yomitan installed title.

YRP-VERSION-6 — Generate the independent release revision and hosted update index from the frozen release metadata.

YRP-VERSION-7 — Use a new release tag. The recommended tag is `v1.0.1` unless repository release policy chooses a run-qualified tag before implementation starts.

## YRP-BUILD — Rebuild all five formats

YRP-BUILD-1 — Build from the authoritative Run 59 database after approved canonicalization. Do not overwrite v1.0 artifacts.

YRP-BUILD-2 — Export Yomitan to `dist/jp-ru-kolobok-400k-v1.0.1-yomitan.zip` and run `translationctl verify` against it.

YRP-BUILD-3 — Export GoldenDict to `dist/jp-ru-kolobok-400k-v1.0.1-goldendict.zip` and run `verify-goldendict`.

YRP-BUILD-4 — Export MDict to `dist/jp-ru-kolobok-400k-v1.0.1-mdict.zip` and run `verify-mdict`.

YRP-BUILD-5 — Export PocketBook to `dist/jp-ru-kolobok-400k-v1.0.1-pocketbook.zip` with the pinned compiler and language directory, then run `verify-pocketbook`.

YRP-BUILD-6 — Export Apple Dictionary to `dist/jp-ru-kolobok-400k-v1.0.1-apple-dictionary.zip` with the pinned DDK tool and schema hashes, then run `verify-apple-dictionary`.

YRP-BUILD-7 — Run the V1 lexical scanner against the Yomitan archive and against every rich exporter that renders the same accepted text.

YRP-BUILD-8 — Record every export ID, file count, article count, loss ledger result, SHA-256, build time, and verifier result.

YRP-BUILD-9 — Build all five archives a second time to new temporary paths and require byte-for-byte identical SHA-256 values.

## YRP-SMOKE — Client and update smoke gates

YRP-SMOKE-1 — Import v1.0.1 into a clean Yomitan profile.

YRP-SMOKE-2 — Check expression, reading, inflected, kana-only, multiple-reading, cross-reference, ruby, example, table, link, and long-entry rendering.

YRP-SMOKE-3 — Check a redirect entry including `社会情報學` and confirm the Russian redirect label.

YRP-SMOKE-4 — Check numeric, Greek, and fullwidth-Latin restriction entries and confirm the Russian label and tooltip.

YRP-SMOKE-5 — Check entries that retain JMdict, Tatoeba, brands, taxa, acronyms, quoted English grammar, and source-language forms.

YRP-SMOKE-6 — Check representative repaired mixed-alphabet entries, including the former `losили` example.

YRP-SMOKE-7 — Record the clean-profile smoke report with `record-yomitan-smoke` and the release actor.

YRP-SMOKE-8 — Install an older test Kolobok archive with the stable title, point it to a staged owned update index, and run Yomitan's update check.

YRP-SMOKE-9 — Confirm that the update downloads the Kolobok v1.0.1 asset, keeps Russian target metadata, preserves profile dictionary settings, and does not install Jitendex.

YRP-SMOKE-10 — Fetch every final release asset into a clean temporary directory and rerun hash checks and format verifiers where practical.

## YRP-DOC — Documentation before publication

YRP-DOC-1 — Add a new run-history section for the V1–V3 incident and v1.0.1 remediation. Never rewrite the v1.0 history.

YRP-DOC-2 — Record the exact old metadata, the Yomitan update behavior, and the fact that v1.0 cannot be repaired through its own update button.

YRP-DOC-3 — Record the before-and-after V1 counts and the approved remediation manifest hash.

YRP-DOC-4 — Record the database backup hash, canonicalization history count, export IDs, archive hashes, test results, smoke actor, and update test.

YRP-DOC-5 — Add new README state IDs for v1.0.1. Do not renumber v1.0 IDs.

YRP-DOC-6 — Update the public home page to v1.0.1 filenames, sizes, release URL, version, and manual upgrade warning.

YRP-DOC-7 — Add a visible warning that v1.0 users must not use its update button and must manually install v1.0.1.

YRP-DOC-8 — Write release notes in Russian and English. Explain the redirect and tooltip localization, mixed-alphabet repairs, stable title, owned updater, preserved attribution, and manual upgrade requirement.

YRP-DOC-9 — State clearly that Jitendex, JMdict, Tatoeba, creator names, scientific names, brands, and license identifiers intentionally remain.

## YRP-COMMIT — Main branch change control

YRP-COMMIT-1 — Perform this work directly on `main` as requested.

YRP-COMMIT-2 — Preserve unrelated user files and ignore `.idea/` unless the user separately requests it.

YRP-COMMIT-3 — Review `git diff`, generated reports, database audit output, and archive hashes before every commit.

YRP-COMMIT-4 — Use intent-based commits that explain why the change exists and its impact. One acceptable sequence is code and tests, approved remediation data, release identity and metadata, documentation and site, then publication metadata.

YRP-COMMIT-5 — Do not commit production database dumps, secrets, temporary Luna payloads, or unreviewed generated candidates.

## YRP-CMD — Reproducible command templates

YRP-CMD-1 — Resolve these values from the frozen release state before running production commands. Do not guess the PostgreSQL port, run ID, external tool path, or hash.

```sh
export KOL_RUN_ID=59
export KOL_RELEASE_VERSION=1.0.1
export KOL_RELEASE_TAG=v1.0.1
: "${JITENDEX_POSTGRES_URL:?set through the existing approved secret setup}"
```

YRP-CMD-2 — Replace the illustrative secret-resolution command above with the existing approved environment setup. Never put the database URL in the plan, Git history, shell history, or a report.

YRP-CMD-3 — Create and validate the pre-change PostgreSQL backup using an explicit path under `work/backups/`.

```sh
pg_dump --format=custom --no-owner --no-privileges \
  --dbname "$JITENDEX_POSTGRES_URL" \
  --file "work/backups/jitendex-postgresql-before-yomitan-v1.0.1.dump"

pg_restore --list \
  "work/backups/jitendex-postgresql-before-yomitan-v1.0.1.dump" >/dev/null

shasum -a 256 \
  "work/backups/jitendex-postgresql-before-yomitan-v1.0.1.dump"
```

YRP-CMD-4 — Run the new pre-change localization audit and save its JSON report. The exact command name may change during implementation, but it must be a first-class `translationctl` command rather than an ad hoc release script.

```sh
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  audit-yomitan-localization --run-id "$KOL_RUN_ID" \
  --output "reports/yomitan_localization/run59-v1.0.1-before.json"
```

YRP-CMD-5 — Apply the approved remediation manifest through the extended canonicalizer, then run it a second time to prove idempotence.

```sh
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  canonicalize-final-run --run-id "$KOL_RUN_ID" \
  --remediation-manifest \
  "terminology/yomitan-v1.0.1-approved-remediation.json"

PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  canonicalize-final-run --run-id "$KOL_RUN_ID" \
  --remediation-manifest \
  "terminology/yomitan-v1.0.1-approved-remediation.json"
```

YRP-CMD-6 — `--remediation-manifest` is implemented and tested. Do not run the production templates until the approved manifest exists, workers are stopped, and the backup and integrity gates in YRP-DATA are complete.

YRP-CMD-6A — The implemented database-free command below reproduces the v1.0 archive baseline without opening the production database. It is an evidence step, not a replacement for YRP-CMD-4.

```sh
PYTHONPATH=src .venv/bin/translationctl \
  audit-yomitan-archive \
  dist/jp-ru-kolobok-400k-v1.0-yomitan.zip \
  --run-id 59 \
  --output reports/yomitan_localization/run59-v1.0-before.json
```

YRP-CMD-7 — Validate the authoritative run and execute the full automated test suite before building release archives.

```sh
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  validate --run-id "$KOL_RUN_ID"

PYTHONPATH=src .venv/bin/pytest -q
```

YRP-CMD-8 — Build and verify the Yomitan archive.

```sh
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  build --run-id "$KOL_RUN_ID" \
  --output "dist/jp-ru-kolobok-400k-v1.0.1-yomitan.zip"

PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  verify "dist/jp-ru-kolobok-400k-v1.0.1-yomitan.zip"
```

YRP-CMD-9 — Build and verify GoldenDict and MDict.

```sh
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  export-goldendict --run-id "$KOL_RUN_ID" \
  --output "dist/jp-ru-kolobok-400k-v1.0.1-goldendict.zip"

PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  verify-goldendict \
  "dist/jp-ru-kolobok-400k-v1.0.1-goldendict.zip"

PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  export-mdict --run-id "$KOL_RUN_ID" \
  --output "dist/jp-ru-kolobok-400k-v1.0.1-mdict.zip"

PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  verify-mdict "dist/jp-ru-kolobok-400k-v1.0.1-mdict.zip"
```

YRP-CMD-10 — Build and verify PocketBook with the existing pinned external compiler and language directory.

```sh
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  export-pocketbook --run-id "$KOL_RUN_ID" \
  --output "dist/jp-ru-kolobok-400k-v1.0.1-pocketbook.zip" \
  --compiler "$KOL_POCKETBOOK_COMPILER" \
  --compiler-sha256 "$KOL_POCKETBOOK_COMPILER_SHA256" \
  --language-dir "$KOL_POCKETBOOK_LANGUAGE_DIR"

PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  verify-pocketbook \
  "dist/jp-ru-kolobok-400k-v1.0.1-pocketbook.zip"
```

YRP-CMD-11 — Build and verify Apple Dictionary with the existing pinned DDK tool and schema.

```sh
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  export-apple-dictionary --run-id "$KOL_RUN_ID" \
  --output "dist/jp-ru-kolobok-400k-v1.0.1-apple-dictionary.zip" \
  --build-tool "$KOL_APPLE_BUILD_TOOL" \
  --build-tool-sha256 "$KOL_APPLE_BUILD_TOOL_SHA256" \
  --schema "$KOL_APPLE_SCHEMA" \
  --schema-sha256 "$KOL_APPLE_SCHEMA_SHA256"

PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  verify-apple-dictionary \
  "dist/jp-ru-kolobok-400k-v1.0.1-apple-dictionary.zip"
```

YRP-CMD-12 — Create one release checksum file from explicit v1.0.1 targets.

```sh
shasum -a 256 \
  dist/jp-ru-kolobok-400k-v1.0.1-yomitan.zip \
  dist/jp-ru-kolobok-400k-v1.0.1-goldendict.zip \
  dist/jp-ru-kolobok-400k-v1.0.1-mdict.zip \
  dist/jp-ru-kolobok-400k-v1.0.1-pocketbook.zip \
  dist/jp-ru-kolobok-400k-v1.0.1-apple-dictionary.zip \
  > dist/jp-ru-kolobok-400k-v1.0.1-SHA256SUMS.txt
```

YRP-CMD-13 — Record the Yomitan smoke report only after its ZIP hash matches a verified export record.

```sh
PYTHONPATH=src .venv/bin/translationctl --config config.luna.toml \
  record-yomitan-smoke \
  "reports/yomitan_localization/run59-v1.0.1-smoke.json" \
  --actor "$KOL_SMOKE_ACTOR"
```

YRP-CMD-14 — Create the draft release and upload only explicit v1.0.1 artifacts. Run this only after all local gates pass.

```sh
gh release create "$KOL_RELEASE_TAG" \
  --draft \
  --title "Колобок 400k v1.0.1" \
  --notes-file "reports/yomitan_localization/v1.0.1-release-notes.md"

gh release upload "$KOL_RELEASE_TAG" \
  dist/jp-ru-kolobok-400k-v1.0.1-yomitan.zip \
  dist/jp-ru-kolobok-400k-v1.0.1-goldendict.zip \
  dist/jp-ru-kolobok-400k-v1.0.1-mdict.zip \
  dist/jp-ru-kolobok-400k-v1.0.1-pocketbook.zip \
  dist/jp-ru-kolobok-400k-v1.0.1-apple-dictionary.zip \
  dist/jp-ru-kolobok-400k-v1.0.1-SHA256SUMS.txt
```

YRP-CMD-15 — Download draft assets to a newly created explicit temporary directory and compare their hashes before publication. Do not reuse a directory containing older releases.

## YRP-PUB — Publish version 1.0.1

YRP-PUB-1 — Require every YRP-TEST, YRP-DATA, YRP-BUILD, YRP-SMOKE, and YRP-DOC gate to pass before creating a public release.

YRP-PUB-2 — Create the v1.0.1 GitHub release as a draft from the frozen `main` commit.

YRP-PUB-3 — Upload the five versioned archives, their SHA-256 manifest, the localization audit summary, and any required installation notes to the draft release.

YRP-PUB-4 — Download every draft asset with GitHub tooling and require exact agreement with the locally verified SHA-256 manifest.

YRP-PUB-5 — Stage the public `yomitan.json` with the final revision and final owned download URL. Validate it against the pinned schema and compare it with the Yomitan archive metadata.

YRP-PUB-6 — Stage the site-home changes with the v1.0.1 download links and manual-upgrade warning.

YRP-PUB-7 — Confirm that no public page or operational metadata field points Kolobok users to the Jitendex update index or Jitendex download asset.

YRP-PUB-8 — Publish the GitHub v1.0.1 release from draft.

YRP-PUB-9 — Push the frozen site and update-index commit to `main`, wait for the Pages workflow to succeed, and verify the public project page, owned `yomitan.json`, release links, and archive hash.

YRP-PUB-DONE-1 — Version 1.0.1 is published only when the public Kolobok page serves the new downloads, the owned update index names the same verified Yomitan archive, and users can no longer be directed to English Jitendex by Kolobok metadata.
