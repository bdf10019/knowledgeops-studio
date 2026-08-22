from __future__ import annotations

from knowledge_ops.database import get_session_factory
from knowledge_ops.models import (
    Collection,
    KnowledgeRequest,
    PromptTemplate,
    User,
    WorkflowEvent,
)
from knowledge_ops.retrieval import RetrievedChunk, evidence_score, retrieve
from knowledge_ops.security import Identity
from knowledge_ops.services import (
    _select_generation_contexts,
    create_knowledge_request,
    process_request,
)
from knowledge_ops.worker import process_next
from sqlalchemy import select


def test_retrieval_finds_access_policy() -> None:
    with get_session_factory()() as db:
        collection = db.scalar(select(Collection).where(Collection.name == "Operations handbook"))
        assert collection is not None
        chunks = retrieve(
            db,
            collection_id=collection.id,
            question="調職後權限應多久撤銷？",
            limit=3,
        )
        assert chunks
        assert chunks[0].filename == "access-control.md"
        assert evidence_score(chunks) > 0.1


def test_generation_context_filters_weak_candidates() -> None:
    contexts = [
        RetrievedChunk("one", "doc-one", "one.md", "relevant", 0.8, "demo"),
        RetrievedChunk("two", "doc-two", "two.md", "noise", 0.2, "demo"),
    ]
    assert _select_generation_contexts(contexts, 0.1) == contexts[:1]


def test_workflow_completes_with_validated_citations() -> None:
    with get_session_factory()() as db:
        collection = db.scalar(select(Collection).where(Collection.name == "Operations handbook"))
        prompt = db.scalar(select(PromptTemplate).where(PromptTemplate.status == "released"))
        viewer = db.scalar(select(User).where(User.username == "viewer"))
        assert collection and prompt and viewer
        identity = Identity(viewer.id, viewer.username, viewer.display_name, viewer.role)
        row = create_knowledge_request(
            db,
            question="Prompt 發布前要比較哪些指標？",
            collection_id=collection.id,
            prompt=prompt,
            provider_name="mock",
            identity=identity,
        )
        process_request(db, row)
        db.commit()
        assert row.status == "completed"
        assert row.citations_json
        assert row.trace_json["prompt_sha256"] == prompt.sha256
        states = list(
            db.scalars(
                select(WorkflowEvent.state)
                .where(WorkflowEvent.request_id == row.id)
                .order_by(WorkflowEvent.created_at)
            )
        )
        assert states == ["submitted", "retrieving", "generating", "validating", "completed"]


def test_workflow_routes_unrelated_question_to_review() -> None:
    with get_session_factory()() as db:
        collection = db.scalar(select(Collection).where(Collection.name == "Operations handbook"))
        prompt = db.scalar(select(PromptTemplate).where(PromptTemplate.status == "released"))
        viewer = db.scalar(select(User).where(User.username == "viewer"))
        assert collection and prompt and viewer
        identity = Identity(viewer.id, viewer.username, viewer.display_name, viewer.role)
        row = create_knowledge_request(
            db,
            question="下個月東京每天的天氣預報是什麼？",
            collection_id=collection.id,
            prompt=prompt,
            provider_name="mock",
            identity=identity,
        )
        process_request(db, row)
        assert row.status == "review_required"
        assert not row.citations_json


def test_unconfigured_provider_has_auditable_mock_fallback() -> None:
    with get_session_factory()() as db:
        collection = db.scalar(select(Collection).where(Collection.name == "Operations handbook"))
        prompt = db.scalar(select(PromptTemplate).where(PromptTemplate.status == "released"))
        viewer = db.scalar(select(User).where(User.username == "viewer"))
        assert collection and prompt and viewer
        identity = Identity(viewer.id, viewer.username, viewer.display_name, viewer.role)
        row = create_knowledge_request(
            db,
            question="文件如何避免重複索引？",
            collection_id=collection.id,
            prompt=prompt,
            provider_name="openai",
            identity=identity,
        )
        process_request(db, row)
        assert row.provider == "mock"
        assert "not configured" in row.trace_json["fallback_reason"]


def test_worker_processes_queued_request() -> None:
    with get_session_factory()() as db:
        collection = db.scalar(select(Collection).where(Collection.name == "Operations handbook"))
        prompt = db.scalar(select(PromptTemplate).where(PromptTemplate.status == "released"))
        viewer = db.scalar(select(User).where(User.username == "viewer"))
        assert collection and prompt and viewer
        row = create_knowledge_request(
            db,
            question="事件處理後需要保存哪些紀錄？",
            collection_id=collection.id,
            prompt=prompt,
            provider_name="mock",
            identity=Identity(viewer.id, viewer.username, viewer.display_name, viewer.role),
        )
        db.commit()
        request_id = row.id

    with get_session_factory()() as db:
        assert process_next(db) == request_id
        processed = db.get(KnowledgeRequest, request_id)
        assert processed is not None
        assert processed.status in {"completed", "review_required"}
