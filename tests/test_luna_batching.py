import pytest

from jitendex_ru.batch import _manifest, _pack_envelopes, _required_tag_terminology


def _article(article_id: str, sources: list[str]) -> dict:
    return {
        "article_id": article_id,
        "source_sha256": f"hash-{article_id}",
        "term": "月",
        "reading": "つき",
        "sequence": int(article_id.removeprefix("a-")),
        "kaishi_evidence": [],
        "read_only_context": {},
        "units": [
            {
                "unit_id": f"u-{article_id}-{index}",
                "source_sha256": f"unit-hash-{article_id}-{index}",
                "role": "glossary",
                "protected_tokens": [],
                "local_context": "glossary",
                "source_text": source,
            }
            for index, source in enumerate(sources)
        ],
    }


def _article_of_serialized_size(article_id: str, target_bytes: int) -> dict:
    article = _article(article_id, [""])
    base_bytes = len(_manifest("b-" + "0" * 24, [article], {})[1])
    payload_bytes = target_bytes - base_bytes
    assert payload_bytes >= 0
    multibyte_characters, ascii_characters = divmod(payload_bytes, len("月".encode()))
    article["units"][0]["source_text"] = "月" * multibyte_characters + "x" * ascii_characters
    return article


def _pack(envelopes: list[dict], **overrides: int) -> list[list[dict]]:
    limits = {
        "soft_max_articles": 6,
        "soft_max_bytes": 24_576,
        "soft_max_units": 100,
        "singleton_threshold_bytes": 16_384,
        "hard_max_article_bytes": 49_152,
        "hard_max_article_units": 200,
    }
    limits.update(overrides)
    return _pack_envelopes(envelopes, {}, **limits)


def test_approved_tag_terminology_selects_compact_label_and_full_tooltip():
    source = [None, None, None, None, None, [{
        "data": {"class": "tag", "content": "part-of-speech-info", "code": "v5b"},
        "content": "5-dan -bu", "title": "Godan verb with 'bu' ending",
    }]]
    catalog = {("part-of-speech-info", "v5b"): {
        "label_ru": "гл. годан на ぶ", "description_ru": "Глагол годан с окончанием на «ぶ».",
    }}

    label = _required_tag_terminology(source, "/5/0/content", catalog)
    tooltip = _required_tag_terminology(source, "/5/0/title", catalog)

    assert label["target_text"] == "гл. годан на ぶ"
    assert tooltip["target_text"] == "Глагол годан с окончанием на «ぶ»."


def test_tag_without_approved_terminology_does_not_stop_intermediate_batch():
    source = [None, None, None, None, None, [{
        "data": {"class": "tag", "content": "part-of-speech-info", "code": "v5b"},
        "content": "5-dan -bu",
    }]]

    assert _required_tag_terminology(source, "/5/0/content", {}) is None


def test_article_over_soft_byte_cap_is_valid_ordered_singleton():
    oversized = _article_of_serialized_size("a-2", 34_780)
    serialized = _manifest("b-" + "0" * 24, [oversized], {})[1]
    assert len(serialized) == 34_780
    assert len(serialized.decode()) < len(serialized)

    batches = _pack([_article("a-1", ["small"]), oversized, _article("a-3", ["small"])])

    assert [[article["article_id"] for article in batch] for batch in batches] == [
        ["a-1"], ["a-2"], ["a-3"]
    ]


def test_article_over_hard_byte_ceiling_is_rejected():
    article = _article_of_serialized_size("a-1", 34_780)

    with pytest.raises(ValueError, match=r"article a-1 exceeds a hard article limit"):
        _pack([article], hard_max_article_bytes=34_779)


def test_article_over_soft_unit_cap_is_valid_singleton():
    oversized = _article("a-2", ["unit"] * 3)

    batches = _pack(
        [_article("a-1", ["unit"]), oversized, _article("a-3", ["unit"])],
        soft_max_units=2,
        hard_max_article_units=3,
        singleton_threshold_bytes=49_152,
    )

    assert [[article["article_id"] for article in batch] for batch in batches] == [
        ["a-1"], ["a-2"], ["a-3"]
    ]


def test_article_over_hard_unit_ceiling_is_rejected():
    article = _article("a-1", ["unit"] * 3)

    with pytest.raises(ValueError, match=r"article a-1 exceeds a hard article limit"):
        _pack([article], soft_max_units=2, hard_max_article_units=2, singleton_threshold_bytes=49_152)
