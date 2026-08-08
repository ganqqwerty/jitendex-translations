import json

import pytest

from jitendex_ru.pilot import ArticleMetric, _select_article_metrics, load_pilot_selection
from jitendex_ru.util import canonical_json, sha256_bytes


def metric(article_id, units, roles, *features):
    return ArticleMetric(article_id, 1000 + article_id, units, roles, frozenset(features))


def test_pilot_selector_meets_role_targets_units_and_mandatory_features():
    metrics = [
        metric(1, 10, {"a": 10}, "oversize_24k", "kana_only"),
        metric(2, 10, {"b": 10}, "multi_sense"),
        metric(3, 10, {"a": 5, "b": 5}, "protected_tokens"),
        metric(4, 10, {"a": 10}, "single_sense"),
        metric(5, 10, {"b": 10}, "japanese_examples"),
    ]

    selected = _select_article_metrics(metrics, min_units=40, role_targets={"a": 15, "b": 15})

    assert 1 in selected
    assert sum(item.unit_count for item in metrics if item.article_id in selected) >= 40
    assert sum(item.role_counts.get("a", 0) for item in metrics if item.article_id in selected) >= 15
    assert sum(item.role_counts.get("b", 0) for item in metrics if item.article_id in selected) >= 15


def test_pilot_selector_fails_when_role_floor_is_impossible():
    metrics = [metric(1, 5, {"a": 5})]

    with pytest.raises(ValueError, match="cannot reach role target"):
        _select_article_metrics(metrics, min_units=5, role_targets={"a": 6})


def test_pilot_selection_loader_verifies_hash_and_unique_articles(tmp_path):
    payload = {"articles": [{"article_id": 1}], "unit_count": 1}
    payload["selection_sha256"] = sha256_bytes(canonical_json(payload))
    path = tmp_path / "pilot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert load_pilot_selection(path)["articles"][0]["article_id"] == 1
    payload["unit_count"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_pilot_selection(path)
