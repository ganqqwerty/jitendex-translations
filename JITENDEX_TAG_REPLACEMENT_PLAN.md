# TAG — Plan for Replacing Russian Jitendex Tags

## TAG-SRC — Source of truth

TAG-SRC-1 — `terminology/jitendex-tags-ru.csv` is the exact source of truth for all 236
Russian tag names and tooltips. Luna must not overwrite these translations.

TAG-SRC-2 — We will keep old Luna translations in the database for history, but they will no
longer affect exported dictionaries.

## TAG-WHY — Why we need a full replacement

TAG-WHY-1 — The same English tag was translated by the LLM many times in different articles.
This created many Russian versions of the same tag.

TAG-WHY-2 — We cannot find tags by looking at their current Russian text. Instead, we will use
the original Jitendex tag code and category, such as:

TAG-WHY-3 — category: `part-of-speech-info`

TAG-WHY-4 — code: `v1`

TAG-WHY-5 — This information does not change when the visible text is translated.

## TAG-DONE — Already done

TAG-DONE-1 — Matched all 236 spreadsheet rows with the original Jitendex tags.

TAG-DONE-2 — Put all approved translations into `jitendex_tag`.

TAG-DONE-3 — Saved the spreadsheet path and SHA-256 in the database.

TAG-DONE-4 — Saved the previous Luna translations in `jitendex_tag_translation_history`.

TAG-DONE-5 — Prevented Luna from overwriting approved rows.

TAG-DONE-6 — Created a backup of the database from before the import.

## TAG-BUILD — Approved tags in dictionary builds

TAG-BUILD-1 — Load the approved tags for the Jitendex version used by the build.

TAG-BUILD-2 — Stop the build if any tag is missing or has more than one match.

TAG-BUILD-3 — Find every tag in an article using its original category and code.

TAG-BUILD-4 — Replace its visible name with the approved `label_ru`.

TAG-BUILD-5 — Replace its tooltip with the approved `description_ru`.

TAG-BUILD-6 — Do the same for tags stored in `tag_bank_*.json`.

TAG-BUILD-7 — Replace every old LLM version, even when it already looks correct.

TAG-BUILD-8 — We will do this while building the dictionary. We will not rewrite old translation
runs, attempts, or reviews. This keeps the history intact.

## TAG-OLD — Old tag source retired

TAG-OLD-1 — The new build logic is tested and active for Yomitan and GoldenDict.

TAG-OLD-2 — Stop reading tag translations from `terminology/tag-bank-ru-v1.json`.

TAG-OLD-3 — Use only the approved database table.

TAG-OLD-4 — Old Luna tag text remains immutable history and cannot affect an export.

TAG-OLD-5 — The Luna runbook explains the PostgreSQL approved-catalog process.

## TAG-TEST — Release verification

TAG-TEST-1 — Test normal tags, tags without a code, and `tag_bank` tags.

TAG-TEST-2 — Test that a missing or duplicate approved tag stops the build.

TAG-TEST-3 — Run 59 produced new Yomitan and GoldenDict archives without overwriting export
65.

TAG-TEST-4 — Check every exported tag against the approved database table.

TAG-TEST-5 — The Run 59 report records per-tag occurrences and historical variants at
`reports/jitendex_tags/run59-tag-unification.json`.

TAG-TEST-6 — All 140 project tests passed, with two expected PostgreSQL integration skips.
The Yomitan schema and both independent archive verifiers passed.

TAG-TEST-7 — The before-and-after report has zero missing mappings and records the catalog
SHA-256 and all tag-bank reference rewrites.

TAG-TEST-8 — A clean-profile Yomitan import and hover check remains a manual release gate
because automated browser control cannot open extension settings.

## TAG-COMPLETE — Completion state

TAG-COMPLETE-1 — Every exported tag exactly matches the approved spreadsheet.

TAG-COMPLETE-2 — Old LLM wording cannot affect the output.

TAG-COMPLETE-3 — Missing or unclear tag matches stop the build.

TAG-COMPLETE-4 — Old translation history is still available.

TAG-COMPLETE-5 — Importing the same spreadsheet again makes no changes.

TAG-COMPLETE-6 — Building the same dictionary again produces the same result.

TAG-COMPLETE-7 — TAG-COMPLETE-1 through TAG-COMPLETE-6 pass. Publication waits only for
TAG-TEST-8.
