from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from jitendex_ru.util import canonical_json, sha256_bytes
from jitendex_ru.yomitan_remediation import MIXED_ALPHABET_RE, VISIBLE_TOKEN_RE


TOOLTIP_SOURCE = (
    "jukujikun (idiomatic reading of a kanji compound) or "
    "gikun (idiosyncratic reading of a particular kanji)"
)
TOOLTIP_TARGET = (
    "дзюкудзикун (идиоматическое чтение сочетания кандзи) или "
    "гикун (индивидуальное чтение отдельного кандзи)"
)

LATIN_TO_CYRILLIC = {
    "a": "а", "c": "с", "e": "е", "i": "и", "o": "о", "p": "р", "x": "х", "y": "у",
    "á": "а", "ā": "а", "é": "е", "í": "и", "ó": "о", "ö": "о", "ō": "о", "ú": "у", "ỳ": "у",
    "A": "А", "C": "С", "E": "Е", "I": "И", "O": "О", "P": "Р", "X": "Х", "Y": "У",
    "Á": "А", "Ā": "А", "É": "Е", "Í": "И", "Ó": "О", "Ö": "О", "Ō": "О", "Ú": "У",
}
LATIN_RE = re.compile(r"[A-Za-z\u00c0-\u024f\u1e00-\u1eff]")

EXPLICIT_TOKEN_REPLACEMENTS = {
    "credentialизм": "креденциализм",
    "emphатическая": "эмфатическая",
    "emphатично": "эмфатично",
    "emphатичное": "эмфатичное",
    "Śакра": "Шакра",
    "Кōbō": "Кобо",
    "Киheitai": "Кихэйтай",
    "Коhелета": "Кохелета",
    "ММR": "MMR",
    "Манaka": "Манака",
    "Марu": "Мару",
    "Миwa": "Мива",
    "Нakasэндо": "Накасэндо",
    "Оrectolobus": "Orectolobus",
    "Хокурiku": "Хокурику",
    "Ямантaka": "Ямантака",
    "аманatsu": "аманацу",
    "бурqa": "бурка",
    "гikun": "гикун",
    "гuy": "guy",
    "гикýн": "гикун",
    "дзюкудзikun": "дзюкудзикун",
    "ивагaki": "ивагаки",
    "касugамицин": "касугамицин",
    "кинako": "кинако",
    "клutch": "клатч",
    "котatsu": "котацу",
    "лаissez": "laissez",
    "ловушka": "ловушка",
    "мандarinка": "мандаринка",
    "меunière": "meunière",
    "намahагэ": "намахагэ",
    "ньcastleская": "ньюкаслская",
    "сарouэль": "саруэль",
    "скуka": "скука",
    "сталagmíт": "сталагмит",
    "фукýси": "фукуси",
    "хлорофthalmus": "Chlorophthalmus",
    "чữном": "chữ Nôm",
    "эjective": "эжективный",
    "яmaуба": "ямауба",
    "ДOС": "DOS",
    "гиккỳном": "гикуном",
    "тонзиллолúт": "тонзиллолит",
    "сёпō": "сиппо",
}

SOURCE_OVERRIDES = {
    TOOLTIP_SOURCE: TOOLTIP_TARGET,
    "We really painted the town red last night.": (
        "Мы вчера вечером, выпив, ходили по всему городу и вовсю кутили."
    ),
    "This program cannot be run in DOS mode.": "Эта программа не запускается в режиме DOS.",
    "reading is gikun for 更衣": "чтение 更衣 является гикуном",
    "even Kōbō Daishi's handwriting contains mistakes": "даже в почерке Кобо Дайси бывают ошибки",
    '{"content":"chu nom (formerly used Vietnamese script based on Chinese characters)","tag":"li"}': (
        '["chữ Nôm — вьетнамская письменность на основе китайских иероглифов, '
        'ныне вышедшая из употребления"]'
    ),
    '[{"content":"tonsillolith","tag":"li"},{"content":"tonsil stone","tag":"li"}]': (
        '["тонзиллолит","камень в миндалине"]'
    ),
    '{"content":"shippō pattern (of overlapping circles)","tag":"li"}': (
        '["узор сиппо (из перекрывающихся кругов)"]'
    ),
    '{"content":"Newcastle disease","tag":"li"}': '["болезнь Ньюкасла"]',
    '{"content":"ejective consonant","tag":"li"}': '["эжективный согласный","эжектив"]',
    '{"content":"Chikushū (the two former provinces of Chikuzen and Chikugo)","tag":"li"}': (
        '["Тикусю — общее название двух бывших провинций, Тикудзэн и Тикуго"]'
    ),
    '[{"content":"yakishime chinaware","tag":"li"},{"content":"high-fired unglazed ceramics","tag":"li"}]': (
        '["якисимэ — керамика, обожжённая при высокой температуре без глазури",'
        '"высокотемпературная неглазурованная керамика"]'
    ),
    '{"content":"mandarin duck (Aix galericulata)","tag":"li"}': (
        '["утка-мандаринка (Aix galericulata)"]'
    ),
    '[{"content":"burka","tag":"li"},{"content":"burqa","tag":"li"},{"content":"burkha","tag":"li"},{"content":"bourkha","tag":"li"}]': (
        '["бурка"]'
    ),
}


