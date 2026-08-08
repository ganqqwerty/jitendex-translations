from __future__ import annotations

import copy
import json
import re
import sqlite3
from typing import Any

from .util import JAPANESE_RE, json_pointer_get, json_pointer_set, sha256_bytes, structural_fingerprint


FORM_ONLY_RE = re.compile(r"^(.+?) only$")


def _localize_mixed_form_restrictions(node: Any) -> None:
    """Localize Jitendex's mixed Japanese/English ``<form> only`` labels."""
    if isinstance(node, dict):
        content = node.get("content")
        match = (
            FORM_ONLY_RE.fullmatch(content)
            if node.get("lang") == "ja" and isinstance(content, str)
            else None
        )
        if match and JAPANESE_RE.search(match.group(1)):
            node["content"] = f"только {match.group(1)}"
            node["lang"] = "ru"
        for value in node.values():
            _localize_mixed_form_restrictions(value)
    elif isinstance(node, list):
        for item in node:
            _localize_mixed_form_restrictions(item)


def _set_language_for_leaf(source: Any, pointer: str) -> None:
    segments = pointer.removeprefix("/").split("/")
    if not segments:
        return
    parent_pointer = "/" + "/".join(segments[:-1]) if len(segments) > 1 else ""
    try:
        parent = json_pointer_get(source, parent_pointer)
    except (KeyError, IndexError, TypeError, ValueError):
        return
    if isinstance(parent, dict) and parent.get("lang") == "en" and segments[-1] in {"content", "title"}:
        parent["lang"] = "ru"


def _compose_glossary(source_items: Any, serialized_target: str, pointer: str) -> Any:
    definitions = json.loads(serialized_target)
    if not isinstance(definitions, list) or not definitions:
        raise ValueError(f"glossary target is not a non-empty list at {pointer}")
    if isinstance(source_items, str):
        return definitions[0] if len(definitions) == 1 else "; ".join(definitions)
    if isinstance(source_items, dict) and "content" in source_items:
        rendered = []
        for definition in definitions:
            item = copy.deepcopy(source_items)
            item["content"] = definition
            if item.get("lang") == "en":
                item["lang"] = "ru"
            rendered.append(item)
        return rendered[0] if len(rendered) == 1 else rendered
    if not isinstance(source_items, list) or not source_items:
        raise ValueError(f"glossary source has an unsupported shape at {pointer}")
    template = source_items[0]
    output: list[Any] = []
    for definition in definitions:
        if not isinstance(definition, str) or not definition.strip():
            raise ValueError(f"invalid glossary definition at {pointer}")
        if isinstance(template, str):
            output.append(definition)
        elif isinstance(template, dict) and "content" in template:
            item = copy.deepcopy(template)
            item["content"] = definition
            if item.get("lang") == "en":
                item["lang"] = "ru"
            output.append(item)
        else:
            raise ValueError(f"unsupported glossary item shape at {pointer}")
    return output


def apply_article(connection: sqlite3.Connection, run_id: int, article: sqlite3.Row) -> list[Any]:
    if sha256_bytes(article["raw_json"].encode()) != article["source_sha256"]:
        raise ValueError(f"article {article['id']} source hash changed")
    source = json.loads(article["raw_json"])
    rows = connection.execute(
        """SELECT tu.json_pointer,tu.role,tu.source_text,t.target_text,t.target_sha256
        FROM translation_unit tu JOIN translation t ON t.unit_id=tu.id AND t.run_id=tu.run_id
        WHERE tu.run_id=? AND tu.article_id=? AND t.accepted=1 ORDER BY tu.json_pointer""",
        (run_id, article["id"]),
    ).fetchall()
    all_units = connection.execute(
        "SELECT json_pointer FROM translation_unit WHERE run_id=? AND article_id=? ORDER BY json_pointer",
        (run_id, article["id"]),
    ).fetchall()
    if len(rows) != len(all_units):
        raise ValueError(f"article {article['id']} has unaccepted translation units")
    pointers = {row["json_pointer"] for row in all_units}
    run_article = connection.execute(
        "SELECT structural_fingerprint FROM run_article WHERE run_id=? AND article_id=?",
        (run_id, article["id"]),
    ).fetchone()
    expected_fingerprint = run_article["structural_fingerprint"] if run_article else article["structural_fingerprint"]
    if structural_fingerprint(source, pointers) != expected_fingerprint:
        raise ValueError(f"article {article['id']} source structural fingerprint changed")
    output = copy.deepcopy(source)
    for row in rows:
        if sha256_bytes(row["target_text"].encode()) != row["target_sha256"]:
            raise ValueError(f"accepted target hash changed at {row['json_pointer']}")
        current = json_pointer_get(output, row["json_pointer"])
        expected_source = json.loads(row["source_text"]) if row["role"] == "glossary_set" else row["source_text"]
        if current != expected_source:
            raise ValueError(f"source text changed at {row['json_pointer']}")
        target = _compose_glossary(current, row["target_text"], row["json_pointer"]) if row["role"] == "glossary_set" else row["target_text"]
        json_pointer_set(output, row["json_pointer"], target)
        _set_language_for_leaf(output, row["json_pointer"])
    # Language edits are the only structural exception, checked by reverting them.
    comparison = copy.deepcopy(output)
    for row in rows:
        original = json.loads(row["source_text"]) if row["role"] == "glossary_set" else row["source_text"]
        json_pointer_set(comparison, row["json_pointer"], original)
        segments = row["json_pointer"].removeprefix("/").split("/")
        parent_pointer = "/" + "/".join(segments[:-1]) if len(segments) > 1 else ""
        parent = json_pointer_get(comparison, parent_pointer)
        source_parent = json_pointer_get(source, parent_pointer)
        if isinstance(parent, dict) and isinstance(source_parent, dict) and "lang" in source_parent:
            parent["lang"] = source_parent["lang"]
    if structural_fingerprint(comparison, pointers) != expected_fingerprint:
        raise ValueError(f"article {article['id']} unapproved structure changed")
    # These upstream labels are marked as Japanese and therefore are not
    # translation units, although their trailing English marker is visible.
    _localize_mixed_form_restrictions(output)
    return output
