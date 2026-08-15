#!/usr/bin/env python3
"""Build the static, paginated Jitendex translation demo site."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import sqlite3
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

SITE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SITE_ROOT.parent
DATABASE_PATH = PROJECT_ROOT / "work" / "progress.sqlite3"
LUNA_ZIP = PROJECT_ROOT / "dist" / "jitendex-kaishi-ru-luna-clean-v1.zip"
CLAUDE_ZIP = Path("/Users/iuriikatkov/Downloads/jitendex-kaishi-ru-inline.zip")
PAGE_SIZE = 100
NEW_INCREMENT_PREVIEW_LIMIT = 1_000
RUN_ID = 2
TOP_5K_RUN_ID = 5
JPDB_INCREMENT_DEMOS = (
    (6, 5, "jpdb-5k-to-10k", "JPDB 5k–10k", "5,001–10,000", "top 5k", "top 10k"),
    (7, 6, "jpdb-10k-to-20k", "JPDB 10k–20k", "10,001–20,000", "top 10k", "top 20k"),
    (8, 7, "jpdb-20k-to-30k", "JPDB 20k–30k", "20,001–30,000", "top 20k", "top 30k"),
    (9, 8, "jpdb-30k-to-40k", "JPDB 30k–40k", "30,001–40,000", "top 30k", "top 40k"),
    (10, 9, "jpdb-40k-to-50k", "JPDB 40k–50k", "40,001–50,000", "top 40k", "top 50k"),
    (11, 10, "jpdb-50k-to-60k", "JPDB 50k–60k", "50,001–60,000", "top 50k", "top 60k"),
    (12, 11, "jpdb-60k-to-70k", "JPDB 60k–70k", "60,001–70,000", "top 60k", "top 70k"),
    (13, 12, "jpdb-70k-to-80k", "JPDB 70k–80k", "70,001–80,000", "top 70k", "top 80k"),
    (14, 13, "jpdb-80k-to-90k", "JPDB 80k–90k", "80,001–90,000", "top 80k", "top 90k"),
    (15, 14, "jpdb-90k-to-100k", "JPDB 90k–100k", "90,001–100,000", "top 90k", "top 100k"),
)
ZIP_SAMPLE_SIZE = 100
LEGACY_SAMPLE_DEMOS = (
    {
        "slug": "articles-216368-to-226368",
        "nav_label": "Статьи 216,369–226,368",
        "manifest": {
            "slug": "articles-216368-to-226368",
            "range": "216,369–226,368 статей",
            "increment_entries": 10_000,
            "samples": 100,
            "archive": "jitendex-articles-226368-ru-luna-v4.zip",
            "archive_sha256": "75fe600adc4790363ac28da54a4547a42196a15e7ea4a274af4b8b62d5e6cfaa",
        },
    },
)


def jpdb_archive(scope: int) -> Path:
    provenance = "luna-clean-v1" if scope <= 140_000 else "luna-v4"
    return PROJECT_ROOT / "dist" / f"jitendex-jpdb-{scope // 1000}k-ru-{provenance}.zip"


def article_archive(scope: int) -> Path:
    suffix = "-tags-ru-v1" if scope == 433_885 else ""
    return PROJECT_ROOT / "dist" / f"jitendex-articles-{scope}-ru-luna-v4{suffix}.zip"


ZIP_SAMPLE_DEMOS: list[dict[str, Any]] = [
    {
        "slug": "jpdb-top-5k",
        "nav_label": "JPDB top 5k",
        "rank_label": "1–5,000",
        "previous": None,
        "current": jpdb_archive(5_000),
    },
    {
        "slug": "jpdb-5k-to-10k",
        "nav_label": "JPDB 5k–10k",
        "rank_label": "5,001–10,000",
        "previous": jpdb_archive(5_000),
        "current": jpdb_archive(10_000),
    },
]
for current_scope in range(20_000, 300_001, 10_000):
    previous_scope = current_scope - 10_000
    ZIP_SAMPLE_DEMOS.append({
        "slug": f"jpdb-{previous_scope // 1000}k-to-{current_scope // 1000}k",
        "nav_label": f"JPDB {previous_scope // 1000}k–{current_scope // 1000}k",
        "rank_label": f"{previous_scope + 1:,}–{current_scope:,}",
        "previous": jpdb_archive(previous_scope),
        "current": jpdb_archive(current_scope),
    })
ARTICLE_SAMPLE_RANGES = (
    (226_368, 276_368),
    (276_368, 326_368),
    (326_368, 376_368),
    (376_368, 426_368),
    (426_368, 433_885),
)
for previous_scope, current_scope in ARTICLE_SAMPLE_RANGES:
    ZIP_SAMPLE_DEMOS.append({
        "slug": f"articles-{previous_scope}-to-{current_scope}",
        "nav_label": f"Статьи {previous_scope + 1:,}–{current_scope:,}",
        "rank_label": f"статьи {previous_scope + 1:,}–{current_scope:,}",
        "previous": article_archive(previous_scope),
        "current": article_archive(current_scope),
    })

sys.path.insert(0, str(PROJECT_ROOT / "src"))
from jitendex_ru.apply_translations import apply_article  # noqa: E402
from jitendex_ru.db import connect  # noqa: E402


ALLOWED_TAGS = {
    "a", "div", "li", "ol", "ruby", "rt", "span", "table", "tbody",
    "td", "th", "thead", "tr", "ul", "br",
}


def load_dictionary(path: Path) -> tuple[list[list[Any]], str]:
    rows: list[list[Any]] = []
    with zipfile.ZipFile(path) as archive:
        names = sorted(
            name for name in archive.namelist()
            if name.startswith("term_bank_") and name.endswith(".json")
        )
        for name in names:
            rows.extend(json.loads(archive.read(name)))
        styles = archive.read("styles.css").decode("utf-8") if "styles.css" in archive.namelist() else ""
    return rows, styles


def numbered_bank_names(archive: zipfile.ZipFile, prefix: str = "term_bank") -> list[str]:
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)\.json$")
    matches: list[tuple[int, str]] = []
    for name in archive.namelist():
        match = pattern.match(name)
        if match:
            matches.append((int(match.group(1)), name))
    return [name for _, name in sorted(matches)]


def iter_dictionary_rows(path: Path):
    with zipfile.ZipFile(path) as archive:
        for name in numbered_bank_names(archive):
            yield from json.loads(archive.read(name))


def dictionary_row_key(row: list[Any]) -> tuple[str, str, int]:
    if len(row) < 7 or not isinstance(row[0], str) or not isinstance(row[1], str):
        raise ValueError("Invalid Yomitan term row")
    return row[0], row[1], int(row[6])


def archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dictionary_lookup(rows: list[list[Any]]) -> tuple[dict[tuple[str, str, int], list[Any]], dict[int, list[Any]]]:
    exact = {(row[0], row[1], row[6]): row for row in rows}
    grouped: dict[int, list[list[Any]]] = defaultdict(list)
    for row in rows:
        grouped[row[6]].append(row)
    unique_sequence = {sequence: values[0] for sequence, values in grouped.items() if len(values) == 1}
    return exact, unique_sequence


def find_row(
    exact: dict[tuple[str, str, int], list[Any]],
    unique_sequence: dict[int, list[Any]],
    expression: str,
    reading: str,
    sequence: int,
) -> list[Any] | None:
    return exact.get((expression, reading, sequence)) or unique_sequence.get(sequence)


def attr_name(name: str) -> str:
    parts = name.replace("_", "-").split("-")
    return "data-sc-" + "-".join(part.lower() for part in parts)


def css_name(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def render_node(node: Any) -> str:
    if node is None:
        return ""
    if isinstance(node, (str, int, float)):
        return html.escape(str(node))
    if isinstance(node, list):
        return "".join(render_node(item) for item in node)
    if not isinstance(node, dict):
        return html.escape(str(node))

    if node.get("type") == "structured-content":
        return render_node(node.get("content"))

    tag = node.get("tag")
    if tag not in ALLOWED_TAGS:
        return render_node(node.get("content"))

    attributes: list[tuple[str, str]] = []
    for key in ("href", "lang", "title"):
        value = node.get(key)
        if value is not None:
            attributes.append((key, str(value)))
    style = node.get("style")
    if isinstance(style, dict):
        attributes.append(("style", ";".join(f"{css_name(str(key))}:{value}" for key, value in style.items())))
    elif style is not None:
        attributes.append(("style", str(style)))
    for source, target in (("colSpan", "colspan"), ("rowSpan", "rowspan")):
        if source in node:
            attributes.append((target, str(node[source])))
    for key, value in (node.get("data") or {}).items():
        attributes.append((attr_name(str(key)), str(value)))
    if tag == "a":
        attributes.extend((("target", "_blank"), ("rel", "noreferrer")))
    serialized = "".join(
        f' {name}="{html.escape(value, quote=True)}"' for name, value in attributes
    )
    if tag == "br":
        return f"<br{serialized}>"
    return f"<{tag}{serialized}>{render_node(node.get('content'))}</{tag}>"


def render_entry(row: list[Any] | None, expression: str, reading: str) -> str:
    heading = f'<span class="expression" lang="ja">{html.escape(expression)}</span>'
    if reading and reading != expression:
        heading += f'<span class="entry-reading" lang="ja">{html.escape(reading)}</span>'
    if row is None:
        content = '<p class="missing-entry">Нет статьи в этом словаре.</p>'
    else:
        content = render_node(row[5])
    return f'<article class="yomitan-entry"><div class="entry-heading">{heading}</div><div class="definition-list">{content}</div></article>'


def render_row(
    article: sqlite3.Row,
    entries: list[list[Any] | None],
    column_keys: tuple[str, ...],
) -> str:
    expression = article["expression"]
    reading = article["reading"]
    if len(column_keys) != len(entries):
        raise ValueError("Each comparison column must have exactly one entry")
    cells = []
    for column, entry in zip(column_keys, entries):
        cells.append(f'<td data-compare-column="{column}">{render_entry(entry, expression, reading)}</td>')
    search = f"{expression} {reading}".strip()
    return (
        f'<tr class="comparison-row" data-term-id="{article["id"]}" '
        f'data-search-title="{html.escape(search, quote=True)}">'
        + "".join(cells)
        + "</tr>"
    )


APP_CSS = r"""
:root { color-scheme: light; --canvas: #f1f3f5; --fg: #222; --text-color: #222; --background-color: #fff; --font-size-no-units: 14; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--canvas); color: var(--fg); font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", sans-serif; }
.page { width: min(1800px, calc(100% - 24px)); margin: 0 auto; padding: 24px 0 48px; }
.page-title { margin: 0 0 14px; font-size: 18px; font-weight: 600; }
.page-description { max-width: 860px; margin: -2px 0 18px; color: var(--muted, #596168); font-size: 15px; }
.demo-nav { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 18px; }
.demo-nav a { padding: 6px 10px; border: 1px solid #b8bec5; border-radius: 999px; background: #fff; color: #384047; text-decoration: none; }
.demo-nav a:hover { border-color: #1a73e8; color: #1a73e8; }
.demo-nav a[aria-current="page"] { border-color: #1a73e8; background: #e8f0fe; color: #174ea6; font-weight: 600; }
.term-search { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 0 0 12px; }
.term-search label { color: #4b5157; font-size: 13px; font-weight: 600; }
.term-search input { width: min(360px, 100%); padding: 8px 10px; border: 1px solid #b8bec5; border-radius: 6px; background: #fff; color: #222; font: inherit; }
.term-search input:focus, .pagination select:focus, .pagination button:focus { outline: 2px solid #1a73e8; outline-offset: 1px; }
.term-search-status { color: #70757a; font-size: 12px; white-space: nowrap; }
.column-picker { display: flex; flex-wrap: wrap; gap: 8px 18px; align-items: center; margin: 0 0 14px; padding: 10px 12px; border: 1px solid #cfd3d8; border-radius: 6px; background: #fff; }
.column-picker legend { padding: 0 5px; color: #60666c; font-size: 12px; font-weight: 600; }
.column-picker label { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; user-select: none; }
.column-picker input { margin: 0; accent-color: #1a73e8; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 10px; margin: 14px 0; }
.pagination button, .pagination select { min-height: 36px; padding: 7px 11px; border: 1px solid #b8bec5; border-radius: 6px; background: #fff; color: #222; font: inherit; }
.pagination button { cursor: pointer; }
.pagination button:disabled { cursor: default; opacity: .45; }
.pagination[hidden] { display: none; }
.table-shell { min-height: 180px; overflow-x: auto; border: 1px solid #cfd3d8; border-radius: 6px; background: #fff; }
.comparison-table { display: block; width: 100%; border-collapse: collapse; }
.comparison-table > thead, .comparison-table > tbody { display: block; }
.comparison-table > thead > tr, .comparison-table > tbody > tr.comparison-row { display: grid; grid-template-columns: repeat(var(--visible-columns), minmax(0, 1fr)); }
.comparison-table > thead > tr > th { position: sticky; top: 0; z-index: 2; padding: 9px 14px; border-bottom: 1px solid #cfd3d8; background: #e9ecef; color: #4b5157; text-align: left; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.comparison-table > thead > tr > th + th, .comparison-table > tbody > tr > td + td { border-left: 1px solid #cfd3d8; }
.comparison-table > tbody > tr > td { padding: 14px 16px 18px; vertical-align: top; border-top: 1px solid #dfe2e5; }
.comparison-table > tbody > tr:first-child > td { border-top: 0; }
.comparison-table > tbody > tr:nth-child(even) > td { background: #fafbfc; }
.comparison-table [hidden] { display: none !important; }
.entry-heading { display: flex; align-items: baseline; gap: .65em; margin: 0 0 .45em; padding-bottom: .35em; border-bottom: 1px solid #e4e6e8; }
.expression { font-family: "Hiragino Kaku Gothic ProN", "Yu Gothic", "Noto Sans JP", sans-serif; font-size: 1.65em; font-weight: 500; }
.entry-reading { color: #60666c; font-size: 1.05em; }
.definition-list { overflow-wrap: anywhere; }
.definition-list > div { margin-bottom: .3em; }
.missing-entry { color: #777; font-style: italic; }
.loading-row td { padding: 44px 16px !important; color: #70757a; text-align: center; }
.yomitan-entry a { color: #1a73e8; text-decoration: none; }
.yomitan-entry a:hover { text-decoration: underline; }
.yomitan-entry table { border-collapse: collapse; }
.yomitan-entry th, .yomitan-entry td { border: 1px solid #b9bec4; padding: .15em .35em; }
@media (max-width: 700px) { .page { width: calc(100% - 12px); padding-top: 10px; } .comparison-table > tbody > tr > td { padding: 10px; } }
"""


APP_JS = r"""
(() => {
  const PAGE_SIZE = __PAGE_SIZE__;
  const pageCount = __PAGE_COUNT__;
  const totalCount = __TOTAL_COUNT__;
  const terms = __SEARCH_INDEX__;
  const table = document.querySelector('.comparison-table');
  const tableBody = table.querySelector('tbody');
  const searchInput = document.querySelector('#term-search-input');
  const searchStatus = document.querySelector('#term-search-status');
  const pagers = [...document.querySelectorAll('.pagination')];
  const toggles = [...document.querySelectorAll('[data-column-toggle]')];
  const cache = new Map();
  let currentPage = Math.min(pageCount, Math.max(1, Number(new URL(location.href).searchParams.get('page')) || 1));
  let requestVersion = 0;

  const normalize = (value) => value.normalize('NFKC').trim().toLocaleLowerCase('ja');
  const htmlEscape = (value) => String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[character]);
  const pagePath = (page) => `data/page-${String(page).padStart(3, '0')}.html`;
  const setLoading = () => { tableBody.innerHTML = '<tr class="loading-row"><td colspan="__COLUMN_COUNT__">Загрузка…</td></tr>'; };
  const getPage = async (page) => {
    if (!cache.has(page)) cache.set(page, fetch(pagePath(page)).then((response) => {
      if (!response.ok) throw new Error(`Page ${page} failed: ${response.status}`);
      return response.text();
    }));
    return cache.get(page);
  };
  const syncColumns = () => {
    const visible = toggles.filter((toggle) => toggle.checked);
    if (!visible.length) { toggles[0].checked = true; return syncColumns(); }
    table.style.setProperty('--visible-columns', String(visible.length));
    table.style.minWidth = `${Math.max(420, visible.length * 420)}px`;
    toggles.forEach((toggle) => {
      document.querySelectorAll(`[data-compare-column="${toggle.dataset.columnToggle}"]`)
        .forEach((cell) => { cell.hidden = !toggle.checked; });
    });
  };
  const syncPagers = () => pagers.forEach((pager) => {
    pager.hidden = Boolean(searchInput.value.trim());
    const select = pager.querySelector('select');
    select.value = String(currentPage);
    pager.querySelector('[data-page-prev]').disabled = currentPage === 1;
    pager.querySelector('[data-page-next]').disabled = currentPage === pageCount;
  });
  const showPage = async (page, pushState = true) => {
    const version = ++requestVersion;
    currentPage = Math.min(pageCount, Math.max(1, page));
    searchInput.value = '';
    setLoading();
    syncPagers();
    const content = await getPage(currentPage);
    if (version !== requestVersion) return;
    tableBody.innerHTML = content;
    const first = (currentPage - 1) * PAGE_SIZE + 1;
    const last = Math.min(totalCount, currentPage * PAGE_SIZE);
    searchStatus.textContent = `${first}–${last} / ${totalCount}`;
    syncColumns();
    if (pushState) history.pushState({page: currentPage}, '', `?page=${currentPage}`);
    scrollTo({top: 0, behavior: 'smooth'});
  };
  const showSearch = async () => {
    const version = ++requestVersion;
    const query = normalize(searchInput.value);
    syncPagers();
    if (!query) return showPage(currentPage, false);
    const matches = terms.filter((term) => term.search.includes(query));
    if (!matches.length) {
      tableBody.innerHTML = '<tr class="loading-row"><td colspan="__COLUMN_COUNT__">Ничего не найдено.</td></tr>';
      searchStatus.textContent = `0 / ${totalCount}`;
      return;
    }
    setLoading();
    const shown = matches.slice(0, PAGE_SIZE);
    const pages = [...new Set(shown.map((term) => term.page))];
    const documents = await Promise.all(pages.map(async (page) => {
      const template = document.createElement('template');
      template.innerHTML = await getPage(page);
      return template.content;
    }));
    if (version !== requestVersion) return;
    const ids = new Set(shown.map((term) => String(term.id)));
    const rows = documents.flatMap((document) => [...document.querySelectorAll('.comparison-row')])
      .filter((row) => ids.has(row.dataset.termId));
    const byId = new Map(rows.map((row) => [row.dataset.termId, row]));
    tableBody.replaceChildren(...shown.map((term) => byId.get(String(term.id))).filter(Boolean));
    searchStatus.textContent = matches.length > PAGE_SIZE
      ? `${PAGE_SIZE} из ${matches.length} совпадений`
      : `${matches.length} / ${totalCount}`;
    syncColumns();
  };

  pagers.forEach((pager) => {
    const select = pager.querySelector('select');
    for (let page = 1; page <= pageCount; page += 1) {
      const option = document.createElement('option');
      option.value = String(page);
      option.textContent = `Страница ${page} из ${pageCount}`;
      select.append(option);
    }
    select.addEventListener('change', () => showPage(Number(select.value)));
    pager.querySelector('[data-page-prev]').addEventListener('click', () => showPage(currentPage - 1));
    pager.querySelector('[data-page-next]').addEventListener('click', () => showPage(currentPage + 1));
  });
  toggles.forEach((toggle) => toggle.addEventListener('change', syncColumns));
  let searchTimer;
  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(showSearch, 120);
  });
  addEventListener('popstate', () => showPage(Number(new URL(location.href).searchParams.get('page')) || 1, false));
  showPage(currentPage, false).catch((error) => {
    tableBody.innerHTML = `<tr class="loading-row"><td colspan="__COLUMN_COUNT__">Не удалось загрузить страницу: ${htmlEscape(error.message)}</td></tr>`;
  });
})();
"""


def pagination_markup() -> str:
    return """<nav class="pagination" aria-label="Навигация по страницам">
      <button type="button" data-page-prev>← Назад</button>
      <select aria-label="Текущая страница"></select>
      <button type="button" data-page-next>Вперёд →</button>
    </nav>"""


def navigation_markup(active_path: str) -> str:
    links = [
        ("/", "Kaishi 1.5k"),
    ]
    links.extend((f'/{demo["slug"]}/', demo["nav_label"]) for demo in LEGACY_SAMPLE_DEMOS)
    links.extend((f'/{demo["slug"]}/', demo["nav_label"]) for demo in ZIP_SAMPLE_DEMOS)
    rendered = []
    for path, label in links:
        current = ' aria-current="page"' if path == active_path else ""
        rendered.append(f'<a href="{path}"{current}>{label}</a>')
    return '<nav class="demo-nav" aria-label="Наборы слов">' + "".join(rendered) + "</nav>"


def build_document(
    styles: str,
    search_index: list[dict[str, Any]],
    page_count: int,
    *,
    title: str,
    description: str,
    active_path: str,
    columns: tuple[tuple[str, str], ...],
) -> str:
    asset_prefix = ".." if active_path == "/" else "../.."
    comparison_href = "./" if active_path == "/" else "../"
    kaishi_note = (
        '<p class="page-description">Kaishi 1.5k был нашей испытательной площадкой: '
        'здесь мы пробовали разные модели и способы перевода. Luna при этом могла '
        'подглядывать в результат Terra и учитывать его. Ниже все варианты стоят '
        'рядом — можно самому сравнить, что получилось лучше.</p>'
        if active_path == "/"
        else ""
    )
    script = (
        APP_JS.replace("__PAGE_SIZE__", str(PAGE_SIZE))
        .replace("__PAGE_COUNT__", str(page_count))
        .replace("__TOTAL_COUNT__", str(len(search_index)))
        .replace("__SEARCH_INDEX__", json.dumps(search_index, ensure_ascii=False, separators=(",", ":")))
        .replace("__COLUMN_COUNT__", str(len(columns)))
    )
    toggles = "".join(
        f'<label><input type="checkbox" data-column-toggle="{key}" checked> {label}</label>'
        for key, label in columns
    )
    headers = "".join(
        f'<th scope="col" data-compare-column="{key}">{label}</th>'
        for key, label in columns
    )
    minimum_width = max(420, len(columns) * 420)
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#e8462a">
  <link rel="icon" href="{asset_prefix}/favicon.svg" type="image/svg+xml">
  <meta name="description" content="{html.escape(description, quote=True)}">
  <title>{html.escape(title)}</title>
  <style>{APP_CSS}\n{styles}</style>
  <link rel="stylesheet" href="{asset_prefix}/site-theme.css">
</head>
<body class="comparison-page">
  <header class="site-header wrap">
    <a class="brand" href="{asset_prefix}/"><span class="brand-mark">辞</span><span>Колобок 400k</span></a>
    <div class="header-actions">
      <nav class="site-nav" aria-label="Основная навигация">
        <a href="{asset_prefix}/">Главная</a>
        <a href="{comparison_href}" aria-current="page">Сравнение</a>
      </nav>
      <button class="theme-toggle" type="button" aria-label="Включить тёмную тему" aria-pressed="false" title="Включить тёмную тему"><span aria-hidden="true">☾</span></button>
    </div>
  </header>
  <main class="page">
    <div class="comparison-intro">
      <div class="eyebrow">Сравнение переводов</div>
      <h1 class="page-title">{html.escape(title)}</h1>
      {kaishi_note}
    </div>
    {navigation_markup(active_path)}
    <div class="term-search">
      <label for="term-search-input">Поиск</label>
      <input id="term-search-input" type="search" placeholder="Слово или чтение" autocomplete="off">
      <span class="term-search-status" id="term-search-status" aria-live="polite">1–{min(PAGE_SIZE, len(search_index))} / {len(search_index)}</span>
    </div>
    <fieldset class="column-picker">
      <legend>Показывать столбцы</legend>
      {toggles}
    </fieldset>
    {pagination_markup()}
    <div class="table-shell">
      <table class="comparison-table" style="--visible-columns:{len(columns)};min-width:{minimum_width}px">
        <thead><tr>{headers}</tr></thead>
        <tbody><tr class="loading-row"><td colspan="{len(columns)}">Загрузка…</td></tr></tbody>
      </table>
    </div>
    {pagination_markup()}
  </main>
  <footer class="site-footer wrap"><span>Колобок 400k · общественный словарный проект</span><span><a href="{asset_prefix}/">На главную</a> · <a href="https://github.com/ganqqwerty/jp-ru-kolobok-dictionary">GitHub</a></span></footer>
  <script src="{asset_prefix}/site-theme.js"></script>
  <script>{script}</script>
</body>
</html>
"""


def write_dataset(
    connection: sqlite3.Connection,
    output: Path,
    articles: list[sqlite3.Row],
    *,
    run_id: int,
    styles: str,
    title: str,
    description: str,
    active_path: str,
) -> dict[str, Any]:
    columns = (("original", "Original Jitendex (English)"), ("luna", "Luna clean v1"))
    data_dir = output / "data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True)
    search_index: list[dict[str, Any]] = []
    for offset in range(0, len(articles), PAGE_SIZE):
        page_number = offset // PAGE_SIZE + 1
        rendered = []
        for article in articles[offset:offset + PAGE_SIZE]:
            original = json.loads(article["raw_json"])
            luna = apply_article(connection, run_id, article)
            rendered.append(render_row(article, [original, luna], tuple(key for key, _ in columns)))
            search_index.append({
                "id": article["id"],
                "page": page_number,
                "search": f'{article["expression"]} {article["reading"]}'.strip().lower(),
            })
        (data_dir / f"page-{page_number:03d}.html").write_text("".join(rendered), encoding="utf-8")

    page_count = (len(articles) + PAGE_SIZE - 1) // PAGE_SIZE
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.html").write_text(
        build_document(
            styles,
            search_index,
            page_count,
            title=title,
            description=description,
            active_path=active_path,
            columns=columns,
        ),
        encoding="utf-8",
    )
    return {"articles": len(articles), "pages": page_count, "output": str(output)}


def write_zip_sample_dataset(
    output: Path,
    samples: list[list[Any]],
    originals: dict[tuple[str, str, int], list[Any]],
    *,
    styles: str,
    title: str,
    description: str,
    active_path: str,
) -> dict[str, Any]:
    columns = (("original", "Original Jitendex (English)"), ("russian", "Колобок 400k"))
    data_dir = output / "data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True)
    rendered: list[str] = []
    search_index: list[dict[str, Any]] = []
    for ordinal, translated in enumerate(samples, start=1):
        key = dictionary_row_key(translated)
        original = originals.get(key)
        if original is None:
            raise ValueError(f"Original Jitendex row is missing for {key!r}")
        article = {
            "id": f"sample-{ordinal}",
            "expression": translated[0],
            "reading": translated[1],
        }
        rendered.append(render_row(article, [original, translated], tuple(key for key, _ in columns)))
        search_index.append({
            "id": article["id"],
            "page": 1,
            "search": f'{article["expression"]} {article["reading"]}'.strip().lower(),
        })
    if len(samples) != ZIP_SAMPLE_SIZE:
        raise ValueError(f"Expected {ZIP_SAMPLE_SIZE} samples, received {len(samples)}")
    (data_dir / "page-001.html").write_text("".join(rendered), encoding="utf-8")
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.html").write_text(
        build_document(
            styles,
            search_index,
            1,
            title=title,
            description=description,
            active_path=active_path,
            columns=columns,
        ),
        encoding="utf-8",
    )
    return {"samples": len(samples), "pages": 1, "output": str(output)}


def build_zip_samples(output: Path) -> None:
    source_zip = PROJECT_ROOT / "work" / "downloads" / "jitendex-yomitan.zip"
    required = [source_zip]
    required.extend(demo["current"] for demo in ZIP_SAMPLE_DEMOS)
    required.extend(demo["previous"] for demo in ZIP_SAMPLE_DEMOS if demo["previous"] is not None)
    missing = sorted({str(path) for path in required if not path.is_file()})
    if missing:
        raise FileNotFoundError("Missing verified dictionary archives: " + ", ".join(missing))

    samples_by_slug: dict[str, list[list[Any]]] = {}
    manifest = [dict(demo["manifest"]) for demo in LEGACY_SAMPLE_DEMOS]
    needed_originals: set[tuple[str, str, int]] = set()
    cached_key_sets: dict[Path, set[tuple[str, str, int]]] = {}
    for demo in ZIP_SAMPLE_DEMOS:
        previous_path = demo["previous"]
        if previous_path is None:
            previous_keys: set[tuple[str, str, int]] = set()
        else:
            previous_keys = cached_key_sets.get(previous_path, set())
            if not previous_keys:
                previous_keys = {dictionary_row_key(row) for row in iter_dictionary_rows(previous_path)}
        current_keys: set[tuple[str, str, int]] = set()
        samples: list[list[Any]] = []
        increment_size = 0
        for row in iter_dictionary_rows(demo["current"]):
            key = dictionary_row_key(row)
            current_keys.add(key)
            if key not in previous_keys:
                increment_size += 1
                if len(samples) < ZIP_SAMPLE_SIZE:
                    samples.append(row)
                    needed_originals.add(key)
        cached_key_sets = {demo["current"]: current_keys}
        if increment_size < ZIP_SAMPLE_SIZE:
            raise ValueError(f'{demo["slug"]} has only {increment_size} new entries')
        samples_by_slug[demo["slug"]] = samples
        manifest.append({
            "slug": demo["slug"],
            "range": demo["rank_label"],
            "increment_entries": increment_size,
            "samples": len(samples),
            "archive": demo["current"].name,
            "archive_sha256": archive_sha256(demo["current"]),
        })

    originals: dict[tuple[str, str, int], list[Any]] = {}
    for row in iter_dictionary_rows(source_zip):
        key = dictionary_row_key(row)
        if key in needed_originals:
            originals[key] = row
    missing_originals = needed_originals - originals.keys()
    if missing_originals:
        raise ValueError(f"Missing {len(missing_originals)} sampled rows in English Jitendex")

    with zipfile.ZipFile(ZIP_SAMPLE_DEMOS[-1]["current"]) as latest_archive:
        styles = latest_archive.read("styles.css").decode("utf-8") if "styles.css" in latest_archive.namelist() else ""

    output.mkdir(parents=True, exist_ok=True)
    generated_slugs = {demo["slug"] for demo in ZIP_SAMPLE_DEMOS}
    for child in output.iterdir():
        if child.is_dir() and child.name in generated_slugs:
            shutil.rmtree(child)
    results: dict[str, dict[str, Any]] = {}
    for demo in ZIP_SAMPLE_DEMOS:
        results[demo["slug"]] = write_zip_sample_dataset(
            output / demo["slug"],
            samples_by_slug[demo["slug"]],
            originals,
            styles=styles,
            title=f'Jitendex English × Колобок 400k — {demo["rank_label"]} — 100 примеров',
            description=f'Сто примеров новых статей из проверенного словаря: {demo["rank_label"]}.',
            active_path=f'/{demo["slug"]}/',
        )

    root_index = output / "index.html"
    if root_index.is_file():
        root_html = root_index.read_text(encoding="utf-8")
        root_html, substitutions = re.subn(
            r'<nav class="demo-nav" aria-label="Наборы слов">.*?</nav>',
            navigation_markup("/"),
            root_html,
            count=1,
            flags=re.DOTALL,
        )
        if substitutions != 1:
            raise ValueError(f"Could not update navigation in {root_index}")
        root_index.write_text(root_html, encoding="utf-8")
    (output / "sample-manifest.json").write_text(
        json.dumps({"sample_size": ZIP_SAMPLE_SIZE, "datasets": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"datasets": results, "manifest": manifest}, ensure_ascii=False))


def build(output: Path) -> None:
    luna_rows, styles = load_dictionary(LUNA_ZIP)
    claude_rows, _ = load_dictionary(CLAUDE_ZIP)
    luna_exact, luna_by_sequence = dictionary_lookup(luna_rows)
    claude_exact, claude_by_sequence = dictionary_lookup(claude_rows)

    connection = connect(DATABASE_PATH)
    articles = connection.execute(
        """SELECT a.* FROM run_article ra JOIN article a ON a.id=ra.article_id
        WHERE ra.run_id=? ORDER BY a.id""",
        (RUN_ID,),
    ).fetchall()

    data_dir = output / "data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True)
    search_index: list[dict[str, Any]] = []
    luna_missing = 0
    claude_missing = 0
    for offset in range(0, len(articles), PAGE_SIZE):
        page_number = offset // PAGE_SIZE + 1
        rendered: list[str] = []
        for article in articles[offset:offset + PAGE_SIZE]:
            original = json.loads(article["raw_json"])
            terra = apply_article(connection, RUN_ID, article)
            luna = find_row(luna_exact, luna_by_sequence, article["expression"], article["reading"], article["sequence"])
            claude = find_row(claude_exact, claude_by_sequence, article["expression"], article["reading"], article["sequence"])
            luna_missing += luna is None
            claude_missing += claude is None
            rendered.append(render_row(article, [original, terra, luna, claude], ("original", "terra", "luna", "claude")))
            search_index.append({
                "id": article["id"],
                "page": page_number,
                "search": f'{article["expression"]} {article["reading"]}'.strip().lower(),
            })
        (data_dir / f"page-{page_number:03d}.html").write_text("".join(rendered), encoding="utf-8")

    page_count = (len(articles) + PAGE_SIZE - 1) // PAGE_SIZE
    (output / "index.html").write_text(build_document(
        styles,
        search_index,
        page_count,
        title="Jitendex × Terra × Luna × Claude — вся выборка Kaishi",
        description="Постраничное сравнение Jitendex, Terra, Luna и Claude для всей выборки Kaishi.",
        active_path="/",
        columns=(("original", "Original Jitendex"), ("terra", "Terra"), ("luna", "Luna clean v1"), ("claude", "Claude")),
    ), encoding="utf-8")

    top_5k_articles = connection.execute(
        """SELECT a.* FROM run_article ra JOIN article a ON a.id=ra.article_id
        WHERE ra.run_id=? AND NOT EXISTS (
          SELECT 1 FROM run_article kaishi
          WHERE kaishi.run_id=? AND kaishi.article_id=ra.article_id
        ) ORDER BY a.id""",
        (TOP_5K_RUN_ID, RUN_ID),
    ).fetchall()
    top_5k_result = write_dataset(
        connection,
        output / "jpdb-top-5k",
        top_5k_articles,
        run_id=TOP_5K_RUN_ID,
        styles=styles,
        title="Jitendex English × Luna — JPDB top 5k (без Kaishi)",
        description="Оригинальные английские статьи Jitendex и перевод Luna для JPDB top 5k, за исключением Kaishi.",
        active_path="/jpdb-top-5k/",
    )

    increment_results: dict[str, dict[str, Any]] = {}
    for run_id, previous_run_id, slug, nav_label, rank_label, previous_scope, current_scope in JPDB_INCREMENT_DEMOS:
        preview_limit = NEW_INCREMENT_PREVIEW_LIMIT if run_id >= 8 else None
        limit_clause = " LIMIT ?" if preview_limit is not None else ""
        query_parameters = (run_id, previous_run_id, preview_limit) if preview_limit is not None else (run_id, previous_run_id)
        increment_articles = connection.execute(
            """SELECT a.* FROM run_article ra JOIN article a ON a.id=ra.article_id
            WHERE ra.run_id=? AND NOT EXISTS (
              SELECT 1 FROM run_article previous
              WHERE previous.run_id=? AND previous.article_id=ra.article_id
            ) ORDER BY a.id""" + limit_clause,
            query_parameters,
        ).fetchall()
        preview_suffix = f" — превью {len(increment_articles):,} статей" if preview_limit is not None else ""
        increment_results[slug] = write_dataset(
            connection,
            output / slug,
            increment_articles,
            run_id=run_id,
            styles=styles,
            title=f"Jitendex English × Luna — JPDB ranks {rank_label}{preview_suffix}",
            description=(
                "Оригинальные английские статьи Jitendex и перевод Luna только для новых статей "
                f"между JPDB {previous_scope} и {current_scope}."
            ),
            active_path=f"/{slug}/",
        )

    print(json.dumps({
        "kaishi": {
        "articles": len(articles),
        "pages": page_count,
        "luna_missing": luna_missing,
        "claude_missing": claude_missing,
        "output": str(output),
        },
        "jpdb_top_5k": top_5k_result,
        "jpdb_increments": increment_results,
        "page_size": PAGE_SIZE,
    }, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=SITE_ROOT)
    parser.add_argument("--zip-samples", action="store_true")
    args = parser.parse_args()
    if args.zip_samples:
        build_zip_samples(args.output.resolve())
    else:
        build(args.output.resolve())


if __name__ == "__main__":
    main()
