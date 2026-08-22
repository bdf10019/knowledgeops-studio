from __future__ import annotations

import argparse
import json
import sys

import uvicorn
from sqlalchemy import select

from knowledge_ops import __version__
from knowledge_ops.cache import get_cache
from knowledge_ops.config import get_settings
from knowledge_ops.database import get_engine, get_session_factory, init_database
from knowledge_ops.evaluation import run_evaluation
from knowledge_ops.models import Collection, PromptTemplate, User
from knowledge_ops.providers import ProviderRegistry
from knowledge_ops.security import Identity
from knowledge_ops.seed import seed_demo
from knowledge_ops.services import create_knowledge_request, process_request
from knowledge_ops.worker import run_worker


def initialize() -> dict[str, str]:
    init_database()
    with get_session_factory()() as db:
        return seed_demo(db)


def doctor() -> int:
    initialize()
    settings = get_settings()
    report = {
        "version": __version__,
        "database": get_engine().dialect.name,
        "redis": get_cache().status(),
        "demo_mode": settings.demo_mode,
        "providers": ProviderRegistry().list_info(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def run_demo(question: str) -> int:
    initialize()
    with get_session_factory()() as db:
        collection = db.scalar(select(Collection).where(Collection.name == "Operations handbook"))
        prompt = db.scalar(select(PromptTemplate).where(PromptTemplate.status == "released"))
        viewer = db.scalar(select(User).where(User.username == "viewer"))
        if collection is None or prompt is None or viewer is None:
            print("Demo seed data is incomplete", file=sys.stderr)
            return 1
        identity = Identity(viewer.id, viewer.username, viewer.display_name, viewer.role)
        row = create_knowledge_request(
            db,
            question=question,
            collection_id=collection.id,
            prompt=prompt,
            provider_name="mock",
            identity=identity,
        )
        process_request(db, row)
        db.commit()
        print(
            json.dumps(
                {
                    "request_id": row.id,
                    "status": row.status,
                    "answer": row.answer,
                    "citations": row.citations_json,
                    "evidence_score": row.evidence_score,
                    "provider": row.provider,
                    "prompt_sha256": row.trace_json.get("prompt_sha256"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


def evaluate_demo() -> int:
    initialize()
    with get_session_factory()() as db:
        prompt = db.scalar(select(PromptTemplate).where(PromptTemplate.status == "released"))
        admin = db.scalar(select(User).where(User.username == "admin"))
        if prompt is None or admin is None:
            print("Demo seed data is incomplete", file=sys.stderr)
            return 1
        run = run_evaluation(
            db,
            prompt=prompt,
            provider_name="mock",
            identity=Identity(admin.id, admin.username, admin.display_name, admin.role),
        )
        db.commit()
        print(
            json.dumps(
                {
                    "run_id": run.id,
                    "status": run.status,
                    "case_count": run.case_count,
                    "pass_rate": run.pass_rate,
                    "citation_rate": run.citation_rate,
                    "refusal_accuracy": run.refusal_accuracy,
                    "median_latency_ms": run.median_latency_ms,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="knowledgeops")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db")
    subparsers.add_parser("doctor")
    demo_parser = subparsers.add_parser("run-demo")
    demo_parser.add_argument("--question", default="Prompt 發布前要比較哪些品質指標？")
    subparsers.add_parser("evaluate")
    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    subparsers.add_parser("worker")
    args = parser.parse_args()

    if args.command == "init-db":
        initialize()
        print("Database initialized and demo data seeded.")
    elif args.command == "doctor":
        raise SystemExit(doctor())
    elif args.command == "run-demo":
        raise SystemExit(run_demo(args.question))
    elif args.command == "evaluate":
        raise SystemExit(evaluate_demo())
    elif args.command == "serve":
        initialize()
        uvicorn.run("knowledge_ops.api:app", host=args.host, port=args.port, reload=False)
    elif args.command == "worker":
        run_worker()


if __name__ == "__main__":
    main()