def _generic_token_replacement(token: str) -> str | None:
    latin = LATIN_RE.findall(token)
    if not latin or not all(character in LATIN_TO_CYRILLIC for character in latin):
        return None
    return "".join(LATIN_TO_CYRILLIC.get(character, character) for character in token)


def _mixed_tokens(text: str) -> list[str]:
    return [token for token in VISIBLE_TOKEN_RE.findall(text) if MIXED_ALPHABET_RE.search(token)]


def generate(audit: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    by_unit: dict[str, dict[str, Any]] = {}
    for finding in audit["findings"]:
        record = by_unit.setdefault(finding["unit_id"], {**finding, "tokens": []})
        if finding["detected_token"] not in record["tokens"]:
            record["tokens"].append(finding["detected_token"])

    changes = []
    approvals = []
    for unit_id, record in by_unit.items():
        previous = record["current_target"]
        canonical = SOURCE_OVERRIDES.get(record["source_text"], previous)
        method = "exact_source_override" if canonical != previous else "reviewed_token_normalization"
        if canonical == previous:
            for token in record["tokens"]:
                replacement = EXPLICIT_TOKEN_REPLACEMENTS.get(token)
                if replacement is None:
                    replacement = _generic_token_replacement(token)
                if replacement is None:
                    raise ValueError(f"unreviewed mixed token {token!r} in {unit_id}")
                canonical = canonical.replace(token, replacement)
        remaining = _mixed_tokens(canonical)
        if remaining:
            raise ValueError(f"remediation left mixed tokens {remaining} in {unit_id}: {canonical}")
        if canonical == previous:
            raise ValueError(f"remediation did not change {unit_id}")
        changes.append({
            "unit_id": unit_id,
            "source_sha256": record["source_sha256"],
            "previous_target_sha256": record["target_sha256"],
            "canonical_target_text": canonical,
        })
        approvals.append({
            "unit_id": unit_id,
            "article_id": record["article_id"],
            "json_pointer": record["json_pointer"],
            "role": record["role"],
            "source_text": record["source_text"],
            "previous_target": previous,
            "canonical_target": canonical,
            "detected_tokens": record["tokens"],
            "classification": "MUST_TRANSLATE",
            "confidence": "high",
            "review_method": method,
            "reason": "Remove adjacent Latin/Cyrillic corruption while preserving the source meaning.",
        })

    manifest = {
        "schema_version": 1,
        "run_id": audit["run_id"],
        "mapping_source": "approved_yomitan_v1_0_1_remediation",
        "changes": changes,
    }
    approval = {
        "schema_version": 1,
        "run_id": audit["run_id"],
        "source_audit_sha256": sha256_bytes(canonical_json(audit)),
        "reviewer": "main-thread-manual-review",
        "approval_scope": f"all mixed Latin/Cyrillic targets detected by {audit['detector_version']}",
        "approved_changes": approvals,
    }
    return manifest, approval


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("approval", type=Path)
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    manifest, approval = generate(audit)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.approval.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_bytes(canonical_json(manifest) + b"\n")
    args.approval.write_bytes(canonical_json(approval) + b"\n")
    print(json.dumps({
        "changes": len(manifest["changes"]),
        "manifest_sha256": sha256_bytes(args.manifest.read_bytes()),
        "approval_sha256": sha256_bytes(args.approval.read_bytes()),
    }, indent=2))


if __name__ == "__main__":
    main()
