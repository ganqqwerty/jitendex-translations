#!/usr/bin/env python3
"""Analyze Yomitan frequency dictionaries against English and Russian Jitendex."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_FREQUENCY_DIR = Path(
    "/Users/iuriikatkov/Documents/_japanese/yomichan/"
    "shoui Yomichan Dictionaries Collection [learnjapanese.moe]/Frequency"
)
DEFAULT_DICTIONARIES = (
    ("aozora", "Aozora Bunko", "[Freq] Aozora Bunko.zip"),
    ("bccwj", "BCCWJ", "[Freq] BCCWJ.zip"),
    ("cc100", "CC100", "[Freq] CC100.zip"),
    ("monodicts", "Monodicts 206k", "[Freq] Monodicts 206k.zip"),
    ("wikipedia", "Wikipedia v2", "[Freq] Wikipedia v2.zip"),
    ("kokugo", "国語辞典", "[Freq] 国語辞典.zip"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bank_names(archive: zipfile.ZipFile, prefix: str) -> list[str]:
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)\.json$")
    matches = []
    for name in archive.namelist():
        match = pattern.match(name)
        if match:
            matches.append((int(match.group(1)), name))
    return [name for _, name in sorted(matches)]


def load_jitendex_headwords(path: Path) -> set[str]:
    words: set[str] = set()
    with zipfile.ZipFile(path) as archive:
        for name in bank_names(archive, "term_bank"):
            rows = json.loads(archive.read(name))
            words.update(row[0] for row in rows if row and isinstance(row[0], str))
    return words


def frequency_rank(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, dict):
        for key in ("frequency", "value"):
            rank = value.get(key)
            if isinstance(rank, (int, float)) and not isinstance(rank, bool):
                return int(rank)
    return None


def load_frequency(
    path: Path, limit: int
) -> tuple[dict[str, int], set[str], dict[str, Any]]:
    ranks: dict[str, int] = {}
    all_headwords: set[str] = set()
    record_count = 0
    ranked_record_count = 0
    with zipfile.ZipFile(path) as archive:
        index = json.loads(archive.read("index.json"))
        for name in bank_names(archive, "term_meta_bank"):
            for row in json.loads(archive.read(name)):
                record_count += 1
                if len(row) < 3 or row[1] != "freq" or not isinstance(row[0], str):
                    continue
                all_headwords.add(row[0])
                rank = frequency_rank(row[2])
                if rank is None or rank < 1 or rank > limit:
                    continue
                ranked_record_count += 1
                ranks[row[0]] = min(rank, ranks.get(row[0], rank))
    metadata = {
        "title": index.get("title"),
        "revision": index.get("revision"),
        "recordsTotal": record_count,
        "recordsTop": ranked_record_count,
    }
    return ranks, all_headwords, metadata


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    source_words = load_jitendex_headwords(args.source)
    russian_words = load_jitendex_headwords(args.russian)
    dictionaries = []
    all_ranks: dict[str, dict[str, int]] = {}
    full_union: set[str] = set()

    for dictionary_id, label, filename in DEFAULT_DICTIONARIES:
        path = args.frequency_dir / filename
        ranks, all_headwords, metadata = load_frequency(path, args.limit)
        full_union.update(all_headwords)
        status = Counter(
            "translated"
            if word in russian_words
            else "untranslated"
            if word in source_words
            else "absent"
            for word in ranks
        )
        dictionaries.append(
            {
                "id": dictionary_id,
                "label": label,
                "filename": filename,
                "sha256": sha256(path),
                "uniqueHeadwords": len(ranks),
                "allUniqueHeadwords": len(all_headwords),
                "translated": status["translated"],
                "untranslated": status["untranslated"],
                "absent": status["absent"],
                **metadata,
            }
        )
        for word, rank in ranks.items():
            all_ranks.setdefault(word, {})[dictionary_id] = rank

    words = []
    union_status: Counter[str] = Counter()
    membership_count: Counter[int] = Counter()
    for word in sorted(all_ranks):
        status = (
            "translated"
            if word in russian_words
            else "untranslated"
            if word in source_words
            else "absent"
        )
        ranks = all_ranks[word]
        union_status[status] += 1
        membership_count[len(ranks)] += 1
        words.append({"w": word, "s": status, "r": ranks})

    return {
        "method": {
            "rankLimit": args.limit,
            "unit": "unique exact headword strings",
            "translatedDefinition": "Headword occurs in the Russian Jitendex export.",
            "untranslatedDefinition": (
                "Headword occurs in source Jitendex but not in the Russian Jitendex export."
            ),
            "absentDefinition": "Headword does not occur in source Jitendex.",
        },
        "baselines": {
            "source": {
                "path": str(args.source),
                "sha256": sha256(args.source),
                "headwords": len(source_words),
            },
            "russian": {
                "path": str(args.russian),
                "sha256": sha256(args.russian),
                "headwords": len(russian_words),
            },
        },
        "dictionaries": dictionaries,
        "union": {
            "uniqueHeadwords": len(all_ranks),
            "allUniqueHeadwords": len(full_union),
            "translated": union_status["translated"],
            "untranslated": union_status["untranslated"],
            "absent": union_status["absent"],
            "membershipCount": dict(sorted(membership_count.items())),
        },
        "words": words,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frequency-dir", type=Path, default=DEFAULT_FREQUENCY_DIR)
    parser.add_argument(
        "--source", type=Path, default=Path("work/downloads/jitendex-yomitan.zip")
    )
    parser.add_argument(
        "--russian", type=Path, default=Path("dist/jitendex-jpdb-140k-ru-luna-clean-v1.zip")
    )
    parser.add_argument("--limit", type=int, default=20_000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "window.FREQUENCY_ANALYSIS = "
        + json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), "union": result["union"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
