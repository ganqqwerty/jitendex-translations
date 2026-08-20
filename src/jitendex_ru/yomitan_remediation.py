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
from .util import atomic_write, canonical_json


REDIRECT_SOURCE_PREFIX = "redirected from "
REDIRECT_RU_PREFIX = "вариант написания: "
FORMS_TOOLTIP_SOURCE = "valid only for these forms and/or readings"
FORMS_TOOLTIP_RU = "допустимо только для этих форм и/или чтений"
FORM_ONLY_RE = re.compile(r"^(.+?) only$")
MIXED_ALPHABET_RE = re.compile(
    r"(?:[A-Za-z][\u0400-\u04ff]|[\u0400-\u04ff][A-Za-z])"
)
VISIBLE_TOKEN_RE = re.compile(r"[A-Za-z\u0400-\u04ff]+")

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
    "short_restrictions_localized": 74,
}


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


def _localize_node(node: Any, counts: dict[str, int]) -> Any:
    if isinstance(node, dict):
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
            node[key] = _localize_node(value, counts)
        return node
    if isinstance(node, list):
        for index, value in enumerate(node):
            node[index] = _localize_node(value, counts)
        return node
    if isinstance(node, str):
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
    return {"issues": issues, "issue_counts": counts}


def write_yomitan_update_index(archive_path: Path, output_path: Path) -> dict[str, Any]:
    """Generate the staged owned update index from a verified archive's metadata."""
    with zipfile.ZipFile(archive_path) as archive:
        archive_index = json.loads(archive.read("index.json"))
    validate_yomitan_metadata(archive_index, require_updatable=False)
    hosted_index = dict(archive_index)
    hosted_index.update({
        "isUpdatable": True,
        "indexUrl": UPDATE_INDEX_URL,
        "downloadUrl": RELEASE_DOWNLOAD_URL,
    })
    validate_yomitan_metadata(hosted_index, require_updatable=True)
    atomic_write(output_path, canonical_json(hosted_index))
    return hosted_index
