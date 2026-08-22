from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    redis: str
    demo_mode: bool


class UserOut(OrmModel):
    id: str
    username: str
    display_name: str
    role: str


class CollectionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)


class CollectionOut(OrmModel):
    id: str
    name: str
    description: str
    created_by: str
    created_at: datetime
    document_count: int = 0
    can_write: bool = False


class AccessGrantCreate(BaseModel):
    username: str
    can_write: bool = False


class DocumentOut(OrmModel):
    id: str
    collection_id: str
    filename: str
    content_type: str
    sha256: str
    version: int
    status: str
    source_label: str
    created_by: str
    created_at: datetime
    chunk_count: int = 0


class PromptCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    system_prompt: str = Field(min_length=20)
    user_template: str = Field(min_length=10)
    provider: str = "mock"
    model: str = "mock-grounded-v1"
    temperature: float = Field(default=0.1, ge=0, le=2)
    retrieval_k: int = Field(default=4, ge=1, le=20)
    min_evidence_score: float = Field(default=0.18, ge=0, le=1)


class PromptOut(OrmModel):
    id: str
    name: str
    version: int
    status: str
    system_prompt: str
    user_template: str
    provider: str
    model: str
    temperature: float
    retrieval_k: int
    min_evidence_score: float
    sha256: str
    created_by: str
    created_at: datetime


class RequestCreate(BaseModel):
    question: str = Field(min_length=5, max_length=4000)
    collection_id: str
    prompt_id: str | None = None
    provider: str | None = None
    process_now: bool = True


class CitationOut(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    quote: str
    score: float


class RequestOut(OrmModel):
    id: str
    question: str
    collection_id: str
    prompt_id: str
    user_id: str
    provider: str
    model: str
    status: str
    answer: str
    citations_json: list[dict[str, Any]]
    evidence_score: float
    needs_review: bool
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    error: str
    trace_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ReviewInput(BaseModel):
    answer: str = Field(min_length=1)
    approve: bool = True
    note: str = Field(default="", max_length=1000)


class WorkflowEventOut(OrmModel):
    id: str
    request_id: str
    state: str
    detail: str
    created_at: datetime


class ProviderOut(BaseModel):
    name: str
    configured: bool
    model: str
    supports_structured_output: bool
    live_calls_enabled: bool


class EvaluationCaseCreate(BaseModel):
    collection_id: str
    name: str
    question: str
    expected_terms: list[str] = Field(default_factory=list)
    should_answer: bool = True


class EvaluationCaseOut(OrmModel):
    id: str
    collection_id: str
    name: str
    question: str
    expected_terms: list[str]
    should_answer: bool


class EvaluationRunCreate(BaseModel):
    prompt_id: str
    provider: str | None = None


class EvaluationRunOut(OrmModel):
    id: str
    prompt_id: str
    provider: str
    model: str
    status: str
    case_count: int
    pass_rate: float
    citation_rate: float
    refusal_accuracy: float
    median_latency_ms: float
    total_estimated_cost: float
    created_by: str
    created_at: datetime


class AuditOut(OrmModel):
    id: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    detail_json: dict[str, Any]
    created_at: datetime


class DashboardOut(BaseModel):
    total_requests: int
    completed_requests: int
    review_queue: int
    document_count: int
    prompt_versions: int
    evaluation_runs: int
    median_latency_ms: float
    citation_rate: float
    provider_counts: dict[str, int]
