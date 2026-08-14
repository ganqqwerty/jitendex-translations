from __future__ import annotations

import os
import re
import shutil
import tempfile
import zipfile
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from PIL import Image, ImageOps

from .build_dictionary import FIXED_ZIP_TIME
from .database import ConnectionLike
from .db import audit
from .export_model import (
    ExportCorpus,
    ExportResource,
    safe_resource_path,
    stable_text_key,
)
from .util import canonical_json, sha256_bytes, sha256_file

Fidelity = Literal["exact", "lossless-transform", "degraded", "omitted"]
FIDELITY_LEVELS: tuple[Fidelity, ...] = (
    "exact", "lossless-transform", "degraded", "omitted",
)
INVALID_XML_RE = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]"
)
CLASS_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def require_xml_text(value: str, label: str = "text") -> str:
    match = INVALID_XML_RE.search(value)
    if match:
        raise ValueError(f"{label} contains invalid XML character U+{ord(match.group()):04X}")
    return value


def class_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = CLASS_RE.sub("-", value).strip("-")
    return cleaned or None


def walk_rich_nodes(node: Any) -> Iterator[Any]:
    yield node
    if isinstance(node, dict):
        if node.get("type") == "structured-content" or "content" in node:
            yield from walk_rich_nodes(node.get("content"))
    elif isinstance(node, list):
        for item in node:
            yield from walk_rich_nodes(item)


@dataclass(slots=True)
class LossLedger:
    target: str
    _counts: Counter[tuple[str, Fidelity, str]] = field(default_factory=Counter)

    def record(
        self, feature: str, fidelity: Fidelity, count: int = 1, note: str = "",
    ) -> None:
        if fidelity not in FIDELITY_LEVELS:
            raise ValueError(f"invalid fidelity {fidelity!r}")
        if count < 0:
            raise ValueError("loss count cannot be negative")
        if count:
            self._counts[(feature, fidelity, note)] += count

    def merge(self, other: LossLedger) -> None:
        if self.target != other.target:
            raise ValueError("cannot merge ledgers for different targets")
        self._counts.update(other._counts)

    def as_dict(self) -> dict[str, Any]:
        items = [
            {"feature": feature, "fidelity": fidelity, "count": count, **({"note": note} if note else {})}
            for (feature, fidelity, note), count in sorted(
                self._counts.items(),
                key=lambda item: (item[0][1], stable_text_key(item[0][0]), stable_text_key(item[0][2])),
            )
        ]
        totals = {
            fidelity: sum(item["count"] for item in items if item["fidelity"] == fidelity)
            for fidelity in FIDELITY_LEVELS
        }
        return {"target": self.target, "totals": totals, "items": items}

    def require_no_omissions(self) -> None:
        omitted = sum(
            count for (_feature, fidelity, _note), count in self._counts.items()
            if fidelity == "omitted"
        )
        if omitted:
            raise ValueError(f"{self.target} loss ledger contains {omitted} omitted items")


def target_resource_path(source: PurePosixPath) -> PurePosixPath:
    return source.with_suffix(".png") if source.suffix.lower() == ".avif" else source


def resource_mapping(resources: Iterable[ExportResource]) -> dict[str, str]:
    mapping = {
        resource.source_path.as_posix(): target_resource_path(resource.source_path).as_posix()
        for resource in resources
    }
    if len(mapping) != len(set(mapping.values())):
        raise ValueError("media paths collide after AVIF-to-PNG conversion")
    return mapping


