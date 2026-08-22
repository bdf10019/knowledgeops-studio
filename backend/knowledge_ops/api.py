from __future__ import annotations

import hashlib
from collections import Counter
from contextlib import asynccontextmanager
from statistics import median

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowledge_ops import __version__
from knowledge_ops.cache import get_cache
from knowledge_ops.config import get_settings
from knowledge_ops.database import get_db, get_engine, get_session_factory, init_database
from knowledge_ops.documents import DocumentError, ingest_document
from knowledge_ops.evaluation import run_evaluation
from knowledge_ops.models import (
    AuditLog,
    Chunk,
    Collection,
    CollectionAccess,
    Document,
    EvaluationCase,
    EvaluationRun,
    KnowledgeRequest,
    PromptTemplate,
    User,
    WorkflowEvent,
)
from knowledge_ops.providers import ProviderRegistry
from knowledge_ops.schemas import (
    AccessGrantCreate,
    AuditOut,
    CollectionCreate,
    CollectionOut,
    DashboardOut,
    DocumentOut,
    EvaluationCaseCreate,
    EvaluationCaseOut,
    EvaluationRunCreate,
    EvaluationRunOut,
    HealthResponse,
    PromptCreate,
    PromptOut,
    ProviderOut,
    RequestCreate,
    RequestOut,
    ReviewInput,
    UserOut,
    WorkflowEventOut,
)
from knowledge_ops.security import (
    REVIEW_ROLES,
    WRITE_ROLES,
    Identity,
    can_access_collection,
    demo_username,
    require_collection_access,
    require_roles,
    resolve_identity,
)
from knowledge_ops.seed import seed_demo
from knowledge_ops.services import (
    audit,
    create_knowledge_request,
    create_prompt_version,
    process_request,
    release_prompt,
    released_prompt,
)


