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
    assert config.raw["versions"]["translation_prompt"] == "translate-luna-v1"
    assert config.raw["versions"]["review_prompt"] == "review-terra-luna-blind-v1"
    assert config.raw["batch"]["soft_max_bytes"] == 24576
    assert config.raw["batch"]["hard_max_article_bytes"] == 49152


def test_model_kind_must_be_explicit():
    config = Config.load(ROOT / "config.luna.toml")

    with pytest.raises(ValueError, match="unsupported model kind"):
        config.model("adjudication")
