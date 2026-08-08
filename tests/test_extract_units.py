from jitendex_ru.extract_units import extract_article_units, glossary_evidence, lexicographic_context, semantic_context


def article(content):
    return ["食べる", "たべる", "", "v1", 0, {"type": "structured-content", "content": content}, 1, ""]


def test_extracts_only_whitelisted_english_leaves_and_protects_tokens():
    row = article([
        {"tag": "div", "data": {"content": "glossary"}, "lang": "en", "content": "to eat JMdict 123"},
        {"tag": "div", "data": {"content": "example-sentence-a"}, "content": "ご飯を食べる。"},
        {"tag": "div", "data": {"content": "example-sentence-b"}, "lang": "en", "content": "I eat rice."},
        {"tag": "a", "href": "https://example.test", "content": "unclassified link"},
        {"tag": "ruby", "data": {"content": "ruby"}, "content": "食べる"},
    ])
    units = extract_article_units(row)
    assert [(unit.role, unit.source_text) for unit in units] == [
        ("glossary", "to eat JMdict 123"), ("example", "I eat rice.")
    ]
    assert units[0].protected_tokens == ("JMdict", "123")
    context = semantic_context(row)
    assert context["examples"] == [{"japanese": "ご飯を食べる。", "english": "I eat rice."}]


def test_excludes_attribution_even_inside_translatable_ancestor():
    row = article({
        "tag": "div", "data": {"content": "glossary"}, "content": [
            "visible gloss",
            {"tag": "span", "data": {"content": "attribution"}, "content": "Creative Commons"},
        ],
    })
    assert [unit.source_text for unit in extract_article_units(row)] == ["visible gloss"]


def test_lexicographer_groups_english_synonyms_into_one_variable_length_unit():
    row = article({
        "tag": "div", "data": {"content": "sense"}, "content": [
            {"tag": "span", "data": {"content": "part-of-speech-info"}, "content": "transitive verb"},
            {"tag": "ul", "data": {"content": "glossary"}, "content": [
                {"tag": "li", "content": "to begin"},
                {"tag": "li", "content": "to start"},
                {"tag": "li", "content": "to commence"},
            ]},
            {"tag": "div", "data": {"content": "example-sentence-a"}, "content": "仕事を始める。"},
            {"tag": "div", "data": {"content": "example-sentence-b"}, "content": "Begin the work."},
        ],
    })
    units = extract_article_units(row, "lexicographer-v2")
    assert [unit.role for unit in units] == ["pos", "glossary_set", "example"]
    assert glossary_evidence(units[1].source_text) == ["to begin", "to start", "to commence"]
    context = lexicographic_context(row)
    assert context["senses"][0]["english_gloss_evidence"] == ["to begin", "to start", "to commence"]
    assert context["senses"][0]["examples"][0]["japanese"] == "仕事を始める。"
