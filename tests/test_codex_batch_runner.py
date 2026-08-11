import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_codex_batches", ROOT / "scripts/run_codex_batches.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parse_codex_usage_events():
    thread_id, usage = MODULE.parse_events(
        '{"type":"thread.started","thread_id":"thread-1"}\n'
        '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":4,"output_tokens":3}}\n'
    )
    assert thread_id == "thread-1"
    assert usage == {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 3}


def test_manifest_schema_constrains_ordered_ids_hashes_and_target_types():
    manifest = {
        "batch_id": "b-1", "manifest_sha256": "a" * 64,
        "articles": [{"units": [
            {"unit_id": "u-1", "source_sha256": "b" * 64, "role": "glossary_set"},
            {"unit_id": "u-2", "source_sha256": "c" * 64, "role": "example"},
        ]}],
    }
    schema = MODULE.build_output_schema(manifest, "translation")
    translations = schema["properties"]["translations"]
    assert translations["minItems"] == translations["maxItems"] == 2
    alternatives = translations["items"]["anyOf"]
    assert alternatives[0]["properties"]["unit_id"] == {"type": "string", "const": "u-1"}
    assert alternatives[0]["properties"]["source_sha256"] == {"type": "string", "const": "b" * 64}
    assert alternatives[0]["properties"]["target_text"]["type"] == "array"
    assert alternatives[1]["properties"]["target_text"]["type"] == "string"
