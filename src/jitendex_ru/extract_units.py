from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterator

from .db import audit
from .util import canonical_json, json_pointer_escape, sha256_bytes, structural_fingerprint


ROLE_BY_SELECTOR = {
    "glossary": "glossary", "example-sentence-b": "example", "part-of-speech-info": "pos",
    "misc-info": "register", "field-info": "label", "dialect-info": "register",
    "sense-note": "note", "info-gloss": "note", "xref": "xref_gloss", "antonym": "xref_gloss",
    "forms": "label", "lang-source": "note",
}
EXCLUDED_SELECTORS = {
    "example-sentence-a", "attribution", "attribution-footnote", "redirect", "ruby", "rt",
}
PROTECTED_RE = re.compile(r"https?://\S+|\b(?:JMdict|Tatoeba)\b|[\u3040-\u30ff\u3400-\u9fff]+|\{[^{}]+\}|\b\d+(?:\.\d+)*\b")


@dataclass(frozen=True)
class ExtractedUnit:
    pointer: str
    role: str
    source_text: str
    protected_tokens: tuple[str, ...]


def _flatten_text(node: Any, output: list[str]) -> None:
    if isinstance(node, str):
        output.append(node)
    elif isinstance(node, dict):
        if "content" in node:
            _flatten_text(node["content"], output)
    elif isinstance(node, list):
        for child in node:
            _flatten_text(child, output)


def _visible_text(node: Any) -> str:
    output: list[str] = []
    _flatten_text(node, output)
    return " ".join(part.strip() for part in output if part.strip())


def glossary_evidence(serialized_subtree: str) -> list[str]:
    subtree = json.loads(serialized_subtree)
    items = subtree if isinstance(subtree, list) else [subtree]
    return [text for item in items if (text := _visible_text(item))]


def _selector(node: dict[str, Any]) -> str | None:
    data = node.get("data")
    if isinstance(data, dict) and isinstance(data.get("content"), str):
        return data["content"]
    return None


def _walk(node: Any, pointer: str = "", selectors: tuple[str, ...] = ()) -> Iterator[ExtractedUnit]:
    if isinstance(node, dict):
        selector = _selector(node)
        active = selectors + ((selector,) if selector else ())
        if any(item in EXCLUDED_SELECTORS for item in active):
            return
        role = next((ROLE_BY_SELECTOR[item] for item in reversed(active) if item in ROLE_BY_SELECTOR), None)
        for key, value in node.items():
            child_pointer = f"{pointer}/{json_pointer_escape(key)}"
            if key in {"data", "href", "path", "src", "lang", "style", "tag"}:
                continue
            if key in {"content", "title"} and isinstance(value, str):
                text = value.strip()
                if role and text and re.search(r"[A-Za-z]", text):
                    yield ExtractedUnit(child_pointer, "tooltip" if key == "title" else role, text, tuple(PROTECTED_RE.findall(text)))
            else:
                yield from _walk(value, child_pointer, active)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{pointer}/{index}", selectors)
    elif isinstance(node, str):
        role = next((ROLE_BY_SELECTOR[item] for item in reversed(selectors) if item in ROLE_BY_SELECTOR), None)
        text = node.strip()
        if role and text and re.search(r"[A-Za-z]", text):
            yield ExtractedUnit(pointer, role, text, tuple(PROTECTED_RE.findall(text)))


def _walk_lexicographer(node: Any, pointer: str = "", selectors: tuple[str, ...] = ()) -> Iterator[ExtractedUnit]:
    """Extract one variable-length unit per glossary and scalar units elsewhere."""
    if isinstance(node, dict):
        selector = _selector(node)
        active = selectors + ((selector,) if selector else ())
        if any(item in EXCLUDED_SELECTORS for item in active):
            return
        if selector == "glossary" and "content" in node:
            subtree = node["content"]
            items = subtree if isinstance(subtree, list) else [subtree]
            glosses = [_visible_text(item) for item in items]
            glosses = [item for item in glosses if item]
            if glosses and any(re.search(r"[A-Za-z]", item) for item in glosses):
                source = canonical_json(subtree).decode()
                protected = tuple(dict.fromkeys(PROTECTED_RE.findall(" ".join(glosses))))
                yield ExtractedUnit(f"{pointer}/content", "glossary_set", source, protected)
            return
        role = next((ROLE_BY_SELECTOR[item] for item in reversed(active) if item in ROLE_BY_SELECTOR), None)
        for key, value in node.items():
            child_pointer = f"{pointer}/{json_pointer_escape(key)}"
            if key in {"data", "href", "path", "src", "lang", "style", "tag"}:
                continue
            if key in {"content", "title"} and isinstance(value, str):
                text = value.strip()
                if role and text and re.search(r"[A-Za-z]", text):
                    yield ExtractedUnit(child_pointer, "tooltip" if key == "title" else role, text, tuple(PROTECTED_RE.findall(text)))
            else:
                yield from _walk_lexicographer(value, child_pointer, active)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk_lexicographer(value, f"{pointer}/{index}", selectors)
    elif isinstance(node, str):
        role = next((ROLE_BY_SELECTOR[item] for item in reversed(selectors) if item in ROLE_BY_SELECTOR), None)
        text = node.strip()
        if role and text and re.search(r"[A-Za-z]", text):
            yield ExtractedUnit(pointer, role, text, tuple(PROTECTED_RE.findall(text)))


