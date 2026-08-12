# F20P — Frequency top-40k translation plan

F20P-1 — This plan adds every Jitendex term found in the rank-40,000-or-better scope of any of six frequency dictionaries. It follows the Luna procedure in [JPDB_LUNA_ORCHESTRATION_RUNBOOK.md](JPDB_LUNA_ORCHESTRATION_RUNBOOK.md).

F20P-2 — The run must be cumulative. It must keep the latest verified JPDB scope, add the six-list union, reuse accepted translations, translate only the remaining units, and produce a verified Yomitan archive.

## F20P-DEC — Scope decision

F20P-DEC-1 — This is a one-off combined export. It keeps the verified JPDB top-190k scope and adds the six-list top-40k union only for this run.

F20P-DEC-2 — After the combined archive is verified, resume the normal JPDB-only sequence at top 200k. Do not keep the six-list overlay in later exports.

## F20P-BASE — Current baseline

F20P-BASE-1 — The current verified source is JPDB top 190k, run 24. Its archive is `dist/jitendex-jpdb-190k-ru-luna-v4.zip` with SHA-256 `8d632ea386915467eb6813b9c3aeba6bd665dbb6af2142ff247a2c607f6ae2e0`.

F20P-BASE-2 — The six rank-limited sets contain 103,536 distinct exact headword strings. Against the top-190k Russian export, 62,334 are present in Russian, 9,591 occur in source Jitendex but not in that export, and 31,611 do not occur as Jitendex expressions.

F20P-BASE-3 — The 9,591 value is an estimate, not the run target. The normal selector matches each spelling against both Jitendex expressions and readings. It can therefore select more articles than the expression-only analysis.

F20P-BASE-4 — The target run must include every matching article. It must not pre-filter articles by whether one homograph is already present in the Russian archive. `reuse-translations` is the only mechanism used to remove already completed work.

## F20P-IN — Pinned inputs

F20P-IN-1 — Pin source Jitendex SHA-256 `807d911114af9d2154d270702972aafb2b6a6c2dc2400afa98db870d035c1a0b` and the JPDB source already pinned by the runbook.

F20P-IN-2 — Pin Aozora Bunko SHA-256 `116009c3034d97a16b257fda10f2138067815986c954bffbb5c93aad60faa867`. Its rank-40,000-or-better scope has 40,156 unique headwords because rank ties are retained.

F20P-IN-3 — Pin BCCWJ SHA-256 `4a0f79b88b3934d2cfca6ec1018c0658c7af6e27bf5eaa371db554e0cb3c1693`. Its scope has 38,898 unique headwords because its recorded ranks have gaps.

F20P-IN-4 — Pin CC100 SHA-256 `64f2a7d79e42dc842a30697e36f8b4f77dbcb3c6ff7fd1feec756b1fe65396e0`. Its scope has 39,319 unique headwords after reading variants are collapsed to exact headword strings.

F20P-IN-5 — Pin Monodicts 206k SHA-256 `932a65a0661c1c040b471a03aa9e11eb20a2ab6f42b62ffbf1dab568db7d8b39`. Its scope has 40,000 unique headwords.

F20P-IN-6 — Pin Wikipedia v2 SHA-256 `d85bb5bb4cdb3277dd862d662ec5e8e87971457ac53a87c2f25b41446c57d6c8`. Its scope has 40,000 unique headwords.

F20P-IN-7 — Pin 国語辞典 SHA-256 `ac267dd5756363fd2b9d0bfd64f89d86d2b9c90f833f3273375173791080c32c`. Its scope has 40,000 unique headwords.

F20P-IN-8 — Keep Luna model `gpt-5.6-luna`, reasoning effort `medium`, configuration `config.luna.toml`, prompt `prompts/translate_luna_v4.txt`, extractor `extractor-v2`, and pipeline `lexicographer-v2` unchanged.

## F20P-IMPL — Required selector work

F20P-IMPL-1 — Implement one combined selector before touching the live selection. The proposed CLI is `select-combined-frequency-scope`. It must accept the pinned JPDB ZIP and limit plus the six external ZIPs and their common rank limit.

