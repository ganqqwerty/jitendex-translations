from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    root: Path
    raw: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "Config":
        resolved = path.resolve()
        return cls(resolved.parent, tomllib.loads(resolved.read_text(encoding="utf-8")))

    def path(self, section: str, key: str) -> Path:
        value = Path(self.raw[section][key])
        return value if value.is_absolute() else self.root / value

    @property
    def work_dir(self) -> Path:
        return self.path("project", "work_dir")

    @property
    def dist_dir(self) -> Path:
        return self.path("project", "dist_dir")

    @property
    def db_path(self) -> Path:
        return self.work_dir / "progress.sqlite3"

