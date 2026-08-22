from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from knowledge_ops.config import get_settings
from knowledge_ops.models import (
    AuditLog,
    Collection,
    CollectionAccess,
    KnowledgeRequest,
    PromptTemplate,
    User,
    WorkflowEvent,
)
from knowledge_ops.providers import (
    GenerationRequest,
    ModelProvider,
    ProviderError,
    ProviderRegistry,
)
from knowledge_ops.retrieval import RetrievedChunk, evidence_score, retrieve
from knowledge_ops.security import Identity

DEFAULT_SYSTEM_PROMPT = """You are an enterprise knowledge assistant.
Use only the authorized evidence provided with the request. Never invent policies, dates,
permissions, or actions. If the evidence is insufficient, say so and require human review.
Return the requested structured object and cite chunk identifiers verbatim.
""".strip()

DEFAULT_USER_TEMPLATE = """Answer the following internal knowledge request for a business user.
Question: {question}
Lead with the operational answer, preserve material limitations, and cite supporting evidence.
""".strip()


def prompt_digest(
    system_prompt: str,
    user_template: str,
    provider: str,
    model: str,
    temperature: float,
    retrieval_k: int,
    min_evidence_score: float,
) -> str:
    canonical = "\n---\n".join(
        [
            system_prompt.strip(),
            user_template.strip(),
            provider.strip().lower(),
            model.strip(),
            f"{temperature:.4f}",
            str(retrieval_k),
            f"{min_evidence_score:.4f}",
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def audit(
    db: Session,
    *,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail_json=detail or {},
        )
    )


def add_event(db: Session, request_id: str, state: str, detail: str = "") -> None:
    db.add(WorkflowEvent(request_id=request_id, state=state, detail=detail))


def create_prompt_version(
    db: Session,
    *,
    name: str,
    system_prompt: str,
    user_template: str,
    provider: str,
    model: str,
    temperature: float,
    retrieval_k: int,
    min_evidence_score: float,
    actor_id: str,
) -> PromptTemplate:
    last_version = db.scalar(
        select(func.max(PromptTemplate.version)).where(PromptTemplate.name == name)
    )
    prompt = PromptTemplate(
        name=name.strip(),
        version=(last_version or 0) + 1,
        status="draft",
        system_prompt=system_prompt.strip(),
        user_template=user_template.strip(),
        provider=provider.strip().lower(),
        model=model.strip(),
        temperature=temperature,
        retrieval_k=retrieval_k,
        min_evidence_score=min_evidence_score,
        sha256=prompt_digest(
            system_prompt,
            user_template,
            provider,
            model,
            temperature,
            retrieval_k,
            min_evidence_score,
        ),
        created_by=actor_id,
    )
    db.add(prompt)
    db.flush()
    audit(
        db,
        actor_id=actor_id,
        action="prompt.create",
        resource_type="prompt",
        resource_id=prompt.id,
        detail={"name": prompt.name, "version": prompt.version, "sha256": prompt.sha256},
    )
    return prompt


def release_prompt(db: Session, prompt: PromptTemplate, actor_id: str) -> PromptTemplate:
    db.execute(
        update(PromptTemplate)
        .where(PromptTemplate.name == prompt.name, PromptTemplate.status == "released")
        .values(status="retired")
    )
    prompt.status = "released"
    audit(
        db,
        actor_id=actor_id,
        action="prompt.release",
        resource_type="prompt",
        resource_id=prompt.id,
        detail={"name": prompt.name, "version": prompt.version, "sha256": prompt.sha256},
    )
    return prompt


def released_prompt(db: Session) -> PromptTemplate | None:
    return db.scalar(
        select(PromptTemplate)
        .where(PromptTemplate.status == "released")
        .order_by(PromptTemplate.created_at.desc())
    )


def _validate_citations(
    result_citations: list[dict[str, str]], contexts: list[RetrievedChunk]
) -> list[dict[str, object]]:
    allowed = {item.chunk_id: item for item in contexts}
    valid: list[dict[str, object]] = []
    seen: set[str] = set()
    for citation in result_citations:
        chunk_id = citation.get("chunk_id", "")
        if chunk_id in allowed and chunk_id not in seen:
            valid.append(allowed[chunk_id].citation())
            seen.add(chunk_id)
    return valid


def _choose_provider(
    registry: ProviderRegistry, requested_name: str
) -> tuple[ModelProvider, str | None]:
    requested = registry.get(requested_name)
    if requested.configured:
        return requested, None
    if requested.name == "mock":
        return requested, None
    return registry.get("mock"), f"{requested.name} is not configured; used offline mock fallback"


def _select_generation_contexts(
    contexts: list[RetrievedChunk], minimum_score: float
) -> list[RetrievedChunk]:
    """Keep weak candidates in the trace without diluting the model context."""

    if not contexts:
        return []
    cutoff = max(minimum_score, contexts[0].score * 0.65)
    selected = [item for item in contexts if item.score >= cutoff]
    return selected or contexts[:1]


def process_request(
    db: Session,
    request_row: KnowledgeRequest,
    *,
    registry: ProviderRegistry | None = None,
) -> KnowledgeRequest:
    registry = registry or ProviderRegistry()
    prompt = db.get(PromptTemplate, request_row.prompt_id)
    if prompt is None:
        request_row.status = "failed"
        request_row.error = "Prompt version not found"
        add_event(db, request_row.id, "failed", request_row.error)
        db.flush()
        return request_row

    try:
        request_row.status = "retrieving"
        add_event(db, request_row.id, "retrieving", "Searching authorized collection")
        contexts = retrieve(
            db,
            collection_id=request_row.collection_id,
            question=request_row.question,
            limit=prompt.retrieval_k,
        )
        score = evidence_score(contexts)
        request_row.evidence_score = score
        request_row.trace_json = {
            "prompt_sha256": prompt.sha256,
            "retrieval": [item.trace() for item in contexts],
        }

        if not contexts or score < prompt.min_evidence_score:
            request_row.answer = "目前授權範圍內的知識庫沒有足夠證據回答此問題。"
            request_row.citations_json = []
            request_row.needs_review = True
            request_row.status = "review_required"
            add_event(db, request_row.id, "review_required", "Evidence threshold was not met")
            db.flush()
            return request_row

        generation_contexts = _select_generation_contexts(contexts, prompt.min_evidence_score)
        request_row.trace_json["selected_context_ids"] = [
            item.chunk_id for item in generation_contexts
        ]

        request_row.status = "generating"
        add_event(db, request_row.id, "generating", f"Requested provider: {request_row.provider}")
        provider, fallback_reason = _choose_provider(registry, request_row.provider)
        if fallback_reason:
            add_event(db, request_row.id, "provider_fallback", fallback_reason)

        safety_identifier = hashlib.sha256(request_row.user_id.encode("utf-8")).hexdigest()[:32]
        generation = provider.generate(
            GenerationRequest(
                question=request_row.question,
                system_prompt=prompt.system_prompt,
                user_prompt=prompt.user_template.format(question=request_row.question),
                contexts=generation_contexts,
                model=provider.default_model if fallback_reason else request_row.model,
                temperature=prompt.temperature,
                safety_identifier=safety_identifier,
            )
        )

        request_row.status = "validating"
        add_event(db, request_row.id, "validating", "Checking citations and output contract")
        valid_citations = _validate_citations(generation.citations, generation_contexts)
        needs_review = generation.needs_review or not valid_citations
        request_row.answer = generation.answer
        request_row.citations_json = valid_citations
        request_row.needs_review = needs_review
        request_row.latency_ms = generation.latency_ms
        request_row.input_tokens = generation.input_tokens
        request_row.output_tokens = generation.output_tokens
        request_row.estimated_cost = 0.0
        request_row.provider = generation.provider
        request_row.model = generation.model
        request_row.trace_json = {
            **request_row.trace_json,
            "raw_response_id": generation.raw_id,
            "provider_trace": generation.trace,
            "fallback_reason": fallback_reason,
        }
        request_row.status = "review_required" if needs_review else "completed"
        add_event(
            db,
            request_row.id,
            request_row.status,
            "Human review required" if needs_review else "Output passed evidence validation",
        )
    except (ProviderError, KeyError, ValueError) as exc:
        request_row.status = "failed"
        request_row.error = str(exc)
        request_row.needs_review = True
        add_event(db, request_row.id, "failed", request_row.error)
    db.flush()
    return request_row


def create_knowledge_request(
    db: Session,
    *,
    question: str,
    collection_id: str,
    prompt: PromptTemplate,
    provider_name: str | None,
    identity: Identity,
) -> KnowledgeRequest:
    provider = (provider_name or prompt.provider or get_settings().default_provider).lower()
    registry = ProviderRegistry()
    selected = registry.get(provider)
    model = prompt.model if provider == prompt.provider else selected.default_model
    row = KnowledgeRequest(
        question=question.strip(),
        collection_id=collection_id,
        prompt_id=prompt.id,
        user_id=identity.id,
        provider=provider,
        model=model,
        status="submitted",
    )
    db.add(row)
    db.flush()
    add_event(db, row.id, "submitted", "Knowledge request accepted")
    audit(
        db,
        actor_id=identity.id,
        action="request.submit",
        resource_type="knowledge_request",
        resource_id=row.id,
        detail={"collection_id": collection_id, "prompt_sha256": prompt.sha256},
    )
    return row


def seed_demo_identities(db: Session) -> dict[str, User]:
    users = {
        "admin": ("Platform Admin", "admin"),
        "editor": ("Knowledge Editor", "editor"),
        "reviewer": ("Response Reviewer", "reviewer"),
        "viewer": ("Business Viewer", "viewer"),
    }
    resolved: dict[str, User] = {}
    for username, (display_name, role) in users.items():
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(username=username, display_name=display_name, role=role)
            db.add(user)
            db.flush()
        resolved[username] = user
    return resolved


def seed_default_prompt(db: Session, admin_id: str) -> PromptTemplate:
    existing = db.scalar(
        select(PromptTemplate).where(
            PromptTemplate.name == "Grounded knowledge response",
            PromptTemplate.status == "released",
        )
    )
    if existing:
        return existing
    prompt = create_prompt_version(
        db,
        name="Grounded knowledge response",
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_template=DEFAULT_USER_TEMPLATE,
        provider="mock",
        model="mock-grounded-v1",
        temperature=0.1,
        retrieval_k=4,
        min_evidence_score=0.10,
        actor_id=admin_id,
    )
    return release_prompt(db, prompt, admin_id)


def grant_demo_access(db: Session, collection: Collection, users: dict[str, User]) -> None:
    for username, can_write in {"editor": True, "reviewer": False, "viewer": False}.items():
        user = users[username]
        exists = db.scalar(
            select(CollectionAccess).where(
                CollectionAccess.collection_id == collection.id,
                CollectionAccess.user_id == user.id,
            )
        )
        if exists is None:
            db.add(
                CollectionAccess(
                    collection_id=collection.id,
                    user_id=user.id,
                    can_write=can_write,
                )
            )
