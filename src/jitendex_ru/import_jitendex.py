from __future__ import annotations

import json
import re
import sqlite3
import zipfile
from pathlib import Path

from .db import audit
from .util import canonical_json, sha256_bytes


TERM_BANK_RE = re.compile(r"^term_bank_(\d+)\.json$")


def import_jitendex(connection: sqlite3.Connection, snapshot_id: int, archive_path: Path) -> int:
    added = 0
    with zipfile.ZipFile(archive_path) as archive:
        banks = sorted(
            ((int(match.group(1)), name) for name in archive.namelist() if (match := TERM_BANK_RE.match(name))),
            key=lambda item: item[0],
        )
        for bank_number, name in banks:
            rows = json.loads(archive.read(name))
            for ordinal, row in enumerate(rows):
                if not isinstance(row, list) or len(row) < 8 or not isinstance(row[6], int):
                    continue
                raw = canonical_json(row)
                connection.execute(
                    """INSERT OR IGNORE INTO article
                    (snapshot_id,bank_number,entry_ordinal,expression,reading,sequence,raw_json,source_sha256)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (snapshot_id, bank_number, ordinal, row[0], row[1], row[6], raw.decode(), sha256_bytes(raw)),
                )
                added += connection.execute("SELECT changes()").fetchone()[0]
    audit(connection, "import", "source_snapshot", snapshot_id, {"kind": "jitendex", "articles_added": added})
    return added
