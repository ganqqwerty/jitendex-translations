from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .attribution import (
    COMPILATION_DATETIME_UTC,
    DICTIONARY_AUTHORS,
    DICTIONARY_VERSION,
    PRODUCT_ID,
    PRODUCT_NAME,
)
from .util import (
    CYRILLIC_RE, LATIN_LETTER_CLASS, MIXED_ALPHABET_RE, atomic_write, canonical_json,
    sha256_bytes,
)


REDIRECT_SOURCE_PREFIX = "redirected from "
REDIRECT_RU_PREFIX = "вариант написания: "
FORMS_TOOLTIP_SOURCE = "valid only for these forms and/or readings"
FORMS_TOOLTIP_RU = "допустимо только для этих форм и/или чтений"
FORM_ONLY_RE = re.compile(r"^(.+?) only$")
VISIBLE_TOKEN_RE = re.compile(rf"[{LATIN_LETTER_CLASS}\u0400-\u04ff]+")
LATIN_VISIBLE_RE = re.compile(rf"[{LATIN_LETTER_CLASS}]")
PRESERVED_VISIBLE_SELECTORS = {"attribution", "lang-source-content"}

YOMITAN_TITLE = PRODUCT_NAME
PROJECT_URL = "https://ganqqwerty.github.io/jp-ru-kolobok-dictionary/"
UPDATE_INDEX_URL = f"{PROJECT_URL}yomitan.json"
RELEASE_DOWNLOAD_URL = (
    "https://github.com/ganqqwerty/jp-ru-kolobok-dictionary/releases/download/"
    f"v{DICTIONARY_VERSION}/{PRODUCT_ID}-v{DICTIONARY_VERSION}-yomitan.zip"
)
FORBIDDEN_OPERATIONAL_METADATA = (
    "jitendex.org",
    "github.com/stephenmk/",
    "jitendex-yomitan.zip",
)
PINNED_FULL_ARTICLE_COUNT = 433_885
PINNED_LOCALIZATION_COUNTS = {
    "redirects_localized": 136_668,
    "tooltips_localized": 4_307,
    "short_restrictions_localized": 4_307,
    "graphic_by_localized": 444,
    "graphic_photo_localized": 60,
    "graphic_unknown_author_localized": 3,
}

