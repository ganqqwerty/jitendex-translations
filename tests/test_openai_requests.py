import json

from jitendex_ru.openai_requests import (
    TRANSLATION_RESPONSE_SCHEMA,
    build_translation_request,
    count_input_tokens,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return json.dumps(self.payload).encode()


def test_translation_request_is_tool_free_stateless_and_strict():
    request = build_translation_request(
        model="gpt-5.6-luna", reasoning_effort="medium",
        instructions="blind prompt", manifest='{"batch_id":"b"}',
    )

    assert request["model"] == "gpt-5.6-luna"
    assert request["reasoning"] == {"effort": "medium", "context": "current_turn"}
    assert request["tools"] == []
    assert request["store"] is False
    assert "previous_response_id" not in request
    assert request["input"][0]["content"][0]["text"] == '{"batch_id":"b"}'
    assert request["text"]["format"]["strict"] is True
    assert request["text"]["format"]["schema"] == TRANSLATION_RESPONSE_SCHEMA


def test_input_token_counter_posts_exact_request_body():
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse({"object": "response.input_tokens", "input_tokens": 123})

    body = {"model": "gpt-5.6-luna", "input": "hello"}
    assert count_input_tokens(body, "secret", opener=opener) == 123
    assert captured["url"].endswith("/v1/responses/input_tokens")
    assert captured["authorization"] == "Bearer secret"
    assert captured["body"] == body
