from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .batch import _article_envelope, _manifest
from .util import atomic_write, canonical_json, sha256_bytes


HIGH_RISK_ROLES = {"glossary_set", "label", "example", "pos"}
DEFAULT_ROLE_TARGETS = {
    "glossary_set": 110,
    "label": 110,
    "example": 110,
    "pos": 110,
    "tooltip": 100,
    "note": 100,
    "xref_gloss": 100,
    "register": 100,
}
KANA_ONLY_RE = re.compile(r"[\u3040-\u30ffー]+")


@dataclass(frozen=True)
class ArticleMetric:
    article_id: int
    serialized_bytes: int
    unit_count: int
    role_counts: Mapping[str, int]
    features: frozenset[str]


def _stable_order(metric: ArticleMetric) -> str:
    return sha256_bytes(f"luna-pilot-v1:{metric.article_id}".encode())


def _select_article_metrics(
    metrics: list[ArticleMetric], *, min_units: int = 1500,
    role_targets: Mapping[str, int] = DEFAULT_ROLE_TARGETS,
) -> set[int]:
    if not metrics:
        raise ValueError("cannot select a pilot from an empty run")
    selected: set[int] = set()

    def add(metric: ArticleMetric) -> None:
        selected.add(metric.article_id)

    for metric in metrics:
        if "oversize_24k" in metric.features:
            add(metric)
    by_size = sorted(metrics, key=lambda item: (item.serialized_bytes, item.article_id))
    for index in (0, len(by_size) // 2, int((len(by_size) - 1) * 0.95), len(by_size) - 1):
        add(by_size[index])
    add(max(metrics, key=lambda item: (item.unit_count, -item.article_id)))

    required_features = {
        "single_sense", "multi_sense", "japanese_examples", "protected_tokens",
        "numbers_or_identifiers", "kana_only", "forms", "xref", "antonym",
        "sense_note", "lang_source", "culture_or_domain",
    }
    for feature in sorted(required_features):
        candidates = [metric for metric in metrics if feature in metric.features]
        if candidates:
            add(min(candidates, key=_stable_order))

    def counts() -> Counter[str]:
        result: Counter[str] = Counter()
        for metric in metrics:
            if metric.article_id in selected:
                result.update(metric.role_counts)
        return result

    current_roles = counts()
    for role, target in role_targets.items():
        candidates = sorted(
            (metric for metric in metrics if metric.role_counts.get(role, 0)),
            key=lambda item: (-item.role_counts.get(role, 0), _stable_order(item)),
        )
        for metric in candidates:
            if current_roles[role] >= target:
                break
            if metric.article_id not in selected:
                add(metric)
                current_roles.update(metric.role_counts)
        if current_roles[role] < target:
            raise ValueError(f"pilot cannot reach role target for {role}: {current_roles[role]}/{target}")

    total_units = sum(metric.unit_count for metric in metrics if metric.article_id in selected)
    for metric in sorted(metrics, key=_stable_order):
        if total_units >= min_units:
            break
        if metric.article_id not in selected:
            add(metric)
            total_units += metric.unit_count
    if total_units < min_units:
        raise ValueError(f"pilot cannot reach minimum units: {total_units}/{min_units}")
    return selected


def build_pilot_selection(
    connection: sqlite3.Connection, run_id: int, terminology: dict[str, str],
    *, protocol_sha256: str, min_units: int = 1500,
) -> dict[str, Any]:
    run = connection.execute("SELECT * FROM run WHERE id=?", (run_id,)).fetchone()
    if run is None:
        raise ValueError(f"unknown run {run_id}")
    grouped: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for unit in connection.execute(
        "SELECT * FROM translation_unit WHERE run_id=? ORDER BY article_id,json_pointer", (run_id,)
    ):
        grouped[unit["article_id"]].append(unit)
    articles = {row["id"]: row for row in connection.execute("SELECT * FROM article WHERE selected=1")}
    metrics: list[ArticleMetric] = []
    for article_id, units in sorted(grouped.items()):
        article = articles[article_id]
        envelope = _article_envelope(connection, article, units)
        serialized_bytes = len(_manifest("b-" + "0" * 24, [envelope], terminology)[1])
        role_counts = Counter(unit["role"] for unit in units)
        context = envelope["read_only_context"]
        senses = context.get("senses", [])
        inventory = {item["element"] for item in context.get("preservation_inventory", [])}
        protected = [token for unit in units for token in json.loads(unit["protected_tokens_json"])]
        source_text = " ".join(unit["source_text"] for unit in units)
        features: set[str] = set()
        if serialized_bytes > 24576:
            features.add("oversize_24k")
        if len(senses) == 1:
            features.add("single_sense")
        elif len(senses) > 1:
            features.add("multi_sense")
        if "example-sentence-a" in inventory:
            features.add("japanese_examples")
        if protected:
            features.add("protected_tokens")
        if any(character.isdigit() for character in source_text) or any("{" in token for token in protected):
            features.add("numbers_or_identifiers")
        if KANA_ONLY_RE.fullmatch(article["expression"]):
            features.add("kana_only")
        for inventory_feature, feature in {
            "forms": "forms", "xref": "xref", "antonym": "antonym",
            "sense-note": "sense_note", "lang-source": "lang_source",
        }.items():
            if inventory_feature in inventory:
                features.add(feature)
        if role_counts.get("label", 0) or role_counts.get("register", 0) or role_counts.get("note", 0):
            features.add("culture_or_domain")
        metrics.append(ArticleMetric(
            article_id, serialized_bytes, len(units), dict(role_counts), frozenset(features)
        ))

    selected_ids = _select_article_metrics(metrics, min_units=min_units)
    selected_metrics = [metric for metric in metrics if metric.article_id in selected_ids]
    selected_metrics.sort(key=lambda item: item.article_id)
    roles: Counter[str] = Counter()
    features: Counter[str] = Counter()
    for metric in selected_metrics:
        roles.update(metric.role_counts)
        features.update(metric.features)
    articles_payload = [
        {
            "article_id": metric.article_id,
            "serialized_bytes": metric.serialized_bytes,
            "unit_count": metric.unit_count,
            "role_counts": dict(sorted(metric.role_counts.items())),
            "features": sorted(metric.features),
        }
        for metric in selected_metrics
    ]
    payload: dict[str, Any] = {
        "protocol": "luna-pilot-v1",
        "protocol_sha256": protocol_sha256,
        "run_id": run_id,
        "pipeline": run["pipeline_version"],
        "minimum_units": min_units,
        "role_targets": DEFAULT_ROLE_TARGETS,
        "article_count": len(selected_metrics),
        "unit_count": sum(metric.unit_count for metric in selected_metrics),
        "role_counts": dict(sorted(roles.items())),
        "feature_article_counts": dict(sorted(features.items())),
        "articles": articles_payload,
    }
    payload["selection_sha256"] = sha256_bytes(canonical_json(payload))
    return payload


def write_pilot_selection(path: Path, payload: dict[str, Any]) -> None:
    atomic_write(path, canonical_json(payload) + b"\n")