APPROVED_LEXICAL_REMEDIATIONS = {
    'English: "single hit"': 'Английский: «single hit»',
    'English: "single player"': 'Английский: «single player»',
    '[{"content":"to insert (e.g. a break into proceedings)","tag":"li"},'
    '{"content":"to interpose (e.g. an objection)","tag":"li"},'
    '{"content":"to interject","tag":"li"},'
    '{"content":"to throw in (e.g. a joke)","tag":"li"}]': (
        '["вставлять реплику или паузу в ход происходящего",'
        '"вмешиваться с возражением","вклиниваться в разговор","вставлять шутку"]'
    ),
    '[{"content":"pointe shoes","tag":"li"},{"content":"toe shoes","tag":"li"}]': (
        '["пуанты","балетные туфли с твёрдым носком"]'
    ),
    'Uighur (Turkic ethnic group); Uyghur; Uigur; Uygur': (
        'уйгур (тюркская этническая группа); уйгур; уйгур; уйгур'
    ),
    '[{"content":"with a crackle (of a fire)","tag":"li"},'
    '{"content":"with a rustle","tag":"li"},{"content":"with a burst","tag":"li"}]': (
        '["с потрескиванием (об огне)","с шелестом","резким порывом"]'
    ),
    'common bean (Phaseolus vulgaris); kidney bean; navy bean; wax bean; green bean; '
    'string bean; French bean': (
        'фасоль обыкновенная (Phaseolus vulgaris); фасоль кидни; мелкая белая фасоль; '
        'восковая фасоль; стручковая фасоль; спаржевая фасоль; французская фасоль'
    ),
    'arnis (Filipino marshal art)': 'арнис (филиппинское боевое искусство)',
    'escrima (Filipino martial art)': 'эскрима (филиппинское боевое искусство)',
    '[{"content":"outdoor clothing fashion style for young women","tag":"li"},'
    '{"content":"young woman who dresses in outdoor clothing","tag":"li"},'
    '{"content":"young woman who enjoys mountain climbing","tag":"li"}]': (
        '["модный стиль одежды для молодых женщин в духе одежды для активного отдыха",'
        '"молодая женщина, одевающаяся в туристическом стиле",'
        '"молодая женщина, увлекающаяся альпинизмом"]'
    ),
    'Blue Screen of Death (Windows error screen); BSoD': (
        'синий экран смерти (экран ошибки Windows); BSoD'
    ),
    'axolotl (Ambystoma mexicanum); Mexican salamander; Mexican walking fish': (
        'аксолотль (Ambystoma mexicanum); мексиканская саламандра; '
        'мексиканская ходячая рыба'
    ),
    '[{"content":"nonstandard","tag":"li"},{"content":"out of spec","tag":"li"},'
    '{"content":"irregular","tag":"li"},'
    '{"content":"unconventional (e.g. relationship)","tag":"li"},'
    '{"content":"ugly (e.g. fruits and vegetables)","tag":"li"}]': (
        '["нестандартный","не соответствующий стандарту","нетипичный",'
        '"необычный, например об отношениях","некрасивый, например о фруктах и овощах"]'
    ),
    'Koreatown (Korean district of a city)': 'Корейтаун (корейский район города)',
    'corn flour; maize flour': 'кукурузная мука; маисовая мука',
    '{"content":"goal line","tag":"li"}': '["линия ворот"]',
    'showily decorated truck (e.g. chrome, air-brushed pictures, colored lights); art truck': (
        'показательно украшенный грузовик (например, с хромированными деталями, '
        'аэрографией, цветными огнями); арт-трак'
    ),
    'pull up leather': 'кожа пулл-ап',
}

UNFINISHED_TARGET_TEXTS = frozenset({
    'Язык-источник: English: "single hit"',
    'Язык-источник: English: "single player"',
    '["вставлять реплику или паузу в ход proceedings","вмешиваться с возражением",'
    '"вставлять шутку"]',
    '["вставлять паузу в ход proceedings","вставлять возражение",'
    '"вклиниваться в разговор","вставлять шутку"]',
    '["пу anything"]',
    'уйгур (Turkic ethnic группа); уйгур; уйгур; уйгур',
    'уйгур (Turkic ethnic group); уйгур; уйгур; уйгур',
    '["с потрескиванием (о fire)","с шелестом","резко вспыхнув"]',
    'фасоль обыкновенная (Phaseolus vulgaris); фасоль кидни; фасоль navy; '
    'восковая фасоль; стручковая фасоль; спаржевая фасоль; французская фасоль',
    'арнис (Filipino marshal art)',
    'эскрима (Filipino martial art)',
    '["модный стиль одежды для молодых женщин в духе одежды для активного отдыха",'
    '"молодая женщина, одевающаяся в стиле outdoor",'
    '"молодая женщина, увлекающаяся альпинизмом"]',
    '«Синий экран смерти» (экран ошибки Windows error); BSoD',
    'синий экран смерти (Windows error screen); BSoD',
    'Синий экран смерти (Windows error screen); BSoD',
    'аксолотль (Ambystoma mexicanum); Mexican salamander; Mexican walking fish',
    '["нестандартный","не соответствующий стандарту","нетипичный",'
    '"необычный, unconventional, например об отношениях",'
    '"некрасивый, например о фруктах и овощах"]',
    'Корейтаун (Korean district города)',
    'Корейтаун (Korean district of a city)',
    'corn flour; кукурузная мука',
    '["линия ворот","линия goal в спортивной игре"]',
    'показательно украшенный грузовик (например, с хромированными деталями, '
    'аэрографией, цветными огнями); art truck',
    'кожа pull-up',
})


