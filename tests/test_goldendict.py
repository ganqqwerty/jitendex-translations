from io import BytesIO
from pathlib import PurePosixPath

import pytest
from PIL import Image

from jitendex_ru.goldendict import ALLOWED_TAGS, _GoldenTagVerifier, _write_resource, render_content


def test_renders_structured_content_and_internal_links_safely():
    node = {
        "tag": "div",
        "data": {
            "class": "extra-box", "content": "xref", "code": "n",
            "sentence-key": "example-1", "source": "Jitendex", "source-type": "dictionary",
        },
        "content": [
            {"tag": "a", "href": "?query=食べる&wildcards=off", "content": "食べる <eat>"},
            {"tag": "a", "href": "https://www.edrdg.org/", "content": "JMdict"},
            {"tag": "ruby", "content": ["食", {"tag": "rt", "content": "た"}]},
            {
                "tag": "img", "path": "jitendex/graphics/example.svg", "alt": "diagram",
                "appearance": "monochrome", "background": False,
            },
        ],
    }
    rendered = render_content(node)
    assert 'class="extra-box sc-xref"' in rendered
    assert 'data-sc-code="n"' in rendered
    assert 'data-sc-sentence-key="example-1"' in rendered
    assert 'data-sc-source="Jitendex"' in rendered
    assert 'data-sc-source-type="dictionary"' in rendered
    assert 'href="bword://%E9%A3%9F%E3%81%B9%E3%82%8B"' in rendered
    assert 'href="https://www.edrdg.org/"' in rendered
    assert "食べる &lt;eat&gt;" in rendered
    assert "<ruby>食<rt>た</rt></ruby>" in rendered
    assert 'src="jitendex/graphics/example.svg"' in rendered
    assert 'alt="diagram"' in rendered
    assert 'class="gloss-image image-monochrome"' in rendered
    assert 'data-sc-appearance="monochrome"' in rendered
    assert 'data-sc-background="false"' in rendered


@pytest.mark.parametrize("tag", sorted(ALLOWED_TAGS - {"img"}))
def test_renders_every_structured_content_tag(tag):
    rendered = render_content({"tag": tag, "content": "value"})
    if tag == "br":
        assert rendered == "<br>"
    else:
        assert rendered == f"<{tag}>value</{tag}>"


def test_preserves_table_list_and_collapsible_image_semantics():
    table = render_content({
        "tag": "table", "content": {"tag": "tr", "content": {
            "tag": "th", "colSpan": 2, "rowSpan": 3, "content": "форма",
        }},
    })
    assert '<th colspan="2" rowspan="3">форма</th>' in table
    styled = render_content({"tag": "li", "style": {"listStyleType": '"①"'}, "content": "первый"})
    assert 'style="list-style-type:&quot;①&quot;"' in styled
    image = render_content({
        "tag": "img", "path": "image.png", "alt": "схема", "collapsible": True,
        "collapsed": True, "background": True, "width": 20, "height": 10, "sizeUnits": "px",
    })
    assert '<details class="gloss-image-container">' in image
    assert "<summary>схема</summary>" in image
    assert 'style="width:20px;height:10px"' in image
    assert "image-background" in image
    assert 'data-sc-collapsible="true"' in image
    assert 'data-sc-collapsed="true"' in image
    assert 'data-sc-size-units="px"' in image


def test_rewrites_and_transcodes_avif_to_png(tmp_path):
    source = BytesIO()
    Image.new("RGBA", (3, 2), (20, 80, 160, 128)).save(source, format="AVIF", quality=100)
    source.seek(0)
    destination = tmp_path / "image.png"
    assert _write_resource(source, PurePosixPath("graphics/image.avif"), destination)
    with Image.open(destination) as converted:
        assert converted.format == "PNG"
        assert converted.size == (3, 2)
    rendered = render_content(
        {"tag": "img", "path": "graphics/image.avif"},
        {"graphics/image.avif": "graphics/image.png"},
    )
    assert 'src="graphics/image.png"' in rendered
    assert ".avif" not in rendered


def test_verifies_approved_embedded_tags_and_hover_badges():
    catalog = {
        "embedded": {("part-of-speech-info", "n"): {
            "label_ru": "сущ.", "description_ru": "Существительное",
        }},
        "tag_bank": {"priority\u00a0form": {
            "label_ru": "приор. форма",
            "description_ru": "Написание или чтение с высоким приоритетом",
        }},
    }
    verifier = _GoldenTagVerifier(catalog)
    verifier.feed(
        '<span data-sc-class="tag" data-sc-content="part-of-speech-info" '
        'data-sc-code="n" title="Существительное">сущ.</span>'
        '<span class="jr-tag" title="Написание или чтение с высоким приоритетом">'
        'приор. форма</span>'
    )
    verifier.finish()
    assert verifier.embedded_tag_occurrences == 1
    assert verifier.tag_bank_references == 1

    bad = _GoldenTagVerifier(catalog)
    with pytest.raises(ValueError, match="tooltip differs"):
        bad.feed(
            '<span data-sc-class="tag" data-sc-content="part-of-speech-info" '
            'data-sc-code="n" title="noun">сущ.</span>'
        )
