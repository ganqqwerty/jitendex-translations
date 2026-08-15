from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path


BUILD_SITE_PATH = Path(__file__).parents[1] / "terra-luna-site" / "build_site.py"
SPEC = importlib.util.spec_from_file_location("terra_luna_build_site", BUILD_SITE_PATH)
assert SPEC is not None and SPEC.loader is not None
BUILD_SITE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD_SITE)


def test_metadata_markup_has_social_card_and_schema() -> None:
    markup = BUILD_SITE.metadata_markup("Сравнение", "Описание", "/jpdb-top-5k/")

    canonical_url = (
        "https://ganqqwerty.github.io/jp-ru-kolobok-dictionary/"
        "comparison/jpdb-top-5k/"
    )
    assert f'<link rel="canonical" href="{canonical_url}">' in markup
    assert '<meta name="twitter:card" content="summary_large_image">' in markup
    assert '<meta property="og:image:width" content="1724">' in markup
    assert BUILD_SITE.SOCIAL_IMAGE_URL in markup

    match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>',
        markup,
        flags=re.DOTALL,
    )
    assert match is not None
    structured_data = json.loads(match.group(1))
    assert structured_data["@type"] == "WebPage"
    assert structured_data["url"] == canonical_url
    assert structured_data["about"]["@id"].endswith("/#dictionary")


def test_refresh_metadata_preserves_page_body_and_is_idempotent(tmp_path: Path) -> None:
    page = tmp_path / "sample" / "index.html"
    page.parent.mkdir()
    page.write_text(
        """<!doctype html>
<html><head>
  <meta name="description" content="Описание">
  <title>Заголовок</title>
</head><body><p>Не менять</p></body></html>
""",
        encoding="utf-8",
    )

    BUILD_SITE.refresh_metadata(tmp_path)
    first = page.read_text(encoding="utf-8")
    BUILD_SITE.refresh_metadata(tmp_path)

    assert page.read_text(encoding="utf-8") == first
    assert "<p>Не менять</p>" in first
    assert "/comparison/sample/" in first
    assert first.count("<!-- SOCIAL-METADATA:START -->") == 1


def test_checked_in_pages_have_unique_canonical_urls_and_valid_schema() -> None:
    project_root = Path(__file__).parents[1]
    pages = [project_root / "site-home" / "index.html"]
    pages.extend(
        page
        for page in (project_root / "terra-luna-site").rglob("index.html")
        if "dist" not in page.relative_to(project_root / "terra-luna-site").parts
    )
    canonical_urls: set[str] = set()

    for page in pages:
        source = page.read_text(encoding="utf-8")
        canonical_match = re.search(r'<link rel="canonical" href="([^"]+)">', source)
        schema_matches = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>',
            source,
            flags=re.DOTALL,
        )
        assert canonical_match is not None, page
        assert canonical_match.group(1) not in canonical_urls, page
        assert len(schema_matches) == 1, page
        assert source.count('<meta property="og:image"') == 1, page
        assert BUILD_SITE.SOCIAL_IMAGE_URL in source, page
        json.loads(schema_matches[0])
        canonical_urls.add(canonical_match.group(1))

    assert len(pages) == 39