F20P-IMPL-2 — Read every `term_meta_bank_N.json` member. Accept numeric ranks stored directly or in `frequency` or `value`. Normalize terms to NFC. Keep every record whose recorded rank is from 1 through 40,000. Within one source, keep the best rank for duplicate terms.

F20P-IMPL-3 — Store the seven sources under stable source keys: `jpdb`, `aozora_bunko`, `bccwj`, `cc100`, `monodicts_206k`, `wikipedia_v2`, and `kokugo_jiten`. Record each source hash and every retained term in `frequency_term`.

F20P-IMPL-4 — Match each normalized term to every Jitendex article with the same normalized expression or reading. Record every mapping in `frequency_article` with `match_kind` equal to `expression` or `reading`.

F20P-IMPL-5 — Set `article.selected=1` for the union of the JPDB scope and all six external scopes. Never select frozen base-run articles merely by ID. Re-derive the complete selection from the pinned sources and prove that it contains every source-run article.

F20P-IMPL-6 — Include the seven source keys, seven hashes, limits, normalized terms, mappings, and selected article fingerprints in `selection_sha256`. Two identical article sets reached from different frequency inputs must not share a run identity.

F20P-IMPL-7 — Add `report-combined-frequency-coverage`. It must report per-source terms, the distinct cross-source union, matched and skipped terms, mapped articles, fully accepted articles, and whether every mapped article is frozen in the target run.

F20P-IMPL-8 — Update export metadata so the title, revision, and description say `JPDB 190k + frequency-six top40k` instead of the old hardcoded JPDB 5k label.

F20P-IMPL-9 — Add tests for every rank representation, tied ranks, rank gaps, multiple bank files, duplicate terms, NFC normalization, expression matches, reading matches, cross-source duplicates, combined selection hashing, cumulative base inclusion, coverage, and export metadata.

F20P-IMPL-10 — Do not start the run until the full test suite passes and the selector dry run produces the expected 103,536-term six-list union.

## F20P-PRE — Preflight

F20P-PRE-1 — Run from the repository root and set the normal environment.

~~~bash
export PYTHONPATH=src
export UV_CACHE_DIR=/private/tmp/jitendex-uv-cache
export F20_SOURCE_RUN_ID=24
export F20_JPDB_LIMIT=190000
export F20_FREQ_LIMIT=40000
export F20_SCOPE_LABEL=jpdb-190k-plus-freq6-top40k
~~~

F20P-PRE-2 — Confirm run 24 has complete coverage and a verified export before replacing the live frequency tables.

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.toml \
  report-jpdb-coverage --run-id "$F20_SOURCE_RUN_ID"

sqlite3 -header -column work/progress.sqlite3 "
SELECT id,run_id,output_path,zip_sha256,verified
FROM export WHERE run_id=$F20_SOURCE_RUN_ID ORDER BY id DESC LIMIT 1;
"
~~~

F20P-PRE-3 — Require `complete: true`, `verified=1`, and the pinned top-190k archive hash. Stop on any mismatch.

F20P-PRE-4 — Verify the seven frequency archive hashes. Save the command output with the run evidence.

~~~bash
shasum -a 256 \
  work/downloads/Freq.JPDB_2022-05-10T03_27_02.930Z.zip \
  '/Users/iuriikatkov/Documents/_japanese/yomichan/shoui Yomichan Dictionaries Collection [learnjapanese.moe]/Frequency/[Freq] Aozora Bunko.zip' \
  '/Users/iuriikatkov/Documents/_japanese/yomichan/shoui Yomichan Dictionaries Collection [learnjapanese.moe]/Frequency/[Freq] BCCWJ.zip' \
  '/Users/iuriikatkov/Documents/_japanese/yomichan/shoui Yomichan Dictionaries Collection [learnjapanese.moe]/Frequency/[Freq] CC100.zip' \
  '/Users/iuriikatkov/Documents/_japanese/yomichan/shoui Yomichan Dictionaries Collection [learnjapanese.moe]/Frequency/[Freq] Monodicts 206k.zip' \
  '/Users/iuriikatkov/Documents/_japanese/yomichan/shoui Yomichan Dictionaries Collection [learnjapanese.moe]/Frequency/[Freq] Wikipedia v2.zip' \
  '/Users/iuriikatkov/Documents/_japanese/yomichan/shoui Yomichan Dictionaries Collection [learnjapanese.moe]/Frequency/[Freq] 国語辞典.zip'
