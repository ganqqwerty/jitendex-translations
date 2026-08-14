from __future__ import annotations

import json
import re
import zipfile
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from .attribution import PRODUCT_NAME
from .build_dictionary import MEDIA_SUFFIXES, _frequency_metadata, materialize_run
from .database import ConnectionLike
from .jitendex_tags import (
    count_tag_bank_references,
    load_approved_tag_catalog,
    localize_embedded_tags,
    localize_tag_bank_rows,
)

TAG_BANK_RE = re.compile(r"^tag_bank_(\d+)\.json$")


def stable_text_key(value: str) -> tuple[bytes, bytes]:
    """Return the project-wide locale-independent UTF-8 ordering key."""
    raw = value.encode("utf-8")
    folded = bytes(byte + 32 if 65 <= byte <= 90 else byte for byte in raw)
    return folded, raw


def safe_resource_path(value: str) -> PurePosixPath:
    if "\x00" in value or "\\" in value:
        raise ValueError(f"unsafe media path {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe media path {value!r}")
    return path


def _paths(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if (
                key in {"path", "src"}
                and isinstance(value, str)
                and Path(value).suffix.lower() in MEDIA_SUFFIXES
            ):
                yield value
            else:
                yield from _paths(value)
    elif isinstance(node, list):
        for value in node:
            yield from _paths(value)


@dataclass(frozen=True, slots=True)
class ExportVariant:
    reading: str
    definition_tags: str
    rules: str
    score: int | float
    glossary: tuple[Any, ...]
    sequence: int | str
    term_tags: str

    @property
    def tag_codes(self) -> tuple[str, ...]:
        return tuple(
            code
            for field in (self.definition_tags, self.term_tags)
            for code in field.split(" ")
            if code
        )


@dataclass(frozen=True, slots=True)
class ExportEntry:
    expression: str
    identity: str
    variants: tuple[ExportVariant, ...]
    readings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExportResource:
    source_path: PurePosixPath


@dataclass(frozen=True, slots=True)
class ExportCorpus:
    run_id: int
    snapshot_id: int
    source_archive: Path
    source_sha256: str
    title: str
    description: str
    entries: tuple[ExportEntry, ...]
    resources: tuple[ExportResource, ...]
    tag_mapping: Mapping[str, Mapping[str, str]]
    tag_catalog_version: str
    tag_catalog_sha256: str
    embedded_summary: Mapping[str, Any]
    tag_bank_references: int

    @property
    def article_count(self) -> int:
        return sum(len(entry.variants) for entry in self.entries)


def _entry_identity(expression: str) -> str:
    from hashlib import sha256

    return "e-" + sha256(expression.encode("utf-8")).hexdigest()[:24]


def _validate_text(value: str, label: str, *, allow_empty: bool = True) -> None:
    if "\x00" in value:
        raise ValueError(f"{label} contains NUL")
    if not allow_empty and not value:
        raise ValueError(f"{label} is empty")


def entries_from_rows(rows: Sequence[Sequence[Any]]) -> tuple[ExportEntry, ...]:
    """Normalize localized Yomitan rows without flattening their glossary trees."""
    groups: dict[str, list[ExportVariant]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 8:
            raise ValueError("invalid Yomitan term row")
        expression = row[0]
        if not isinstance(expression, str):
            raise ValueError("invalid Yomitan term row expression")  # noqa: TRY004
        _validate_text(expression, "expression", allow_empty=False)
        reading = row[1]
        definition_tags = row[2]
        rules = row[3]
        term_tags = row[7]
        if not all(isinstance(value, str) for value in (reading, definition_tags, rules, term_tags)):
            raise ValueError(f"invalid string field for {expression!r}")
        _validate_text(reading, "reading")
        score = row[4]
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ValueError(f"invalid score for {expression!r}")  # noqa: TRY004
        glossary = row[5]
        if isinstance(glossary, list):
            glossary_items = tuple(glossary)
        elif isinstance(glossary, (dict, str, int, float)) and not isinstance(glossary, bool):
            glossary_items = (glossary,)
        else:
            raise ValueError(f"invalid glossary for {expression!r}")  # noqa: TRY004
        sequence = row[6]
        if not isinstance(sequence, (int, str)) or isinstance(sequence, bool):
            raise ValueError(f"invalid sequence for {expression!r}")  # noqa: TRY004
        groups[expression].append(ExportVariant(
            reading=reading,
            definition_tags=definition_tags,
            rules=rules,
            score=score,
            glossary=glossary_items,
            sequence=sequence,
            term_tags=term_tags,
        ))
    entries: list[ExportEntry] = []
    for expression in sorted(groups, key=stable_text_key):
        variants = tuple(groups[expression])
        readings = tuple(dict.fromkeys(
            variant.reading
            for variant in variants
            if variant.reading and variant.reading != expression
        ))
        entries.append(ExportEntry(
            expression=expression,
            identity=_entry_identity(expression),
            variants=variants,
            readings=readings,
        ))
    if not entries:
        raise ValueError("selection is empty")
    return tuple(entries)


def prepare_export(connection: ConnectionLike, run_id: int) -> ExportCorpus:
    """Materialize one run and normalize its rich source into the shared model."""
    run, source_row, rows = materialize_run(connection, run_id)
    catalog = load_approved_tag_catalog(connection, run["jitendex_snapshot_id"])
    embedded = localize_embedded_tags(rows, catalog)
    with zipfile.ZipFile(source_row["local_path"]) as source:
        source_names = set(source.namelist())
        tag_bank_names = sorted(
            (name for name in source_names if TAG_BANK_RE.fullmatch(name)),
            key=lambda name: int(TAG_BANK_RE.fullmatch(name).group(1)),
        )
        source_tag_rows = [
            row
            for name in tag_bank_names
            for row in json.loads(source.read(name))
        ]
        _localized_rows, tag_mapping = localize_tag_bank_rows(source_tag_rows, catalog)
        references = count_tag_bank_references(rows, tag_mapping)
        resource_paths = sorted(
            {safe_resource_path(path) for row in rows for path in _paths(row)},
            key=lambda path: stable_text_key(path.as_posix()),
        )
        missing = [path.as_posix() for path in resource_paths if path.as_posix() not in source_names]
        if missing:
            raise ValueError(f"missing referenced media {missing[0]}")
    frequency_metadata = _frequency_metadata(connection, run_id)
    title = frequency_metadata[0] if frequency_metadata else PRODUCT_NAME
    description = frequency_metadata[2] if frequency_metadata else (
        "Производный русскоязычный словарь на основе Jitendex. "
        "Атрибуция Jitendex/JMdict/Tatoeba и условия CC BY-SA 4.0 сохранены."
    )
    return ExportCorpus(
        run_id=run_id,
        snapshot_id=run["jitendex_snapshot_id"],
        source_archive=Path(source_row["local_path"]),
        source_sha256=source_row["sha256"],
        title=title,
        description=description,
        entries=entries_from_rows(rows),
        resources=tuple(ExportResource(path) for path in resource_paths),
        tag_mapping=MappingProxyType({
            code: MappingProxyType(dict(item)) for code, item in tag_mapping.items()
        }),
        tag_catalog_version=catalog["version"],
        tag_catalog_sha256=catalog["source_sha256"],
        embedded_summary=MappingProxyType(dict(embedded)),
        tag_bank_references=references,
    )
