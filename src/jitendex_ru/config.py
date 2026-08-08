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

    def model(self, kind: str) -> dict[str, str]:
        """Return the explicitly configured effective model for a batch kind."""
        if kind not in {"translation", "review"}:
            raise ValueError(f"unsupported model kind: {kind}")
        spec = self.raw["models"][kind]
        model_id = spec.get("id")
        reasoning_effort = spec.get("reasoning_effort")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError(f"models.{kind}.id must be a non-empty string")
        if reasoning_effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError(f"models.{kind}.reasoning_effort is invalid")
        return {"id": model_id, "reasoning_effort": reasoning_effort}
