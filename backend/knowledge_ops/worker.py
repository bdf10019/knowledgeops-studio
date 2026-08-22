from __future__ import annotations

import logging
import signal
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_ops.config import get_settings
from knowledge_ops.database import get_session_factory, init_database
from knowledge_ops.models import KnowledgeRequest
from knowledge_ops.services import process_request

LOGGER = logging.getLogger("knowledge_ops.worker")


def process_next(db: Session) -> str | None:
    """Claim and process one submitted request.

    PostgreSQL uses SKIP LOCKED so multiple workers can safely share the queue. SQLite ignores
    the lock clause and is intentionally limited to one worker in the offline demo.
    """

    statement = (
        select(KnowledgeRequest)
        .where(KnowledgeRequest.status == "submitted")
        .order_by(KnowledgeRequest.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    row = db.scalar(statement)
    if row is None:
        return None
    request_id = row.id
    process_request(db, row)
    db.commit()
    return request_id


def run_worker() -> None:
    init_database()
    settings = get_settings()
    running = True

    def stop(_: int, __: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    LOGGER.info("KnowledgeOps worker started")
    while running:
        try:
            with get_session_factory()() as db:
                request_id = process_next(db)
            if request_id:
                LOGGER.info("Processed request %s", request_id)
            else:
                time.sleep(settings.worker_poll_seconds)
        except Exception:
            LOGGER.exception("Worker cycle failed")
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
