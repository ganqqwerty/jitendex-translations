from pathlib import Path


HOMEPAGE = Path(__file__).parents[1] / "site-home" / "index.html"


def test_manabu_card_matches_requested_dictionary_entry() -> None:
    source = HOMEPAGE.read_text(encoding="utf-8")

    assert '<div class="term" lang="ja"><ruby>学<rt>まな</rt></ruby>ぶ</div>' in source
    assert '<span class="dict-tag">гл. годан</span>' in source
    assert '<span class="dict-tag">гл. перех.</span>' in source
    assert '<span>учиться</span><span>изучать</span><span>брать уроки</span>' in source
    assert (
        'いくつになっても<span class="example-keyword">'
        '<ruby>学<rt>まな</rt></ruby>ぶ</span>ことはある'
    ) in source
    assert "Учиться никогда не поздно." in source