~~~

F20P-PRE-5 — Regenerate the expression-only estimate against the source export. This is a sanity check, not the selection command.

~~~bash
python3 tools_analyze_frequency_coverage.py \
  --russian dist/jitendex-jpdb-190k-ru-luna-v4.zip \
  --limit 40000 \
  --output /tmp/frequency-analysis-top40k-top190.js
~~~

F20P-PRE-6 — Require 103,536 union headwords, 62,334 already Russian, 9,591 estimated translation gaps, and 31,611 absent expressions.

## F20P-SEL — Build the combined selection

F20P-SEL-1 — The command below is proposed and is not runnable until F20P-IMPL is complete.

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.toml \
  select-combined-frequency-scope \
  --jpdb work/downloads/Freq.JPDB_2022-05-10T03_27_02.930Z.zip \
  --jpdb-limit "$F20_JPDB_LIMIT" \
  --frequency-limit "$F20_FREQ_LIMIT" \
  --aozora '/Users/iuriikatkov/Documents/_japanese/yomichan/shoui Yomichan Dictionaries Collection [learnjapanese.moe]/Frequency/[Freq] Aozora Bunko.zip' \
  --bccwj '/Users/iuriikatkov/Documents/_japanese/yomichan/shoui Yomichan Dictionaries Collection [learnjapanese.moe]/Frequency/[Freq] BCCWJ.zip' \
  --cc100 '/Users/iuriikatkov/Documents/_japanese/yomichan/shoui Yomichan Dictionaries Collection [learnjapanese.moe]/Frequency/[Freq] CC100.zip' \
  --monodicts '/Users/iuriikatkov/Documents/_japanese/yomichan/shoui Yomichan Dictionaries Collection [learnjapanese.moe]/Frequency/[Freq] Monodicts 206k.zip' \
  --wikipedia '/Users/iuriikatkov/Documents/_japanese/yomichan/shoui Yomichan Dictionaries Collection [learnjapanese.moe]/Frequency/[Freq] Wikipedia v2.zip' \
  --kokugo '/Users/iuriikatkov/Documents/_japanese/yomichan/shoui Yomichan Dictionaries Collection [learnjapanese.moe]/Frequency/[Freq] 国語辞典.zip'
~~~

F20P-SEL-2 — Require the six per-source unique counts in F20P-IN and a distinct six-source union of 103,536. JPDB counts must equal the verified runbook top-190k inputs.

F20P-SEL-3 — Record the number of union terms matched by expression, matched only by reading, and skipped. Do not treat the 31,611 expression-only absences as the final skip count because some can match Jitendex readings.

F20P-SEL-4 — Before extraction, require zero selected articles missing from run 24.

~~~bash
sqlite3 -header -column work/progress.sqlite3 "
SELECT COUNT(*) source_articles_missing_from_selection
FROM run_article ra
JOIN article a ON a.id=ra.article_id
WHERE ra.run_id=$F20_SOURCE_RUN_ID AND a.selected<>1;
"
~~~

## F20P-RUN — Create and translate the run

F20P-RUN-1 — Extract units and store the returned run ID.

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.toml extract-units

export F20_RUN_ID='<RETURNED_RUN_ID>'
~~~

F20P-RUN-2 — Require zero source units missing from the target run. Use the cumulative gate from RUN-BATCH-S3 with `F20_SOURCE_RUN_ID` and `F20_RUN_ID`.

F20P-RUN-3 — Reuse all compatible accepted translations from run 24.

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.toml \
  reuse-translations \
  --source-run-id "$F20_SOURCE_RUN_ID" \
  --target-run-id "$F20_RUN_ID"
~~~

F20P-RUN-4 — Record total units, reused accepted units, ready units, new articles, and estimated batch count. Ready units are the actual Luna workload.

F20P-RUN-5 — Create normal Luna batches.

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.toml \
  make-batches --run-id "$F20_RUN_ID"
~~~

F20P-RUN-6 — Start four pools with concurrency 20. Use worker prefixes `freq6top40k-pool1` through `freq6top40k-pool4`.