def _write_resource(source: Any, source_path: PurePosixPath, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source_path.suffix.lower() != ".avif":
        with destination.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
        return False
    try:
        with Image.open(source) as image:
            converted = ImageOps.exif_transpose(image)
            converted.load()
            options: dict[str, Any] = {"compress_level": 9, "optimize": False}
            icc_profile = image.info.get("icc_profile")
            if isinstance(icc_profile, bytes):
                options["icc_profile"] = icc_profile
            converted.save(destination, format="PNG", **options)
    except (OSError, ValueError) as error:
        raise ValueError(
            f"failed to transcode AVIF resource {source_path}; Pillow with AVIF support is required"
        ) from error
    return True


def materialize_resources(
    corpus: ExportCorpus,
    destination: Path,
    *,
    prefix: PurePosixPath | None = None,
) -> tuple[dict[str, str], int]:
    prefix = PurePosixPath() if prefix is None else prefix
    mapping = resource_mapping(corpus.resources)
    converted = 0
    with zipfile.ZipFile(corpus.source_archive) as archive:
        names = set(archive.namelist())
        for resource in corpus.resources:
            source_name = resource.source_path.as_posix()
            if source_name not in names:
                raise ValueError(f"missing referenced media {source_name}")
            output_relative = safe_resource_path(mapping[source_name])
            target_relative = prefix / output_relative
            target = destination.joinpath(*target_relative.parts)
            with archive.open(source_name) as source:
                converted += int(_write_resource(source, resource.source_path, target))
    return mapping, converted


def file_manifest(paths: Iterable[tuple[str, Path]]) -> list[dict[str, Any]]:
    return [
        {"path": name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for name, path in sorted(paths, key=lambda item: stable_text_key(item[0]))
    ]


def write_deterministic_zip(output: Path, paths: Iterable[tuple[str, Path]]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
            for name, path in sorted(paths, key=lambda item: stable_text_key(item[0])):
                safe_resource_path(name)
                info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def write_manifest_file(
    path: Path,
    corpus: ExportCorpus,
    *,
    format_name: str,
    capability_profile: str,
    files: list[dict[str, Any]],
    ledger: LossLedger,
    tools: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    ledger.require_no_omissions()
    manifest = {
        "schema_version": 1,
        "format": format_name,
        "capability_profile": capability_profile,
        "run_id": corpus.run_id,
        "source_archive_sha256": corpus.source_sha256,
        "tag_catalog_version": corpus.tag_catalog_version,
        "tag_catalog_sha256": corpus.tag_catalog_sha256,
        "articles": corpus.article_count,
        "headwords": len(corpus.entries),
        "resources": len(corpus.resources),
        "files": files,
        "loss_ledger": ledger.as_dict(),
        "tools": dict(tools or {}),
    }
    path.write_bytes(canonical_json(manifest) + b"\n")
    return manifest


def record_export(
    connection: ConnectionLike,
    corpus: ExportCorpus,
    output: Path,
    manifest: list[dict[str, Any]],
    *,
    format_name: str,
    details: Mapping[str, Any] | None = None,
) -> tuple[int, str]:
    manifest_hash = sha256_bytes(canonical_json(manifest))
    output_hash = sha256_file(output)
    cursor = connection.execute(
        """INSERT INTO export(run_id,output_path,manifest_sha256,zip_sha256)
        VALUES (?,?,?,?) RETURNING id""",
        (corpus.run_id, str(output), manifest_hash, output_hash),
    )
    export_id = cursor.fetchone()[0]
    connection.executemany(
        "INSERT INTO export_file(export_id,path,sha256,byte_count) VALUES (?,?,?,?)",
        ((export_id, item["path"], item["sha256"], item["bytes"]) for item in manifest),
    )
    audit(connection, f"{format_name}_build", "export", export_id, {
        "output": str(output), "zip_sha256": output_hash, "format": format_name,
        **dict(details or {}),
    })
    return export_id, output_hash


def verify_recorded_export(
    connection: ConnectionLike, path: Path,
) -> tuple[Any, str]:
    output_hash = sha256_file(path)
    export = connection.execute(
        """SELECT e.id,e.run_id,r.jitendex_snapshot_id FROM export e
        JOIN run r ON r.id=e.run_id
        WHERE e.output_path=? AND e.zip_sha256=? ORDER BY e.id DESC LIMIT 1""",
        (str(path), output_hash),
    ).fetchone()
    if export is None:
        raise ValueError("package has no matching export record")
    return export, output_hash


def verify_zip_members(
    archive: zipfile.ZipFile,
    *,
    required: set[str],
) -> list[str]:
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError("duplicate ZIP members")
    for name in names:
        safe_resource_path(name)
    missing = required - set(names)
    if missing:
        raise ValueError(f"missing package members: {sorted(missing)}")
    return names


def zip_member_sha256(archive: zipfile.ZipFile, name: str) -> str:
    digest = sha256()
    with archive.open(name) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
