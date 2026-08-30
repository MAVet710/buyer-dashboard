from __future__ import annotations

import json

from services.ai.providers.local import LocalOpenAIProvider
from services.ai.schemas import AGENT_RESPONSE_SCHEMA, AIRequest, AIResponse
from services.ai.validation import validate_agent_response


class _HTTPResponse:
    def __init__(self, body, *, status_code=200):
        self._body = body
        self.status_code = status_code
        self.ok = status_code < 400

    def json(self):
        return self._body


def _provider() -> LocalOpenAIProvider:
    return LocalOpenAIProvider(
        base_url="https://ai-runtime.doobielogic.io",
        model="qwen3:14b",
        access_client_id="service-id",
        access_client_secret="service-secret",
    )


def test_local_provider_sends_actual_agent_schema_for_structured_output(monkeypatch):
    captured = {}

    def post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _HTTPResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer": "Extraction is online.",
                                    "summary": "Local AI response",
                                    "priority": "normal",
                                    "confidence": 0.9,
                                    "recommendations": [],
                                    "warnings": [],
                                    "missing_data": [],
                                }
                            )
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            }
        )

    monkeypatch.setattr("services.ai.providers.local.requests.post", post)

    response = _provider().generate(
        AIRequest(
            request_id="request",
            system_prompt="You are Extraction Scientist Agent.",
            messages=[{"role": "user", "content": "What can you help me with?"}],
            response_schema=AGENT_RESPONSE_SCHEMA,
        )
    )

    payload = captured["kwargs"]["json"]
    assert captured["url"] == "https://ai-runtime.doobielogic.io/v1/chat/completions"
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "doobielogic_agent_response",
            "schema": AGENT_RESPONSE_SCHEMA,
            "strict": True,
        },
    }
    system_message = payload["messages"][0]["content"]
    assert "top-level `answer` field is required" in system_message
    assert '"required":["answer"]' in system_message
    assert response.structured is not None
    assert response.structured["answer"] == "Extraction is online."
    assert validate_agent_response(response) == (True, "ok")


def test_tool_call_first_pass_does_not_force_final_response_schema(monkeypatch):
    captured = {}

    def post(url, **kwargs):
        captured["payload"] = kwargs["json"]
        return _HTTPResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "preview_dataset",
                                        "arguments": '{"dataset":"inventory","limit":5}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        )

    monkeypatch.setattr("services.ai.providers.local.requests.post", post)

    response = _provider().generate(
        AIRequest(
            request_id="request",
            system_prompt="Use tools when needed.",
            messages=[{"role": "user", "content": "Review inventory."}],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "preview_dataset",
                        "description": "Preview an authorized dataset",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            response_schema=AGENT_RESPONSE_SCHEMA,
        )
    )

    payload = captured["payload"]
    assert "response_format" not in payload
    assert "Response schema:" not in payload["messages"][0]["content"]
    assert response.tool_calls
    assert response.tool_calls[0].name == "preview_dataset"


def test_validation_contract_keeps_answer_required():
    valid = AIResponse(
        text='```json\n{"answer":"Ready","warnings":[],"recommendations":[],"missing_data":[]}\n```',
        provider="local",
        model="qwen3:14b",
        local=True,
    )
    missing_answer = AIResponse(
        text='{"response":"Ready","warnings":[],"recommendations":[],"missing_data":[]}',
        provider="local",
        model="qwen3:14b",
        local=True,
    )

    assert validate_agent_response(valid) == (True, "ok")
    assert validate_agent_response(missing_answer) == (False, "missing_answer")
