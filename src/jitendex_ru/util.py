from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any


CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")
MIXED_ALPHABET_RE = re.compile(
    r"(?:[A-Za-z][\u0400-\u04ff]|[\u0400-\u04ff][A-Za-z])"
)
TAG_RE = re.compile(r"<\/?[A-Za-z][^>]*>|```|\[[^\]]+\]\([^)]+\)")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ASCII_WORD_RE = re.compile(r"\b[A-Za-z]{3,}\b")
LATIN_BINOMIAL_RE = re.compile(
    r"(?P<prefix>^|[;(,]\s*)"
    r"(?P<taxon>[A-Z][a-z]{2,}\s+[a-z][a-z-]{2,})\b"
)
LATIN_TAXON_RE = re.compile(
    r"(?<=\()[A-Z][a-z]+(?:\s+[a-z][a-z-]+){1,2}"
    r"(?:\s+(?:subsp|ssp|var|f)\.\s+[a-z][a-z-]+"
    r"|\s+(?:x|×)\s+[A-Z]\.\s+[a-z][a-z-]+)?"
    r"(?=\s*(?:[;,)]))"
)
LANGUAGE_ORIGIN_RE = re.compile(r'^[A-Za-z]+:\s*"([^"]+)"$')
KEY_CHORD_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:\+[A-Za-z][A-Za-z0-9]*)+\b")
JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")

NON_TAXON_EPITHETS = frozenset({
    "a", "an", "and", "code", "coordinates", "dynasty", "heaven", "law",
    "paper", "people", "period", "pilgrim", "pilgrimage", "school", "sea",
    "style", "treat", "wheel",
})
NON_TAXON_GENERA = frozenset({
    "akihabara", "cartesian", "chinese", "dalmatian", "dutch", "english",
    "german", "islamic", "japanese", "kamakura", "korin", "morse", "muromachi",
    "qin", "scythian", "shikoku", "tusita",
})


def source_xref_taxa(source_text: str) -> list[str]:
    """Conservatively find Latin binomials that a cross-reference must retain."""
    matches = list(LATIN_BINOMIAL_RE.finditer(source_text))
    genera = [match.group("taxon").split()[0] for match in matches]
    taxa: list[str] = []
    for match in matches:
        taxon = match.group("taxon")
        genus, epithet = taxon.split()
        if genus.lower() in NON_TAXON_GENERA or epithet.lower() in NON_TAXON_EPITHETS:
            continue
        prefix = match.group("prefix").strip()
        if prefix in {"(", ","} or genera.count(genus) > 1:
            taxa.append(taxon)
    return list(dict.fromkeys(taxa))


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def reading_variants(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).strip()
    parts = re.split(r"[・/／,、]\s*", normalized)
    variants: list[str] = []
    for part in parts:
        hira = "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in part)
        if hira and hira not in variants:
            variants.append(hira)
    return tuple(variants)


def json_pointer_escape(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def json_pointer_get(value: Any, pointer: str) -> Any:
    current = value
    if not pointer:
        return current
    for raw in pointer.removeprefix("/").split("/"):
        segment = raw.replace("~1", "/").replace("~0", "~")
        current = current[int(segment)] if isinstance(current, list) else current[segment]
    return current


def json_pointer_set(value: Any, pointer: str, replacement: Any) -> None:
    segments = pointer.removeprefix("/").split("/")
    current = value
    for raw in segments[:-1]:
        segment = raw.replace("~1", "/").replace("~0", "~")
        current = current[int(segment)] if isinstance(current, list) else current[segment]
    final = segments[-1].replace("~1", "/").replace("~0", "~")
    if isinstance(current, list):
        current[int(final)] = replacement
    else:
        current[final] = replacement


def structural_fingerprint(value: Any, pointers: set[str], path: str = "") -> str:
    def mask(node: Any, current: str) -> Any:
        if current in pointers:
            return {"$translation_unit": True}
        if isinstance(node, list):
            return [mask(item, f"{current}/{index}") for index, item in enumerate(node)]
        if isinstance(node, dict):
            return {
                key: mask(item, f"{current}/{json_pointer_escape(key)}")
                for key, item in node.items()
            }
        return node

    return sha256_bytes(canonical_json(mask(value, path)))
