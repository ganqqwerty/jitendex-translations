from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any


def validate_archive(path: Path, schema_dir: Path) -> dict[str, int]:
    try:
        import fastjsonschema
    except ImportError as error:  # pragma: no cover - packaging guarantees this dependency
        raise RuntimeError("fastjsonschema is required for pinned Yomitan schema validation") from error
    index_schema = json.loads((schema_dir / "dictionary-index-schema.json").read_text(encoding="utf-8"))
    term_schema = json.loads((schema_dir / "dictionary-term-bank-v3-schema.json").read_text(encoding="utf-8"))
    index_validator = fastjsonschema.compile(index_schema)
    term_validator = fastjsonschema.compile(term_schema)
    banks = 0
    with zipfile.ZipFile(path) as archive:
        index_validator(json.loads(archive.read("index.json")))
        for name in archive.namelist():
            if re.fullmatch(r"term_bank_\d+\.json", name):
                term_validator(json.loads(archive.read(name)))
                banks += 1
    return {"schema_validated_banks": banks}