def extract_article_units(row: list[Any], pipeline_version: str = "scalar-v1") -> list[ExtractedUnit]:
    if len(row) < 6:
        return []
    walker = _walk_lexicographer if pipeline_version == "lexicographer-v2" else _walk
    return list(walker(row[5], "/5"))


def _selector_nodes(node: Any, wanted: str) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        if _selector(node) == wanted:
            yield node
        for child in node.values():
            yield from _selector_nodes(child, wanted)
    elif isinstance(node, list):
        for child in node:
            yield from _selector_nodes(child, wanted)


def lexicographic_context(row: list[Any]) -> dict[str, Any]:
    """A sense-oriented brief: English is evidence, Japanese and metadata lead."""
    senses: list[dict[str, Any]] = []
    for index, sense in enumerate(_selector_nodes(row[5], "sense"), 1):
        glosses = []
        for glossary in _selector_nodes(sense, "glossary"):
            content = glossary.get("content")
            items = content if isinstance(content, list) else [content]
            glosses.extend(_visible_text(item) for item in items)
        examples = []
        japanese = [_visible_text(item) for item in _selector_nodes(sense, "example-sentence-a")]
        english = [_visible_text(item) for item in _selector_nodes(sense, "example-sentence-b")]
        for position in range(max(len(japanese), len(english))):
            examples.append({
                "japanese": japanese[position] if position < len(japanese) else "",
                "english_evidence": english[position] if position < len(english) else "",
            })
        labels = []
        for selector in ("part-of-speech-info", "misc-info", "field-info", "dialect-info", "sense-note", "info-gloss"):
            labels.extend(_visible_text(item) for item in _selector_nodes(sense, selector))
        senses.append({
            "sense_id": f"sense-{index}",
            "english_gloss_evidence": [item for item in glosses if item],
            "linguistic_metadata": [item for item in labels if item],
            "examples": examples,
        })
    inventory = []
    for selector in ("forms", "example-sentence-a", "xref", "antonym", "sense-note", "lang-source", "attribution"):
        nodes = list(_selector_nodes(row[5], selector))
        if nodes:
            inventory.append({"element": selector, "count": len(nodes), "content": [_visible_text(item) for item in nodes]})
    return {"senses": senses, "preservation_inventory": inventory}


def semantic_context(row: list[Any]) -> dict[str, Any]:
    units = extract_article_units(row)
    examples: list[dict[str, str]] = []

    def collect(node: Any, active: str | None = None) -> None:
        if isinstance(node, dict):
            own_selector = _selector(node)
            current = own_selector or active
            if own_selector == "example-sentence-a":
                texts: list[str] = []
                _flatten_text(node, texts)
                examples.append({"japanese": " ".join(texts)})
            elif own_selector == "example-sentence-b":
                texts = []
                _flatten_text(node, texts)
                if examples and "english" not in examples[-1]:
                    examples[-1]["english"] = " ".join(texts)
            for child in node.values():
                collect(child, current)
        elif isinstance(node, list):
            for child in node:
                collect(child, active)

    collect(row[5])
    return {
        "sense_groups": [{"role": unit.role, "text": unit.source_text} for unit in units if unit.role != "example"],
        "examples": examples,
        "cross_references": [unit.source_text for unit in units if unit.role == "xref_gloss"],
    }


def extract_selected(connection: sqlite3.Connection, run_id: int) -> dict[str, int]:
    added = quarantined = 0
    run = connection.execute("SELECT pipeline_version FROM run WHERE id=?", (run_id,)).fetchone()
    if run is None:
        raise ValueError(f"unknown run {run_id}")
    pipeline_version = run["pipeline_version"]
    for article in connection.execute("SELECT * FROM article WHERE selected=1 ORDER BY bank_number,entry_ordinal"):
        source = json.loads(article["raw_json"])
        units = extract_article_units(source, pipeline_version)
        pointers = {unit.pointer for unit in units}
        fingerprint = structural_fingerprint(source, pointers)
        connection.execute(
            "INSERT OR REPLACE INTO run_article(run_id,article_id,structural_fingerprint) VALUES (?,?,?)",
            (run_id, article["id"], fingerprint),
        )
        if not units:
            quarantined += 1
        for unit in units:
            source_hash = sha256_bytes(unit.source_text.encode())
            unit_id = f"u-r{run_id}-{article['id']}-{sha256_bytes(unit.pointer.encode())[:12]}"
            connection.execute(
                """INSERT OR IGNORE INTO translation_unit
                (id,run_id,article_id,json_pointer,role,source_text,source_sha256,protected_tokens_json,byte_count,status)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (unit_id, run_id, article["id"], unit.pointer, unit.role, unit.source_text, source_hash,
                 json.dumps(unit.protected_tokens, ensure_ascii=False), len(unit.source_text.encode()), "ready"),
            )
            added += connection.execute("SELECT changes()").fetchone()[0]
    audit(connection, "extract_units", "run", run_id, {"added": added, "articles_without_units": quarantined})
    return {"units_added": added, "articles_without_units": quarantined}