~~~bash
python scripts/run_codex_batches.py \
  --config config.luna.toml \
  --run-id "$F20_RUN_ID" \
  --kind translation \
  --concurrency 20 \
  --worker-prefix 'freq6top40k-pool1'
~~~

F20P-RUN-7 — Follow RUN-BATCH-S7 through RUN-BATCH-S9 without changes. Monitor authoritative database state, allow automatic retry and split isolation, repair only genuine validation failures, and require zero unfinished batches, zero terminal blocked leaves, zero unresolved errors, and zero ready units.

F20P-RUN-8 — Accept deterministic translations only after the drain gate passes.

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.toml \
  accept-translations --run-id "$F20_RUN_ID"
~~~

F20P-RUN-9 — Require exactly one accepted translation for every target unit using the SQL gate from RUN-BATCH-S10.

## F20P-COV — Combined coverage gate

F20P-COV-1 — Run the new combined coverage report.

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.toml \
  report-combined-frequency-coverage --run-id "$F20_RUN_ID"
~~~

F20P-COV-2 — Require `complete: true`, all run-24 articles present, every matched union term covered, every mapped article frozen in the run, every target article fully accepted, and unmatched terms reported as intentional skips.

F20P-COV-3 — Require zero accepted-translation gaps and zero unresolved blocking validation issues.

## F20P-REL — Build and verify

F20P-REL-1 — Build the cumulative archive with scope-aware metadata.

~~~bash
PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.toml \
  build \
  --run-id "$F20_RUN_ID" \
  --output "dist/jitendex-${F20_SCOPE_LABEL}-ru-luna-v4.zip"

PYTHONPATH=src .venv/bin/translationctl \
  --config config.luna.toml \
  verify "dist/jitendex-${F20_SCOPE_LABEL}-ru-luna-v4.zip"
~~~

F20P-REL-2 — Run the full test suite, `translationctl validate`, the database audit from RUN-BATCH-S13, and `shasum -a 256` on the archive.

F20P-REL-3 — Open the archive index and require the combined scope in its title, revision, and description. Require the recorded export row to have `verified=1`.

F20P-REL-4 — Append the final source hashes, selection counts, run ID, unit counts, reuse counts, repair incidents, archive hash, and verification result to [JPDB_LUNA_RUN_HISTORY.md](JPDB_LUNA_RUN_HISTORY.md). Keep the runbook JPDB stopping point at top 190k because this supplemental run does not advance the JPDB rank sequence.

## F20P-FUT — Resume JPDB-only runs

F20P-FUT-1 — After the one-off archive is verified, select the normal JPDB top-200k scope with `select-jpdb-scope`. This intentionally removes overlay-only articles from the live selection and from the next export.

F20P-FUT-2 — Use run 24 as the primary cumulative source for the top-200k containment gate. Reuse run 24 first so the normal JPDB top-190k baseline is preserved.

F20P-FUT-3 — After reusing run 24, call `reuse-translations` a second time with this one-off run as the source. This safely reuses any overlay translation that has entered JPDB top 200k, while target units outside JPDB remain absent.

F20P-FUT-4 — Once top 200k is verified, return to the normal single-source JPDB progression. Record the optional second reuse in the top-200k history, but do not change the runbook selector or coverage command to the combined versions.

## F20P-SAFE — Safety and recovery

F20P-SAFE-1 — The combined selector replaces live frequency tables and `article.selected`. Frozen prior runs remain safe through `run_article`, but capture the source coverage report before selection.

F20P-SAFE-2 — If selection or extraction fails before dispatch, fix the implementation, rerun the deterministic selector, and confirm the same selection hash. Do not edit frequency rows or selected flags manually.

F20P-SAFE-3 — If translation fails after dispatch, preserve attempts and responses. Use the normal retry, split, revalidation, and audited repair procedure. Never insert accepted translations directly.

## F20P-DONE — Completion criteria

F20P-DONE-1 — The plan is complete only when the combined selector and coverage report are tested, the six-list union is pinned and reproducible, the target includes every source-run article, all compatible translations are reused, all remaining units have exactly one accepted translation, all blocking gates are zero, and the combined Yomitan archive is verified.

F20P-DONE-2 — The one-off work is complete when its archive is verified, its history is recorded, and the runbook still points to JPDB top 200k as the next normal scope.
