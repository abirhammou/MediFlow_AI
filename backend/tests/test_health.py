import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_llm_status_never_exposes_key(client):
    response = await client.get("/api/llm/status")

    assert response.status_code == 200
    assert response.json()["template"] == {"provider": "mock", "key_configured": False}
    assert set(response.json()) == {"documents", "template"}
    assert "api_key" not in response.text


@pytest.mark.asyncio
async def test_documents_module_returns_typed_501(client):
    response = await client.get("/api/documents/")

    assert response.status_code == 501
    assert response.json()["code"] == "not_implemented"


def test_openapi_contains_only_discovered_module_routes():
    paths = app.openapi()["paths"]

    assert "/api/documents/" in paths
    assert "/api/notes/" in paths
    assert "/api/llm/status" in paths
    assert set(paths) == {
        "/health",
        "/api/documents/",
        "/api/notes/",
        "/api/notes/summarize",
        "/api/notes/{note_id}",
        "/api/llm/status",
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/me",
        "/api/auth/change-password",
        "/api/users",
        "/api/users/{user_id}",
        "/api/users/{user_id}/approve",
        "/api/users/{user_id}/disable",
        "/api/users/{user_id}/enable",
        "/api/users/{user_id}/role",
        "/api/users/{user_id}/link-patient",
        "/api/users/{user_id}/unlink-patient",
    }


def test_application_lifespan():
    with TestClient(app) as test_client:
        assert test_client.get("/health").json() == {"status": "ok"}
