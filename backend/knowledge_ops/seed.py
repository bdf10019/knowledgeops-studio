from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_ops.config import get_settings
from knowledge_ops.documents import ingest_document
from knowledge_ops.models import Collection, EvaluationCase
from knowledge_ops.services import (
    grant_demo_access,
    seed_default_prompt,
    seed_demo_identities,
)


def seed_demo(db: Session) -> dict[str, str]:
    users = seed_demo_identities(db)
    collection = db.scalar(select(Collection).where(Collection.name == "Operations handbook"))
    if collection is None:
        collection = Collection(
            name="Operations handbook",
            description=(
                "Synthetic policies and operating procedures for the offline demonstration."
            ),
            created_by=users["admin"].id,
        )
        db.add(collection)
        db.flush()
    grant_demo_access(db, collection, users)
    prompt = seed_default_prompt(db, users["admin"].id)

    content_root = get_settings().effective_content_root
    knowledge_dir = content_root / "examples" / "knowledge"
    for path in sorted(knowledge_dir.glob("*")):
        if path.is_file() and path.suffix.lower() in {".md", ".txt", ".csv", ".json", ".pdf"}:
            ingest_document(
                db,
                collection_id=collection.id,
                filename=path.name,
                content_type="text/markdown" if path.suffix.lower() == ".md" else "text/plain",
                data=path.read_bytes(),
                source_label="Project-original synthetic demonstration material",
                actor_id=users["admin"].id,
            )

    eval_path = content_root / "examples" / "evals" / "cases.jsonl"
    if eval_path.exists():
        for line in eval_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            exists = db.scalar(
                select(EvaluationCase).where(
                    EvaluationCase.collection_id == collection.id,
                    EvaluationCase.name == item["name"],
                )
            )
            if exists is None:
                db.add(
                    EvaluationCase(
                        collection_id=collection.id,
                        name=item["name"],
                        question=item["question"],
                        expected_terms=item.get("expected_terms", []),
                        should_answer=item.get("should_answer", True),
                    )
                )
    db.commit()
    return {"collection_id": collection.id, "prompt_id": prompt.id}
