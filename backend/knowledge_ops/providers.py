from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from knowledge_ops.config import Settings, get_settings
from knowledge_ops.retrieval import RetrievedChunk

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "chunk_id": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["chunk_id", "quote"],
            },
        },
        "needs_review": {"type": "boolean"},
    },
    "required": ["answer", "citations", "needs_review"],
}


class ProviderError(RuntimeError):
    pass


class ProviderNotConfigured(ProviderError):
    pass


@dataclass(frozen=True)
class GenerationRequest:
    question: str
    system_prompt: str
    user_prompt: str
    contexts: list[RetrievedChunk]
    model: str
    temperature: float = 0.1
    max_output_tokens: int = 800
    safety_identifier: str = ""

    def context_text(self) -> str:
        if not self.contexts:
            return "No authorized evidence was retrieved."
        return "\n\n".join(
            f"[chunk_id={item.chunk_id}; file={item.filename}; score={item.score:.4f}]\n"
            f"{item.content}"
            for item in self.contexts
        )


@dataclass(frozen=True)
class GenerationResult:
    provider: str
    model: str
    answer: str
    citations: list[dict[str, str]]
    needs_review: bool
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    raw_id: str = ""
    trace: dict[str, Any] = field(default_factory=dict)


class ModelProvider(ABC):
    name: str
    supports_structured_output = True

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    @abstractmethod
    def configured(self) -> bool: ...

    @property
    @abstractmethod
    def default_model(self) -> str: ...

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResult: ...

    def info(self) -> dict[str, object]:
        return {
            "name": self.name,
            "configured": self.configured,
            "model": self.default_model,
            "supports_structured_output": self.supports_structured_output,
            "live_calls_enabled": self.configured and self.name != "mock",
        }


def _normalize_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if not isinstance(payload, str):
        raise ProviderError("Provider returned an unsupported payload")
    cleaned = payload.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```")
        cleaned = cleaned.removesuffix("```").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProviderError("Provider did not return valid structured JSON") from exc
    if not isinstance(parsed, dict):
        raise ProviderError("Provider JSON root must be an object")
    return parsed


def _result_from_payload(
    *,
    provider: str,
    model: str,
    payload: Any,
    latency_ms: float,
    usage: dict[str, Any] | None = None,
    raw_id: str = "",
) -> GenerationResult:
    normalized = _normalize_payload(payload)
    citations = normalized.get("citations", [])
    if not isinstance(citations, list):
        citations = []
    safe_citations = [
        {"chunk_id": str(item.get("chunk_id", "")), "quote": str(item.get("quote", ""))}
        for item in citations
        if isinstance(item, dict) and item.get("chunk_id")
    ]
    usage = usage or {}
    return GenerationResult(
        provider=provider,
        model=model,
        answer=str(normalized.get("answer", "")).strip(),
        citations=safe_citations,
        needs_review=bool(normalized.get("needs_review", False)),
        latency_ms=round(latency_ms, 2),
        input_tokens=int(usage.get("input_tokens", usage.get("promptTokenCount", 0)) or 0),
        output_tokens=int(usage.get("output_tokens", usage.get("candidatesTokenCount", 0)) or 0),
        raw_id=raw_id,
        trace={"cost_status": "not_configured" if provider != "mock" else "zero_cost_demo"},
    )


