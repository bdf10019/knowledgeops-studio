from __future__ import annotations

import json

import knowledge_ops.providers as provider_module
import pytest
from knowledge_ops.config import Settings
from knowledge_ops.providers import (
    AnthropicProvider,
    GeminiProvider,
    GenerationRequest,
    MockProvider,
    OpenAIProvider,
    ProviderNotConfigured,
    ProviderRegistry,
)
from knowledge_ops.retrieval import RetrievedChunk

PROVIDER_JSON = json.dumps(
    {
        "answer": "Approved",
        "citations": [{"chunk_id": "chunk-1", "quote": "approval"}],
        "needs_review": False,
    }
)


def context() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        filename="policy.md",
        content="Access requires manager approval and an audit event.",
        score=0.8,
        source_label="synthetic",
    )


def test_mock_provider_returns_grounded_citation() -> None:
    provider = MockProvider(Settings())
    result = provider.generate(
        GenerationRequest(
            question="How is access approved?",
            system_prompt="Use evidence only.",
            user_prompt="Answer the question.",
            contexts=[context()],
            model="mock-grounded-v1",
        )
    )
    assert result.provider == "mock"
    assert result.citations[0]["chunk_id"] == "chunk-1"
    assert "manager approval" in result.answer


def test_mock_provider_refuses_without_evidence() -> None:
    result = MockProvider(Settings()).generate(
        GenerationRequest(
            question="Unknown",
            system_prompt="Use evidence only.",
            user_prompt="Answer.",
            contexts=[],
            model="mock-grounded-v1",
        )
    )
    assert result.needs_review is True
    assert result.citations == []


def test_live_provider_requires_environment_key() -> None:
    provider = OpenAIProvider(Settings(openai_api_key=""))
    with pytest.raises(ProviderNotConfigured):
        provider.generate(
            GenerationRequest(
                question="Question",
                system_prompt="System",
                user_prompt="User",
                contexts=[context()],
                model=provider.default_model,
            )
        )


def test_registry_exposes_all_required_providers_without_keys() -> None:
    registry = ProviderRegistry(Settings())
    assert set(registry.providers) == {"mock", "openai", "anthropic", "gemini"}
    assert registry.get("mock").configured
    assert not registry.get("anthropic").configured


class FakeResponse:
    status_code = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def json(self) -> dict[str, object]:
        return self.payload


class FakeClient:
    last_url = ""
    last_headers: dict[str, str] = {}
    last_payload: dict[str, object] = {}
    response_payload: dict[str, object] = {}

    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> FakeResponse:
        FakeClient.last_url = url
        FakeClient.last_headers = headers
        FakeClient.last_payload = json
        return FakeResponse(FakeClient.response_payload)


def generation_request(model: str) -> GenerationRequest:
    return GenerationRequest(
        question="How is access approved?",
        system_prompt="Use authorized evidence only.",
        user_prompt="Answer the question.",
        contexts=[context()],
        model=model,
        safety_identifier="hashed-user",
    )


def test_openai_adapter_normalizes_responses_api(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.response_payload = {
        "id": "resp-1",
        "model": "gpt-5.4-mini",
        "output_text": PROVIDER_JSON,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    monkeypatch.setattr(provider_module.httpx, "Client", FakeClient)
    provider = OpenAIProvider(Settings(OPENAI_API_KEY="test-openai-key"))
    result = provider.generate(generation_request(provider.default_model))
    assert result.answer == "Approved"
    assert result.raw_id == "resp-1"
    assert FakeClient.last_url.endswith("/v1/responses")
    assert FakeClient.last_payload["store"] is False
    assert "temperature" not in FakeClient.last_payload


def test_anthropic_adapter_uses_structured_output(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.response_payload = {
        "id": "msg-1",
        "model": "claude-sonnet-5",
        "content": [
            {
                "type": "text",
                "text": PROVIDER_JSON,
            }
        ],
        "usage": {"input_tokens": 11, "output_tokens": 6},
    }
    monkeypatch.setattr(provider_module.httpx, "Client", FakeClient)
    provider = AnthropicProvider(Settings(ANTHROPIC_API_KEY="test-anthropic-key"))
    result = provider.generate(generation_request(provider.default_model))
    assert result.provider == "anthropic"
    assert FakeClient.last_url.endswith("/v1/messages")
    assert "output_config" in FakeClient.last_payload
    assert "temperature" not in FakeClient.last_payload


def test_gemini_adapter_normalizes_generate_content(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.response_payload = {
        "responseId": "gemini-1",
        "candidates": [{"content": {"parts": [{"text": PROVIDER_JSON}]}}],
        "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 7},
    }
    monkeypatch.setattr(provider_module.httpx, "Client", FakeClient)
    provider = GeminiProvider(Settings(GEMINI_API_KEY="test-gemini-key"))
    result = provider.generate(generation_request(provider.default_model))
    assert result.output_tokens == 7
    assert FakeClient.last_url.endswith(":generateContent")
    assert "temperature" not in FakeClient.last_payload["generationConfig"]