def current_identity(
    username: str = Depends(demo_username), db: Session = Depends(get_db)
) -> Identity:
    return resolve_identity(db, username)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    if get_settings().demo_mode:
        with get_session_factory()() as db:
            seed_demo(db)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Multi-model enterprise knowledge workflow and prompt evaluation API",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=__version__,
            database=get_engine().dialect.name,
            redis=get_cache().status(),
            demo_mode=settings.demo_mode,
        )

    @app.get("/api/v1/me", response_model=UserOut, tags=["identity"])
    def me(identity: Identity = Depends(current_identity)) -> UserOut:
        return UserOut(**identity.__dict__)

    @app.get("/api/v1/providers", response_model=list[ProviderOut], tags=["models"])
    def providers(_: Identity = Depends(current_identity)) -> list[ProviderOut]:
        return [ProviderOut.model_validate(item) for item in ProviderRegistry().list_info()]

    @app.get("/api/v1/collections", response_model=list[CollectionOut], tags=["knowledge"])
    def collections(
        db: Session = Depends(get_db), identity: Identity = Depends(current_identity)
    ) -> list[CollectionOut]:
        rows = list(db.scalars(select(Collection).order_by(Collection.name)))
        output: list[CollectionOut] = []
        for row in rows:
            if not can_access_collection(db, identity, row.id):
                continue
            count = db.scalar(
                select(func.count(Document.id)).where(
                    Document.collection_id == row.id, Document.status != "deleted"
                )
            )
            output.append(
                CollectionOut.model_validate(row).model_copy(
                    update={
                        "document_count": count or 0,
                        "can_write": can_access_collection(db, identity, row.id, write=True),
                    }
                )
            )
        return output

    @app.post(
        "/api/v1/collections",
        response_model=CollectionOut,
        status_code=status.HTTP_201_CREATED,
        tags=["knowledge"],
    )
    def create_collection(
        payload: CollectionCreate,
        db: Session = Depends(get_db),
        identity: Identity = Depends(current_identity),
    ) -> CollectionOut:
        require_roles(identity, WRITE_ROLES)
        if db.scalar(select(Collection).where(Collection.name == payload.name.strip())):
            raise HTTPException(status_code=409, detail="Collection name already exists")
        row = Collection(
            name=payload.name.strip(),
            description=payload.description.strip(),
            created_by=identity.id,
        )
        db.add(row)
        db.flush()
        db.add(CollectionAccess(collection_id=row.id, user_id=identity.id, can_write=True))
        audit(
            db,
            actor_id=identity.id,
            action="collection.create",
            resource_type="collection",
            resource_id=row.id,
        )
        db.commit()
        return CollectionOut.model_validate(row).model_copy(
            update={"document_count": 0, "can_write": True}
        )

    @app.post("/api/v1/collections/{collection_id}/access", tags=["knowledge"])
    def grant_access(
        collection_id: str,
        payload: AccessGrantCreate,
        db: Session = Depends(get_db),
        identity: Identity = Depends(current_identity),
    ) -> dict[str, object]:
        require_roles(identity, {"admin"})
        collection = db.get(Collection, collection_id)
        user = db.scalar(select(User).where(User.username == payload.username))
        if collection is None or user is None:
            raise HTTPException(status_code=404, detail="Collection or user not found")
        grant = db.scalar(
            select(CollectionAccess).where(
                CollectionAccess.collection_id == collection_id,
                CollectionAccess.user_id == user.id,
            )
        )
        if grant is None:
            grant = CollectionAccess(
                collection_id=collection_id, user_id=user.id, can_write=payload.can_write
            )
            db.add(grant)
        else:
            grant.can_write = payload.can_write
        audit(
            db,
            actor_id=identity.id,
            action="collection.grant",
            resource_type="collection",
            resource_id=collection_id,
            detail={"username": payload.username, "can_write": payload.can_write},
        )
        db.commit()
        return {"username": payload.username, "can_write": payload.can_write}

    @app.get(
        "/api/v1/collections/{collection_id}/documents",
        response_model=list[DocumentOut],
        tags=["knowledge"],
    )
    def documents(
        collection_id: str,
        db: Session = Depends(get_db),
        identity: Identity = Depends(current_identity),
    ) -> list[DocumentOut]:
        require_collection_access(db, identity, collection_id)
        rows = list(
            db.scalars(
                select(Document)
                .where(Document.collection_id == collection_id, Document.status != "deleted")
                .order_by(Document.created_at.desc())
            )
        )
        return [
            DocumentOut.model_validate(row).model_copy(
                update={
                    "chunk_count": db.scalar(
                        select(func.count(Chunk.id)).where(Chunk.document_id == row.id)
                    )
                    or 0
                }
            )
            for row in rows
        ]

    @app.post(
        "/api/v1/collections/{collection_id}/documents",
        response_model=DocumentOut,
        status_code=status.HTTP_201_CREATED,
        tags=["knowledge"],
    )
    async def upload_document(
        collection_id: str,
        file: UploadFile = File(...),
        source_label: str = Form(default=""),
        db: Session = Depends(get_db),
        identity: Identity = Depends(current_identity),
    ) -> DocumentOut:
        require_collection_access(db, identity, collection_id, write=True)
        data = await file.read(settings.upload_limit_bytes + 1)
        if len(data) > settings.upload_limit_bytes:
            raise HTTPException(status_code=413, detail="Document exceeds the upload limit")
        try:
            row, created = ingest_document(
                db,
                collection_id=collection_id,
                filename=file.filename or "document.txt",
                content_type=file.content_type or "application/octet-stream",
                data=data,
                source_label=source_label,
                actor_id=identity.id,
            )
        except DocumentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        audit(
            db,
            actor_id=identity.id,
            action="document.ingest" if created else "document.deduplicate",
            resource_type="document",
            resource_id=row.id,
            detail={"sha256": row.sha256, "filename": row.filename},
        )
        db.commit()
        count = db.scalar(select(func.count(Chunk.id)).where(Chunk.document_id == row.id)) or 0
        return DocumentOut.model_validate(row).model_copy(update={"chunk_count": count})

    @app.delete("/api/v1/documents/{document_id}", status_code=204, tags=["knowledge"])
    def delete_document(
        document_id: str,
        db: Session = Depends(get_db),
        identity: Identity = Depends(current_identity),
    ) -> None:
        row = db.get(Document, document_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Document not found")
        require_collection_access(db, identity, row.collection_id, write=True)
        row.status = "deleted"
        audit(
            db,
            actor_id=identity.id,
            action="document.delete",
            resource_type="document",
            resource_id=row.id,
            detail={"soft_delete": True},
        )
        db.commit()

    @app.get("/api/v1/prompts", response_model=list[PromptOut], tags=["prompts"])
    def prompts(
        db: Session = Depends(get_db), _: Identity = Depends(current_identity)
    ) -> list[PromptTemplate]:
        return list(
            db.scalars(
                select(PromptTemplate).order_by(PromptTemplate.name, PromptTemplate.version.desc())
            )
        )

    @app.post(
        "/api/v1/prompts",
        response_model=PromptOut,
        status_code=status.HTTP_201_CREATED,
        tags=["prompts"],
    )
    def create_prompt(
        payload: PromptCreate,
        db: Session = Depends(get_db),
        identity: Identity = Depends(current_identity),
    ) -> PromptTemplate:
        require_roles(identity, WRITE_ROLES)
        row = create_prompt_version(
            db,
            name=payload.name,
            system_prompt=payload.system_prompt,
            user_template=payload.user_template,
            provider=payload.provider,
            model=payload.model,
            temperature=payload.temperature,
            retrieval_k=payload.retrieval_k,
            min_evidence_score=payload.min_evidence_score,
            actor_id=identity.id,
        )
        db.commit()
        return row

    @app.post("/api/v1/prompts/{prompt_id}/release", response_model=PromptOut, tags=["prompts"])
    def publish_prompt(
        prompt_id: str,
        db: Session = Depends(get_db),
        identity: Identity = Depends(current_identity),
    ) -> PromptTemplate:
        require_roles(identity, {"admin"})
        row = db.get(PromptTemplate, prompt_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Prompt not found")
        release_prompt(db, row, identity.id)
        db.commit()
        return row

    @app.get("/api/v1/requests", response_model=list[RequestOut], tags=["workflow"])
    def requests(
        db: Session = Depends(get_db), identity: Identity = Depends(current_identity)
    ) -> list[KnowledgeRequest]:
        rows = list(
            db.scalars(select(KnowledgeRequest).order_by(KnowledgeRequest.created_at.desc()))
        )
        return [
            row
            for row in rows
            if (row.user_id == identity.id or identity.role in REVIEW_ROLES)
            and can_access_collection(db, identity, row.collection_id)
        ]

    @app.post(
        "/api/v1/requests",
        response_model=RequestOut,
        status_code=status.HTTP_201_CREATED,
        tags=["workflow"],
    )
    def submit_request(
        payload: RequestCreate,
        db: Session = Depends(get_db),
        identity: Identity = Depends(current_identity),
    ) -> KnowledgeRequest:
        require_collection_access(db, identity, payload.collection_id)
        rate_key = hashlib.sha256(identity.id.encode("utf-8")).hexdigest()[:24]
        request_count = get_cache().increment(f"rate:knowledge:{rate_key}", ttl_seconds=60)
        if request_count > settings.requests_per_minute:
            raise HTTPException(status_code=429, detail="Knowledge request rate limit exceeded")
        prompt = (
            db.get(PromptTemplate, payload.prompt_id) if payload.prompt_id else released_prompt(db)
        )
        if prompt is None:
            raise HTTPException(status_code=409, detail="No released prompt is available")
        row = create_knowledge_request(
            db,
            question=payload.question,
            collection_id=payload.collection_id,
            prompt=prompt,
            provider_name=payload.provider,
            identity=identity,
        )
        if payload.process_now:
            process_request(db, row)
        db.commit()
        return row

    @app.post("/api/v1/requests/{request_id}/process", response_model=RequestOut, tags=["workflow"])
    def run_request(
        request_id: str,
        db: Session = Depends(get_db),
        identity: Identity = Depends(current_identity),
    ) -> KnowledgeRequest:
        row = db.get(KnowledgeRequest, request_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Request not found")
        if row.user_id != identity.id and identity.role not in REVIEW_ROLES:
            raise HTTPException(status_code=403, detail="Request access denied")
        require_collection_access(db, identity, row.collection_id)
        row.error = ""
        process_request(db, row)
        db.commit()
        return row

    @app.get(
        "/api/v1/requests/{request_id}/events",
        response_model=list[WorkflowEventOut],
        tags=["workflow"],
    )
    def request_events(
        request_id: str,
        db: Session = Depends(get_db),
        identity: Identity = Depends(current_identity),
    ) -> list[WorkflowEvent]:
        row = db.get(KnowledgeRequest, request_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Request not found")
        require_collection_access(db, identity, row.collection_id)
        return list(
            db.scalars(
                select(WorkflowEvent)
                .where(WorkflowEvent.request_id == request_id)
                .order_by(WorkflowEvent.created_at)
            )
        )

    @app.post("/api/v1/requests/{request_id}/review", response_model=RequestOut, tags=["workflow"])
    def review_request(
        request_id: str,
        payload: ReviewInput,
        db: Session = Depends(get_db),
        identity: Identity = Depends(current_identity),
    ) -> KnowledgeRequest:
        require_roles(identity, REVIEW_ROLES)
        row = db.get(KnowledgeRequest, request_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Request not found")
        require_collection_access(db, identity, row.collection_id)
        row.answer = payload.answer.strip()
        row.status = "completed" if payload.approve else "rejected"
        row.needs_review = False
        db.add(
            WorkflowEvent(
                request_id=row.id,
                state=row.status,
                detail=f"Human review by {identity.username}: {payload.note}",
            )
        )
        audit(
            db,
            actor_id=identity.id,
            action="request.review",
            resource_type="knowledge_request",
            resource_id=row.id,
            detail={"approved": payload.approve, "note": payload.note},
        )
        db.commit()
        return row

    @app.get("/api/v1/evaluations/cases", response_model=list[EvaluationCaseOut], tags=["evals"])
    def evaluation_cases(
        db: Session = Depends(get_db), identity: Identity = Depends(current_identity)
    ) -> list[EvaluationCase]:
        rows = list(db.scalars(select(EvaluationCase).order_by(EvaluationCase.name)))
        return [row for row in rows if can_access_collection(db, identity, row.collection_id)]

    @app.post(
        "/api/v1/evaluations/cases",
        response_model=EvaluationCaseOut,
        status_code=201,
        tags=["evals"],
    )
    def create_evaluation_case(
        payload: EvaluationCaseCreate,
        db: Session = Depends(get_db),
        identity: Identity = Depends(current_identity),
    ) -> EvaluationCase:
        require_roles(identity, WRITE_ROLES)
        require_collection_access(db, identity, payload.collection_id, write=True)
        row = EvaluationCase(**payload.model_dump())
        db.add(row)
        db.commit()
        return row

    @app.get("/api/v1/evaluations/runs", response_model=list[EvaluationRunOut], tags=["evals"])
    def evaluation_runs(
        db: Session = Depends(get_db), _: Identity = Depends(current_identity)
    ) -> list[EvaluationRun]:
        return list(db.scalars(select(EvaluationRun).order_by(EvaluationRun.created_at.desc())))

    @app.post(
        "/api/v1/evaluations/runs",
        response_model=EvaluationRunOut,
        status_code=201,
        tags=["evals"],
    )
    def start_evaluation(
        payload: EvaluationRunCreate,
        db: Session = Depends(get_db),
        identity: Identity = Depends(current_identity),
    ) -> EvaluationRun:
        require_roles(identity, WRITE_ROLES | REVIEW_ROLES)
        prompt = db.get(PromptTemplate, payload.prompt_id)
        if prompt is None:
            raise HTTPException(status_code=404, detail="Prompt not found")
        run = run_evaluation(
            db,
            prompt=prompt,
            provider_name=(payload.provider or prompt.provider),
            identity=identity,
        )
        db.commit()
        return run

    @app.get("/api/v1/audit", response_model=list[AuditOut], tags=["governance"])
    def audit_logs(
        db: Session = Depends(get_db), identity: Identity = Depends(current_identity)
    ) -> list[AuditLog]:
        require_roles(identity, {"admin"})
        return list(db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)))

    @app.get("/api/v1/dashboard", response_model=DashboardOut, tags=["analytics"])
    def dashboard(
        db: Session = Depends(get_db), identity: Identity = Depends(current_identity)
    ) -> DashboardOut:
        rows = [
            row
            for row in db.scalars(select(KnowledgeRequest))
            if can_access_collection(db, identity, row.collection_id)
            and (row.user_id == identity.id or identity.role in REVIEW_ROLES)
        ]
        completed = [row for row in rows if row.status == "completed"]
        with_citations = [row for row in completed if row.citations_json]
        return DashboardOut(
            total_requests=len(rows),
            completed_requests=len(completed),
            review_queue=sum(row.status == "review_required" for row in rows),
            document_count=db.scalar(
                select(func.count(Document.id)).where(Document.status != "deleted")
            )
            or 0,
            prompt_versions=db.scalar(select(func.count(PromptTemplate.id))) or 0,
            evaluation_runs=db.scalar(select(func.count(EvaluationRun.id))) or 0,
            median_latency_ms=median([row.latency_ms for row in completed]) if completed else 0,
            citation_rate=len(with_citations) / len(completed) if completed else 0,
            provider_counts=dict(Counter(row.provider for row in rows)),
        )

    return app


app = create_app()