class MockProvider(ModelProvider):
    name = "mock"

    @property
    def configured(self) -> bool:
        return True

    @property
    def default_model(self) -> str:
        return "mock-grounded-v1"

    def generate(self, request: GenerationRequest) -> GenerationResult:
        started = time.perf_counter()
        if not request.contexts or request.contexts[0].score <= 0:
            payload = {
                "answer": "目前授權範圍內的知識庫沒有足夠證據回答此問題。",
                "citations": [],
                "needs_review": True,
            }
        else:
            selected = request.contexts[:2]
            extracts = [item.content[:420].strip() for item in selected]
            payload = {
                "answer": "根據知識庫：" + " ".join(extracts),
                "citations": [
                    {"chunk_id": item.chunk_id, "quote": item.content[:220]} for item in selected
                ],
                "needs_review": False,
            }
        latency = (time.perf_counter() - started) * 1000
        return _result_from_payload(
            provider=self.name,
            model=request.model or self.default_model,
            payload=payload,
            latency_ms=latency,
            usage={"input_tokens": len(request.context_text()) // 4, "output_tokens": 80},
            raw_id="mock-response",
        )


class OpenAIProvider(ModelProvider):
    name = "openai"

    @property
    def configured(self) -> bool:
        return bool(self.settings.openai_api_key)

    @property
    def default_model(self) -> str:
        return self.settings.openai_model

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if not self.configured:
            raise ProviderNotConfigured("OPENAI_API_KEY is not configured")
        payload = {
            "model": request.model or self.default_model,
            "instructions": request.system_prompt,
            "input": f"{request.user_prompt}\n\nAuthorized evidence:\n{request.context_text()}",
            "max_output_tokens": request.max_output_tokens,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "knowledge_answer",
                    "strict": True,
                    "schema": ANSWER_SCHEMA,
                }
            },
        }
        if not str(payload["model"]).startswith("gpt-5"):
            payload["temperature"] = request.temperature
        if request.safety_identifier:
            payload["safety_identifier"] = request.safety_identifier
        started = time.perf_counter()
        with httpx.Client(timeout=self.settings.request_timeout_seconds) as client:
            response = client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {self.settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        latency = (time.perf_counter() - started) * 1000
        if response.status_code >= 400:
            raise ProviderError(f"OpenAI request failed with HTTP {response.status_code}")
        data = response.json()
        output_text = data.get("output_text")
        if not output_text:
            output_text = next(
                (
                    part.get("text")
                    for item in data.get("output", [])
                    for part in item.get("content", [])
                    if part.get("type") == "output_text"
                ),
                "",
            )
        return _result_from_payload(
            provider=self.name,
            model=data.get("model", request.model),
            payload=output_text,
            latency_ms=latency,
            usage=data.get("usage"),
            raw_id=data.get("id", ""),
        )


class AnthropicProvider(ModelProvider):
    name = "anthropic"

    @property
    def configured(self) -> bool:
        return bool(self.settings.anthropic_api_key)

    @property
    def default_model(self) -> str:
        return self.settings.anthropic_model

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if not self.configured:
            raise ProviderNotConfigured("ANTHROPIC_API_KEY is not configured")
        payload = {
            "model": request.model or self.default_model,
            "max_tokens": request.max_output_tokens,
            "system": request.system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"{request.user_prompt}\n\nAuthorized evidence:\n{request.context_text()}"
                    ),
                }
            ],
            "output_config": {"format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
        }
        if not str(payload["model"]).startswith(("claude-sonnet-5", "claude-opus-5")):
            payload["temperature"] = request.temperature
        started = time.perf_counter()
        with httpx.Client(timeout=self.settings.request_timeout_seconds) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
        latency = (time.perf_counter() - started) * 1000
        if response.status_code >= 400:
            raise ProviderError(f"Anthropic request failed with HTTP {response.status_code}")
        data = response.json()
        output_text = next(
            (item.get("text") for item in data.get("content", []) if item.get("type") == "text"),
            "",
        )
        return _result_from_payload(
            provider=self.name,
            model=data.get("model", request.model),
            payload=output_text,
            latency_ms=latency,
            usage=data.get("usage"),
            raw_id=data.get("id", ""),
        )


class GeminiProvider(ModelProvider):
    name = "gemini"

    @property
    def configured(self) -> bool:
        return bool(self.settings.gemini_api_key)

    @property
    def default_model(self) -> str:
        return self.settings.gemini_model

    def generate(self, request: GenerationRequest) -> GenerationResult:
        if not self.configured:
            raise ProviderNotConfigured("GEMINI_API_KEY is not configured")
        model = request.model or self.default_model
        payload = {
            "systemInstruction": {"parts": [{"text": request.system_prompt}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                f"{request.user_prompt}\n\nAuthorized evidence:\n"
                                f"{request.context_text()}"
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "maxOutputTokens": request.max_output_tokens,
                "responseMimeType": "application/json",
                "responseSchema": ANSWER_SCHEMA,
            },
        }
        started = time.perf_counter()
        with httpx.Client(timeout=self.settings.request_timeout_seconds) as client:
            response = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={
                    "x-goog-api-key": self.settings.gemini_api_key,
                    "content-type": "application/json",
                },
                json=payload,
            )
        latency = (time.perf_counter() - started) * 1000
        if response.status_code >= 400:
            raise ProviderError(f"Gemini request failed with HTTP {response.status_code}")
        data = response.json()
        output_text = next(
            (
                part.get("text")
                for candidate in data.get("candidates", [])
                for part in candidate.get("content", {}).get("parts", [])
                if part.get("text")
            ),
            "",
        )
        return _result_from_payload(
            provider=self.name,
            model=model,
            payload=output_text,
            latency_ms=latency,
            usage=data.get("usageMetadata"),
            raw_id=data.get("responseId", ""),
        )


class ProviderRegistry:
    def __init__(self, settings: Settings | None = None) -> None:
        resolved = settings or get_settings()
        self.providers: dict[str, ModelProvider] = {
            "mock": MockProvider(resolved),
            "openai": OpenAIProvider(resolved),
            "anthropic": AnthropicProvider(resolved),
            "gemini": GeminiProvider(resolved),
        }

    def get(self, name: str) -> ModelProvider:
        normalized = name.strip().lower()
        try:
            return self.providers[normalized]
        except KeyError as exc:
            raise ProviderError(f"Unknown provider: {name}") from exc

    def list_info(self) -> list[dict[str, object]]:
        return [provider.info() for provider in self.providers.values()]
