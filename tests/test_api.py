from __future__ import annotations

from conftest import headers
from fastapi.testclient import TestClient


def test_health_and_provider_status(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["database"] == "sqlite"
    providers = client.get("/api/v1/providers", headers=headers("viewer"))
    assert providers.status_code == 200
    assert {item["name"] for item in providers.json()} == {
        "mock",
        "openai",
        "anthropic",
        "gemini",
    }


def test_unknown_identity_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/me", headers=headers("unknown"))
    assert response.status_code == 401


def test_viewer_cannot_create_collection(client: TestClient) -> None:
    response = client.post(
        "/api/v1/collections",
        headers=headers("viewer"),
        json={"name": "Private", "description": "Denied"},
    )
    assert response.status_code == 403


def test_editor_can_upload_and_document_is_deduplicated(client: TestClient) -> None:
    collection = client.get("/api/v1/collections", headers=headers("editor")).json()[0]
    files = {
        "file": (
            "new-policy.md",
            b"# Policy\n\nA sufficiently long synthetic policy body.",
            "text/markdown",
        )
    }
    first = client.post(
        f"/api/v1/collections/{collection['id']}/documents",
        headers=headers("editor"),
        files=files,
        data={"source_label": "test"},
    )
    second = client.post(
        f"/api/v1/collections/{collection['id']}/documents",
        headers=headers("editor"),
        files=files,
        data={"source_label": "test"},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_request_end_to_end_and_role_review(client: TestClient) -> None:
    collection = client.get("/api/v1/collections", headers=headers("viewer")).json()[0]
    response = client.post(
        "/api/v1/requests",
        headers=headers("viewer"),
        json={
            "question": "存取權限需要哪些核准？",
            "collection_id": collection["id"],
            "provider": "mock",
            "process_now": True,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["citations_json"]

    viewer_review = client.post(
        f"/api/v1/requests/{body['id']}/review",
        headers=headers("viewer"),
        json={"answer": body["answer"], "approve": True},
    )
    assert viewer_review.status_code == 403

    reviewer_review = client.post(
        f"/api/v1/requests/{body['id']}/review",
        headers=headers("reviewer"),
        json={"answer": body["answer"], "approve": True, "note": "Verified"},
    )
    assert reviewer_review.status_code == 200


def test_prompt_release_requires_admin(client: TestClient) -> None:
    payload = {
        "name": "Grounded knowledge response",
        "system_prompt": "Use only the supplied evidence and return a traceable answer.",
        "user_template": "Question: {question}. Cite the authorized evidence.",
        "provider": "mock",
        "model": "mock-grounded-v1",
    }
    created = client.post("/api/v1/prompts", headers=headers("editor"), json=payload)
    assert created.status_code == 201
    denied = client.post(
        f"/api/v1/prompts/{created.json()['id']}/release", headers=headers("editor")
    )
    assert denied.status_code == 403
    released = client.post(
        f"/api/v1/prompts/{created.json()['id']}/release", headers=headers("admin")
    )
    assert released.status_code == 200
    assert released.json()["status"] == "released"


def test_evaluation_run_and_dashboard(client: TestClient) -> None:
    prompt = client.get("/api/v1/prompts", headers=headers("editor")).json()[0]
    run = client.post(
        "/api/v1/evaluations/runs",
        headers=headers("editor"),
        json={"prompt_id": prompt["id"], "provider": "mock"},
    )
    assert run.status_code == 201
    assert run.json()["case_count"] == 6
    assert 0 <= run.json()["pass_rate"] <= 1
    dashboard = client.get("/api/v1/dashboard", headers=headers("editor"))
    assert dashboard.status_code == 200
    assert dashboard.json()["evaluation_runs"] == 1


def test_audit_log_is_admin_only(client: TestClient) -> None:
    assert client.get("/api/v1/audit", headers=headers("viewer")).status_code == 403
    response = client.get("/api/v1/audit", headers=headers("admin"))
    assert response.status_code == 200
    assert response.json()
