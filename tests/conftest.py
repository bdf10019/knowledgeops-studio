from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from knowledge_ops.api import app
from knowledge_ops.database import configure_database, get_session_factory, init_database
from knowledge_ops.seed import seed_demo


@pytest.fixture(autouse=True)
def isolated_database(tmp_path: Path) -> Generator[None, None, None]:
    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    engine = configure_database(database_url)
    init_database()
    with get_session_factory()() as db:
        seed_demo(db)
    yield
    engine.dispose()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def headers(username: str) -> dict[str, str]:
    return {"X-Demo-User": username}
