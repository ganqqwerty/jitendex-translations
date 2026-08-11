from pathlib import Path

import pytest

from jitendex_ru.config import Config


ROOT = Path(__file__).resolve().parents[1]


def test_luna_config_selects_blind_models_and_prompts():
    config = Config.load(ROOT / "config.luna.toml")

    assert config.model("translation") == {
        "id": "gpt-5.6-luna",
        "reasoning_effort": "medium",
    }
    assert config.model("review") == {
        "id": "gpt-5.6-terra",
        "reasoning_effort": "medium",
    }
    assert config.raw["versions"]["translation_prompt"] == "translate-luna-v4"
    assert config.raw["versions"]["review_prompt"] == "review-terra-luna-blind-v4"
    assert config.raw["batch"]["soft_max_bytes"] == 24576
    assert config.raw["batch"]["hard_max_article_bytes"] == 49152
    assert config.raw["batch"]["structured_output_contract"] == "per-manifest-v3"


def test_luna_v4_prompts_fix_japanese_grammar_form_notation_and_compact_labels():
    translator = (ROOT / "prompts/translate_luna_v4.txt").read_text(encoding="utf-8")
    reviewer = (ROOT / "prompts/review_terra_luna_blind_v4.txt").read_text(encoding="utf-8")

    for prompt in (translator, reviewer):
        assert "-ます" in prompt
        assert "-て" in prompt
        assert "-масу" in prompt
        assert "-тэ" in prompt
    assert "never `-масу` or `-тэ`" in translator
    assert "Do not reverse this convention" in reviewer
    for prompt in (translator, reviewer):
        assert "`1-dan`" in prompt
        assert "`1-дан`" in prompt
        assert "`5-dan`" in prompt
        assert "`5-дан`" in prompt
        assert "`noun taking する`" in prompt
        assert "`существительное с する`" in prompt
        assert "`kana`" in prompt
        assert "`кана`" in prompt
    assert "1-12 distinct plain Russian definitions" in translator


def test_model_kind_must_be_explicit():
    config = Config.load(ROOT / "config.luna.toml")

    with pytest.raises(ValueError, match="unsupported model kind"):
        config.model("adjudication")
