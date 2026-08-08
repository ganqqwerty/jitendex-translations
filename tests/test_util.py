from jitendex_ru.util import json_pointer_get, json_pointer_set, reading_variants, structural_fingerprint


def test_reading_variants_normalize_width_katakana_and_alternatives():
    assert reading_variants("ナニ・なん") == ("なに", "なん")
    assert reading_variants("ﾊﾟﾝ") == ("ぱん",)


def test_json_pointer_round_trip_and_structural_mask():
    source = {"a/b": [{"content": "English", "lang": "en"}]}
    pointer = "/a~1b/0/content"
    before = structural_fingerprint(source, {pointer})
    json_pointer_set(source, pointer, "Русский")
    assert json_pointer_get(source, pointer) == "Русский"
    assert structural_fingerprint(source, {pointer}) == before
    source["a/b"][0]["tag"] = "span"
    assert structural_fingerprint(source, {pointer}) != before