def yomitan_revision(scope_id: str, *, compilation_datetime: str = COMPILATION_DATETIME_UTC) -> str:
    """Return a Kolobok-owned revision without an upstream revision prefix."""
    timestamp = datetime.fromisoformat(compilation_datetime.replace("Z", "+00:00"))
    release_id = f"{PRODUCT_ID}-v{DICTIONARY_VERSION}"
    qualified_scope = release_id if scope_id == release_id else f"{release_id}-{scope_id}"
    return f"{timestamp:%Y.%m.%d}.0-{qualified_scope}"


def build_yomitan_index(
    source_index: dict[str, Any], *, description: str, revision: str, updatable: bool = False,
) -> dict[str, Any]:
    """Build explicit Kolobok metadata while retaining source attribution."""
    index = {
        "title": YOMITAN_TITLE,
        "revision": revision,
        "format": source_index.get("format", 3),
        "sequenced": source_index.get("sequenced", True),
        "author": DICTIONARY_AUTHORS,
        "description": description,
        "attribution": source_index.get("attribution", ""),
        "sourceLanguage": "ja",
        "targetLanguage": "ru",
        "url": PROJECT_URL,
    }
    if updatable:
        index.update({
            "isUpdatable": True,
            "indexUrl": UPDATE_INDEX_URL,
            "downloadUrl": RELEASE_DOWNLOAD_URL,
        })
    validate_yomitan_metadata(index, require_updatable=updatable)
    return index


def validate_yomitan_metadata(index: dict[str, Any], *, require_updatable: bool | None = None) -> None:
    if index.get("title") != YOMITAN_TITLE:
        raise ValueError(f"Yomitan title must be the stable {YOMITAN_TITLE!r}")
    if index.get("sourceLanguage") != "ja" or index.get("targetLanguage") != "ru":
        raise ValueError("Yomitan language metadata must be ja -> ru")
    if index.get("url") != PROJECT_URL:
        raise ValueError("Yomitan project URL is not owned by Kolobok")
    if f"v{DICTIONARY_VERSION}" not in str(index.get("revision", "")):
        raise ValueError("Yomitan revision lacks the dictionary version")
    update_fields = {key for key in ("isUpdatable", "indexUrl", "downloadUrl") if key in index}
    updatable = index.get("isUpdatable") is True
    if update_fields and (update_fields != {"isUpdatable", "indexUrl", "downloadUrl"} or not updatable):
        raise ValueError("Yomitan update metadata must be enabled as one complete tuple")
    if require_updatable is True and not updatable:
        raise ValueError("Yomitan update metadata is required")
    if require_updatable is False and update_fields:
        raise ValueError("Yomitan update metadata must be absent until publication")
    if updatable and (
        index.get("indexUrl") != UPDATE_INDEX_URL
        or index.get("downloadUrl") != RELEASE_DOWNLOAD_URL
    ):
        raise ValueError("Yomitan update metadata does not use the owned release channel")
    for key in ("url", "indexUrl", "downloadUrl"):
        value = str(index.get(key, "")).lower()
        if any(forbidden in value for forbidden in FORBIDDEN_OPERATIONAL_METADATA):
            raise ValueError(f"foreign operational metadata in {key}")


