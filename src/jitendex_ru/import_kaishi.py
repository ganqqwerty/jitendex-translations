from __future__ import annotations

from .database import ConnectionLike

import sqlite3
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .db import audit
from .util import canonical_json, nfc, sha256_bytes


FIELD_SEPARATOR = "\x1f"
REQUIRED_FIELDS = ("Word", "Word Reading", "Word Meaning", "Sentence", "Sentence Meaning")


def split_fields(raw: str, names: list[str]) -> dict[str, str]:
    values = raw.split(FIELD_SEPARATOR)
    if len(values) < len(names):
        values.extend([""] * (len(names) - len(values)))
    return {name: nfc(values[index]) for index, name in enumerate(names)}


def _collection_from_apkg(apkg: Path, temporary: Path) -> Path:
    with zipfile.ZipFile(apkg) as archive:
        candidates = [name for name in archive.namelist() if name.startswith("collection.anki")]
        if not candidates:
            raise ValueError("APKG has no Anki collection")
        name = sorted(candidates, key=lambda item: (not item.endswith("21b"), item))[0]
        compressed = temporary / Path(name).name
        compressed.write_bytes(archive.read(name))
    if compressed.suffix == ".anki21b":
        output = temporary / "collection.sqlite3"
        subprocess.run(["zstd", "-d", "-q", "-f", str(compressed), "-o", str(output)], check=True)
        return output
    return compressed


def import_kaishi(connection: ConnectionLike, snapshot_id: int, apkg: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="kaishi-import-") as directory:
        collection = _collection_from_apkg(apkg, Path(directory))
        source = sqlite3.connect(f"file:{collection}?mode=ro", uri=True)
        source.row_factory = sqlite3.Row
        models = source.execute("SELECT models FROM col").fetchone()[0]
        if models.strip():
            import json

            model_map = json.loads(models)
            field_names: dict[int, list[str]] = {
                int(model_id): [item["name"] for item in sorted(model["flds"], key=lambda item: item["ord"])]
                for model_id, model in model_map.items()
            }
        else:
            field_names = {}
            for row in source.execute("SELECT ntid,ord,name FROM fields ORDER BY ntid,ord"):
                field_names.setdefault(row["ntid"], []).append(row["name"])
        count = 0
        for row in source.execute("SELECT id, mid, flds FROM notes ORDER BY id"):
            fields = split_fields(row["flds"], field_names[row["mid"]])
            if (
                not all(name in fields for name in REQUIRED_FIELDS)
                or not fields["Word"]
                or not fields["Word Reading"]
                or not fields["Word Meaning"]
            ):
                continue
            payload = {name: fields[name] for name in REQUIRED_FIELDS}
            cursor = connection.execute(
                """INSERT INTO kaishi_note
                (snapshot_id,note_id,word,reading,meaning_en,sentence_ja,sentence_en,source_sha256)
                VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(snapshot_id,note_id) DO NOTHING""",
                (snapshot_id, row["id"], payload["Word"], payload["Word Reading"], payload["Word Meaning"],
                 payload["Sentence"], payload["Sentence Meaning"], sha256_bytes(canonical_json(payload))),
            )
            count += cursor.rowcount
        source.close()
    audit(connection, "import", "source_snapshot", snapshot_id, {"kind": "kaishi", "notes_added": count})
    return count
