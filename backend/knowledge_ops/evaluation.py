from __future__ import annotations

import statistics

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_ops.models import (
    EvaluationCase,
    EvaluationResult,
    EvaluationRun,
    KnowledgeRequest,
    PromptTemplate,
)
from knowledge_ops.providers import ProviderRegistry
from knowledge_ops.security import Identity
from knowledge_ops.services import create_knowledge_request, process_request


def run_evaluation(
    db: Session,
    *,
    prompt: PromptTemplate,
    provider_name: str,
    identity: Identity,
    registry: ProviderRegistry | None = None,
) -> EvaluationRun:
    registry = registry or ProviderRegistry()
    provider = registry.get(provider_name)
    run = EvaluationRun(
        prompt_id=prompt.id,
        provider=provider_name,
        model=provider.default_model,
        status="running",
        created_by=identity.id,
    )
    db.add(run)
    db.flush()

    cases = list(
        db.scalars(
            select(EvaluationCase)
            .where(EvaluationCase.collection_id.is_not(None))
            .order_by(EvaluationCase.name)
        )
    )
    results: list[EvaluationResult] = []
    latencies: list[float] = []
    for case in cases:
        request_row = create_knowledge_request(
            db,
            question=case.question,
            collection_id=case.collection_id,
            prompt=prompt,
            provider_name=provider_name,
            identity=identity,
        )
        process_request(db, request_row, registry=registry)
        answer_lower = request_row.answer.lower()
        expected = [term.lower() for term in case.expected_terms]
        matched = sum(1 for term in expected if term in answer_lower)
        term_recall = matched / len(expected) if expected else 1.0
        refused = request_row.status == "review_required" and not request_row.citations_json
        refusal_correct = refused == (not case.should_answer)
        passed = refusal_correct and (term_recall >= 0.5 if case.should_answer else True)
        result = EvaluationResult(
            run_id=run.id,
            case_id=case.id,
            answer=request_row.answer,
            passed=passed,
            term_recall=term_recall,
            citation_present=bool(request_row.citations_json),
            refused=refused,
            latency_ms=request_row.latency_ms,
            detail_json={
                "request_id": request_row.id,
                "status": request_row.status,
                "evidence_score": request_row.evidence_score,
            },
        )
        db.add(result)
        results.append(result)
        latencies.append(request_row.latency_ms)

    run.case_count = len(results)
    if results:
        run.pass_rate = sum(item.passed for item in results) / len(results)
        run.citation_rate = sum(item.citation_present for item in results) / len(results)
        run.refusal_accuracy = sum(
            item.refused == (not db.get(EvaluationCase, item.case_id).should_answer)  # type: ignore[union-attr]
            for item in results
        ) / len(results)
        run.median_latency_ms = statistics.median(latencies)
    run.status = "completed"
    db.flush()
    return run


def evaluation_requests(db: Session, run_id: str) -> list[KnowledgeRequest]:
    result_rows = list(
        db.scalars(select(EvaluationResult).where(EvaluationResult.run_id == run_id))
    )
    request_ids = [item.detail_json.get("request_id") for item in result_rows]
    if not request_ids:
        return []
    return list(db.scalars(select(KnowledgeRequest).where(KnowledgeRequest.id.in_(request_ids))))
