from __future__ import annotations

import json
import resource
import sys
import time
from contextlib import contextmanager
from typing import Any, Iterator


def peak_memory_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == "darwin" else value * 1024


class PrepMetrics:
    def __init__(self, component: str):
        self.component = component
        self.phases: dict[str, dict[str, Any]] = {}

    @contextmanager
    def phase(self, name: str, **counts: Any) -> Iterator[dict[str, Any]]:
        wall_started = time.monotonic()
        cpu_started = time.process_time()
        result = dict(counts)
        self.progress(name, "started", **counts)
        try:
            yield result
        finally:
            result.update({
                "wall_seconds": round(time.monotonic() - wall_started, 6),
                "cpu_seconds": round(time.process_time() - cpu_started, 6),
                "peak_memory_bytes": peak_memory_bytes(),
            })
            self.phases[name] = result
            self.progress(name, "completed", **result)

    def progress(self, phase: str, state: str, **details: Any) -> None:
        print(json.dumps({
            "event": "run_prep_progress", "component": self.component,
            "phase": phase, "state": state, **details,
        }, ensure_ascii=False, sort_keys=True), file=sys.stderr, flush=True)

    def record(self, name: str, wall_seconds: float, cpu_seconds: float, **counts: Any) -> None:
        result = {
            **counts, "wall_seconds": round(wall_seconds, 6),
            "cpu_seconds": round(cpu_seconds, 6), "peak_memory_bytes": peak_memory_bytes(),
        }
        self.phases[name] = result
        self.progress(name, "completed", **result)