def _localize_node(
    node: Any, counts: dict[str, int], *, graphic_attribution: bool = False,
) -> Any:
    if isinstance(node, dict):
        is_graphic_attribution = (
            isinstance(node.get("data"), dict)
            and node["data"].get("content") == "graphic-attribution"
        )
        content = node.get("content")
        match = (
            FORM_ONLY_RE.fullmatch(content)
            if node.get("lang") == "ja" and isinstance(content, str)
            else None
        )
        if match:
            node["content"] = f"только {match.group(1)}"
            node["lang"] = "ru"
            counts["short_restrictions_localized"] += 1
        for key, value in list(node.items()):
            node[key] = _localize_node(
                value, counts,
                graphic_attribution=graphic_attribution or is_graphic_attribution,
            )
        return node
    if isinstance(node, list):
        for index, value in enumerate(node):
            node[index] = _localize_node(
                value, counts, graphic_attribution=graphic_attribution,
            )
        return node
    if isinstance(node, str):
        if graphic_attribution:
            if node.startswith(" by "):
                counts["graphic_by_localized"] += 1
                creator = node[4:]
                if "Unknown author" in creator:
                    counts["graphic_unknown_author_localized"] += creator.count("Unknown author")
                    creator = creator.replace("Unknown author", "неизвестный автор")
                return f" — автор: {creator}"
            if node == "Photo":
                counts["graphic_photo_localized"] += 1
                return "Фото"
            if node == "Unknown author":
                counts["graphic_unknown_author_localized"] += 1
                return "неизвестный автор"
        if node.startswith(REDIRECT_SOURCE_PREFIX) and len(node) > len(REDIRECT_SOURCE_PREFIX):
            counts["redirects_localized"] += 1
            return f"{REDIRECT_RU_PREFIX}{node[len(REDIRECT_SOURCE_PREFIX):]}"
        if node == FORMS_TOOLTIP_SOURCE:
            counts["tooltips_localized"] += 1
            return FORMS_TOOLTIP_RU
    return node


def localize_yomitan_rows(rows: list[list[Any]]) -> dict[str, int]:
    counts = {key: 0 for key in PINNED_LOCALIZATION_COUNTS}
    for row in rows:
        _localize_node(row[5], counts)
    if len(rows) == PINNED_FULL_ARTICLE_COUNT and counts != PINNED_LOCALIZATION_COUNTS:
        raise ValueError(
            f"pinned Yomitan localization counts changed: expected "
            f"{PINNED_LOCALIZATION_COUNTS}, found {counts}"
        )
    return counts


def _visible_strings(node: Any, pointer: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, str):
        yield pointer, node
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _visible_strings(value, f"{pointer}/{index}")
    elif isinstance(node, dict):
        for key, value in node.items():
            if key in {"content", "title"}:
                yield from _visible_strings(value, f"{pointer}/{key}")


def _visible_leaf_records(
    node: Any, pointer: str = "", *, selector: str | None = None,
    lang: str | None = None,
) -> Iterator[dict[str, Any]]:
    if isinstance(node, str):
        yield {"pointer": pointer, "text": node, "selector": selector, "lang": lang}
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _visible_leaf_records(
                value, f"{pointer}/{index}", selector=selector, lang=lang,
            )
    elif isinstance(node, dict):
        data = node.get("data")
        own_selector = data.get("content") if isinstance(data, dict) else None
        own_lang = node.get("lang") if isinstance(node.get("lang"), str) else None
        for key in ("content", "title"):
            if key in node:
                yield from _visible_leaf_records(
                    node[key], f"{pointer}/{key}",
                    selector=own_selector or selector, lang=own_lang or lang,
                )


