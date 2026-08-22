from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import asdict, dataclass

from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, select
from sqlalchemy.orm import Session

from knowledge_ops.documents import deterministic_embedding
from knowledge_ops.models import EMBEDDING_DIMENSIONS, Chunk, Document


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    filename: str
    content: str
    score: float
    source_label: str

    def citation(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "filename": self.filename,
            "quote": self.content[:320],
            "score": round(self.score, 4),
            "source_label": self.source_label,
        }

    def trace(self) -> dict[str, object]:
        return asdict(self)


def _tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    latin = re.findall(r"[a-z0-9][a-z0-9_-]+", normalized)
    han = re.findall(r"[\u3400-\u9fff]", normalized)
    bigrams = ["".join(han[index : index + 2]) for index in range(max(0, len(han) - 1))]
    return set(latin + han + bigrams)


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(0.0, dot / (left_norm * right_norm))


def _keyword_score(question: str, content: str) -> float:
    question_tokens = _tokens(question)
    if not question_tokens:
        return 0.0
    overlap = question_tokens & _tokens(content)
    return len(overlap) / len(question_tokens)


def retrieve(
    db: Session, *, collection_id: str, question: str, limit: int = 4
) -> list[RetrievedChunk]:
    query_embedding = deterministic_embedding(question)
    statement = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.collection_id == collection_id, Document.status == "indexed")
    )

    # PostgreSQL uses pgvector to narrow the candidate set before the transparent keyword
    # reranker. SQLite scans the small demo collection to preserve zero-service reproducibility.
    if db.get_bind().dialect.name == "postgresql":
        distance = cast(Chunk.embedding, Vector(EMBEDDING_DIMENSIONS)).cosine_distance(
            query_embedding
        )
        statement = statement.add_columns(distance.label("vector_distance")).order_by(distance)
        statement = statement.limit(max(limit * 8, 32))

    candidates = [(row[0], row[1]) for row in db.execute(statement).all()]
    scored: list[RetrievedChunk] = []
    for chunk, document in candidates:
        vector_score = _cosine(query_embedding, list(chunk.embedding))
        keyword_score = _keyword_score(question, chunk.content)
        combined = 0.72 * vector_score + 0.28 * keyword_score
        scored.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=document.id,
                filename=document.filename,
                content=chunk.content,
                score=combined,
                source_label=document.source_label,
            )
        )
    return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]


def evidence_score(chunks: list[RetrievedChunk]) -> float:
    if not chunks:
        return 0.0
    best = chunks[0].score
    supporting = sum(item.score for item in chunks[:3]) / min(3, len(chunks))
    return round(0.7 * best + 0.3 * supporting, 4)
