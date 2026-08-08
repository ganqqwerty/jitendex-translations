import pytest

from jitendex_ru.pilot import ArticleMetric, _select_article_metrics


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
