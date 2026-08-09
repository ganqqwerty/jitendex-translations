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
    assert config.raw["versions"]["translation_prompt"] == "translate-luna-v2"
    assert config.raw["versions"]["review_prompt"] == "review-terra-luna-blind-v2"
    assert config.raw["batch"]["soft_max_bytes"] == 24576
    assert config.raw["batch"]["hard_max_article_bytes"] == 49152


def test_luna_v2_prompts_fix_japanese_grammar_form_notation():
    translator = (ROOT / "prompts/translate_luna_v2.txt").read_text(encoding="utf-8")
    reviewer = (ROOT / "prompts/review_terra_luna_blind_v2.txt").read_text(encoding="utf-8")

    for prompt in (translator, reviewer):
        assert "-ます" in prompt
        assert "-て" in prompt
        assert "-масу" in prompt
        assert "-тэ" in prompt
    assert "never `-масу` or `-тэ`" in translator
    assert "Do not reverse this convention" in reviewer


def test_model_kind_must_be_explicit():
    config = Config.load(ROOT / "config.luna.toml")

    with pytest.raises(ValueError, match="unsupported model kind"):
        config.model("adjudication")
