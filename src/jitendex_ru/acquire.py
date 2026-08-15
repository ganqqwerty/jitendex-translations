from __future__ import annotations

import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import Config
from .util import sha256_file


class ChecksumError(RuntimeError):
    pass


def _download(url: str, target: Path, attempts: int = 3) -> None:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "jp-ru-kolobok-dictionary/0.1"})
            with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            return
        except (OSError, urllib.error.URLError) as error:
            last_error = error
            target.unlink(missing_ok=True)
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    assert last_error is not None
    raise last_error


def acquire(config: Config) -> list[Path]:
    downloads = config.work_dir / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    acquired: list[Path] = []
    for kind in ("jitendex", "kaishi"):
        spec = config.raw[kind]
        target = downloads / spec["filename"]
        if not target.exists():
            temporary = target.with_suffix(target.suffix + ".part")
            _download(spec["url"], temporary)
            temporary.replace(target)
        actual = sha256_file(target)
        if actual != spec["sha256"]:
            raise ChecksumError(f"{kind}: expected {spec['sha256']}, got {actual}")
        acquired.append(target)
    schema_dir = config.work_dir / "schemas" / "pinned-yomitan"
    schema_dir.mkdir(parents=True, exist_ok=True)
    for name, spec in config.raw.get("schemas", {}).items():
        target = schema_dir / spec["filename"]
        if not target.exists():
            temporary = target.with_suffix(target.suffix + ".part")
            _download(spec["url"], temporary)
            temporary.replace(target)
        actual = sha256_file(target)
        if actual != spec["sha256"]:
            raise ChecksumError(f"schema {name}: expected {spec['sha256']}, got {actual}")
        acquired.append(target)
    return acquired