def classify_yomitan_rows(rows: list[list[Any]]) -> dict[str, Any]:
    counts = {"MUST_TRANSLATE": 0, "MUST_PRESERVE": 0, "REVIEW": 0}
    preserve_rules: dict[str, int] = {}
    reviews: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        for leaf in _visible_leaf_records(row[5], "/5"):
            text = leaf["text"]
            if not LATIN_VISIBLE_RE.search(text):
                continue
            code = None
            if text.startswith(REDIRECT_SOURCE_PREFIX) or text == FORMS_TOOLTIP_SOURCE:
                code = "raw_ui_template"
            elif any(MIXED_ALPHABET_RE.search(token) for token in VISIBLE_TOKEN_RE.findall(text)):
                code = "mixed_alphabet_token"
            elif leaf["lang"] == "en" and leaf["selector"] not in PRESERVED_VISIBLE_SELECTORS:
                code = "unexpected_english_language_markup"
            if code:
                counts["MUST_TRANSLATE"] += 1
                issues.append({"code": code, "row": row_index, **leaf})
                continue
            if leaf["selector"] in PRESERVED_VISIBLE_SELECTORS:
                rule = "attribution" if leaf["selector"] == "attribution" else "source_quotation"
                counts["MUST_PRESERVE"] += 1
                preserve_rules[rule] = preserve_rules.get(rule, 0) + 1
                continue
            if leaf["lang"] == "ja":
                counts["MUST_PRESERVE"] += 1
                preserve_rules["japanese_source"] = preserve_rules.get("japanese_source", 0) + 1
                continue
            if not CYRILLIC_RE.search(text) and leaf["selector"] != "graphic-attribution":
                counts["MUST_PRESERVE"] += 1
                preserve_rules["code_name_formula_or_source_term"] = (
                    preserve_rules.get("code_name_formula_or_source_term", 0) + 1
                )
                continue
            counts["REVIEW"] += 1
            identity = {
                "text": text, "selector": leaf["selector"], "lang": leaf["lang"],
            }
            reviews.append({
                "identity_sha256": sha256_bytes(canonical_json(identity)),
                **identity, "row": row_index, "pointer": leaf["pointer"],
            })
    return {
        "classification_counts": counts,
        "must_preserve_rule_counts": preserve_rules,
        "review_records": reviews,
        "must_translate_issues": issues,
    }


def scan_yomitan_rows(rows: list[list[Any]]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        for pointer, text in _visible_strings(row[5], "/5"):
            if text.startswith(REDIRECT_SOURCE_PREFIX):
                issues.append({"code": "raw_redirect_template", "row": row_index, "pointer": pointer, "text": text})
            if text == FORMS_TOOLTIP_SOURCE:
                issues.append({"code": "raw_forms_tooltip", "row": row_index, "pointer": pointer, "text": text})
            for token in VISIBLE_TOKEN_RE.findall(text):
                if MIXED_ALPHABET_RE.search(token):
                    issues.append({
                        "code": "mixed_alphabet_token", "row": row_index,
                        "pointer": pointer, "text": text, "token": token,
                    })
        stack = [("/5", row[5])]
        while stack:
            pointer, node = stack.pop()
            if isinstance(node, dict):
                content = node.get("content")
                if node.get("lang") == "ja" and isinstance(content, str) and FORM_ONLY_RE.fullmatch(content):
                    issues.append({
                        "code": "raw_short_restriction", "row": row_index,
                        "pointer": f"{pointer}/content", "text": content,
                    })
                stack.extend((f"{pointer}/{key}", value) for key, value in node.items())
            elif isinstance(node, list):
                stack.extend((f"{pointer}/{index}", value) for index, value in enumerate(node))
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue["code"]] = counts.get(issue["code"], 0) + 1
    classification = classify_yomitan_rows(rows)
    for issue in classification["must_translate_issues"]:
        if issue["code"] == "unexpected_english_language_markup":
            issues.append(issue)
            counts[issue["code"]] = counts.get(issue["code"], 0) + 1
    return {"issues": issues, "issue_counts": counts, **classification}


def write_yomitan_update_index(archive_path: Path, output_path: Path) -> dict[str, Any]:
    """Generate the staged owned update index from a verified archive's metadata."""
    with zipfile.ZipFile(archive_path) as archive:
        archive_index = json.loads(archive.read("index.json"))
    validate_yomitan_metadata(archive_index, require_updatable=None)
    hosted_index = dict(archive_index)
    hosted_index.update({
        "isUpdatable": True,
        "indexUrl": UPDATE_INDEX_URL,
        "downloadUrl": RELEASE_DOWNLOAD_URL,
    })
    validate_yomitan_metadata(hosted_index, require_updatable=True)
    atomic_write(output_path, canonical_json(hosted_index))
    return hosted_index
