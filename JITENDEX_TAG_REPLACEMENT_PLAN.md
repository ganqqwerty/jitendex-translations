# Plan for Replacing Russian Jitendex Tags

## Source of truth

The approved spreadsheet is now the source of truth for Russian tag names and
tooltips. Luna must not overwrite these translations.

We will keep old Luna translations in the database for history, but they will no
longer affect exported dictionaries.

## Why we need a full replacement

The same English tag was translated by the LLM many times in different articles.
This created many Russian versions of the same tag.

We cannot find tags by looking at their current Russian text. Instead, we will use
the original Jitendex tag code and category, such as:

- category: `part-of-speech-info`
- code: `v1`

This information does not change when the visible text is translated.

## Already done

1. Matched all 236 spreadsheet rows with the original Jitendex tags.
2. Put all approved translations into `jitendex_tag`.
3. Saved the spreadsheet path and SHA-256 in the database.
4. Saved the previous Luna translations in `jitendex_tag_translation_history`.
5. Prevented Luna from overwriting approved rows.
6. Created a backup of the database from before the import.

## Next step: use approved tags in dictionary builds

1. Load the approved tags for the Jitendex version used by the build.
2. Stop the build if any tag is missing or has more than one match.
3. Find every tag in an article using its original category and code.
4. Replace its visible name with the approved `label_ru`.
5. Replace its tooltip with the approved `description_ru`.
6. Do the same for tags stored in `tag_bank_*.json`.
7. Replace every old LLM version, even when it already looks correct.

We will do this while building the dictionary. We will not rewrite old translation
runs, attempts, or reviews. This keeps the history intact.

## Remove the old tag source

After the new build logic is tested:

1. Stop reading tag translations from `terminology/tag-bank-ru-v1.json`.
2. Use only the approved database table.
3. Mark the old Luna tag prompt and responses as replaced, but keep them for history.
4. Update the Luna runbook to explain the new process.

## Tests before release

1. Test normal tags, tags without a code, and `tag_bank` tags.
2. Test that a missing or duplicate approved tag stops the build.
3. Build a test dictionary from run 6.
4. Check every exported tag against the approved database table.
5. Count how many different LLM translations were replaced for each tag.
6. Run all project tests and Yomitan validation.
7. Show a before-and-after report for review.
8. After approval, rebuild and publish the maintained dictionaries.

## Finished when

- Every exported tag exactly matches the approved spreadsheet.
- Old LLM wording cannot affect the output.
- Missing or unclear tag matches stop the build.
- Old translation history is still available.
- Importing the same spreadsheet again makes no changes.
- Building the same dictionary again produces the same result.
