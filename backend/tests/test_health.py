import pytest
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient

from app.core.config import settings
from app.core.db import get_db
from app.main import app


@pytest.mark.asyncio
async def test_health_pings_mongo(client, db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = await client.get("/api/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.asyncio
async def test_health_returns_503_when_mongo_is_down(client):
    unreachable = AsyncMongoClient("mongodb://127.0.0.1:1", serverSelectionTimeoutMS=200)
    app.dependency_overrides[get_db] = lambda: unreachable["mediflow"]
    try:
        response = await client.get("/api/health")
    finally:
        app.dependency_overrides.clear()
        await unreachable.close()

    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"


@pytest.mark.asyncio
async def test_llm_status_never_exposes_key(client):
    response = await client.get("/api/llm/status")

    assert response.status_code == 200
    assert response.json()["template"] == {"provider": "mock", "key_configured": False}
    assert set(response.json()) == {"appointments", "documents", "follow_up", "template"}
    assert "api_key" not in response.text


@pytest.mark.asyncio
async def test_documents_module_requires_authentication(client):
    response = await client.get("/api/documents/")

    assert response.status_code == 401


def test_openapi_contains_only_discovered_module_routes():
    paths = app.openapi()["paths"]

    assert "/api/documents/" in paths
    assert "/api/notes/" in paths
    assert "/api/llm/status" in paths
    assert set(paths) == {
        "/health",
        "/api/documents",
        "/api/documents/",
        "/api/documents/patient-options",
        "/api/documents/patients/{patient_id}/history",
        "/api/documents/{document_id}",
        "/api/documents/{document_id}/extract",
        "/api/documents/{document_id}/review",
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
        "/api/dashboard/summary",
        "/api/reports",
        "/api/reports/{report_id}",
        "/api/reports/{report_id}/archive",
        "/api/reports/{report_id}/finalize",
        "/api/reports/{report_id}/generate",
        "/api/patients",
        "/api/patients/duplicates",
        "/api/patients/deleted",
        "/api/patients/{patient_id}",
        "/api/patients/{patient_id}/restore",
        "/api/patients/{patient_id}/summaries",
        "/api/patients/{patient_id}/summaries/generate",
        "/api/patients/{patient_id}/summaries/current",
        "/api/patients/{patient_id}/summaries/{summary_id}",
        "/api/patients/{patient_id}/summaries/{summary_id}/validate",
        "/api/patients/{patient_id}/summaries/{summary_id}/reject",
        "/api/follow-up/tasks",
        "/api/follow-up/tasks/stats",
        "/api/follow-up/tasks/{task_id}",
        "/api/follow-up/reminders/generate",
        "/api/appointments",
        "/api/appointments/parse-request",
        "/api/appointments/{appointment_id}",
        "/api/appointments/{appointment_id}/cancel",
    }


def test_application_lifespan(monkeypatch, app_mongodb_uri):
    """Startup connects as mediflow_app and initialises Beanie, like `uvicorn app.main:app`."""
    monkeypatch.setattr(settings, "mongodb_uri", app_mongodb_uri)

    with TestClient(app) as test_client:
        assert test_client.get("/api/health").json() == {"status": "ok", "database": "ok"}