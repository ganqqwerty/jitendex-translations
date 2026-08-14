from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os


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
        benchmark = os.environ.get("JITENDEX_BENCHMARK_WORK_DIR")
        if benchmark:
            return Path(benchmark).resolve()
        return self.path("project", "work_dir")

    @property
    def dist_dir(self) -> Path:
        benchmark = os.environ.get("JITENDEX_BENCHMARK_DIST_DIR")
        if benchmark:
            return Path(benchmark).resolve()
        return self.path("project", "dist_dir")

    @property
    def db_path(self) -> Path:
        benchmark = os.environ.get("JITENDEX_BENCHMARK_DATABASE")
        if benchmark:
            return Path(benchmark).resolve()
        database = self.raw.get("database", {})
        value = database.get("sqlite_path")
        if value is None:
            return self.work_dir / "progress.sqlite3"
        path = Path(value)
        return path if path.is_absolute() else self.root / path

    @property
    def db_backend(self) -> str:
        backend = os.environ.get(
            "JITENDEX_BENCHMARK_DATABASE_BACKEND",
            self.raw.get("database", {}).get("backend", "sqlite"),
        )
        if backend not in {"sqlite", "postgresql"}:
            raise ValueError("database.backend must be 'sqlite' or 'postgresql'")
        return backend

    @property
    def db_pool_max(self) -> int:
        value = int(self.raw.get("database", {}).get("pool_max", 4))
        if value < 1:
            raise ValueError("database.pool_max must be positive")
        return value

    @property
    def db_checkout_timeout(self) -> float:
        value = float(self.raw.get("database", {}).get("checkout_timeout_seconds", 10))
        if value <= 0:
            raise ValueError("database.checkout_timeout_seconds must be positive")
        return value

    def database_url(self) -> str:
        database = self.raw.get("database", {})
        env_name = database.get("url_env")
        if not isinstance(env_name, str) or not env_name:
            raise ValueError("database.url_env must name the PostgreSQL URL environment variable")
        value = os.environ.get(env_name)
        if not value:
            raise ValueError(f"PostgreSQL URL environment variable is not set: {env_name}")
        return value

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
