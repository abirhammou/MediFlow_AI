from datetime import UTC, datetime

import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.database import get_db
from app.main import app
from app.security import create_access_token, hash_password


@pytest.fixture
def mock_database():
    client = AsyncMongoMockClient()
    database = client["mediflow_test"]
    app.dependency_overrides[get_db] = lambda: database
    yield database
    app.dependency_overrides.clear()
    client.close()


@pytest_asyncio.fixture
async def client(mock_database):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client


@pytest.fixture
def token_factory():
    def create_token(user_id: str, role: str = "patient") -> str:
        return create_access_token(user_id, role)

    return create_token


@pytest_asyncio.fixture
async def user_factory(mock_database):
    async def create_user(
        *,
        email: str = "user@example.test",
        full_name: str = "Test User",
        password: str = "password-123",
        role: str = "patient",
        status: str = "active",
        patient_id: ObjectId | None = None,
    ) -> dict:
        await mock_database["users"].create_index(
            "email",
            unique=True,
            name="email_unique",
        )
        user = {
            "_id": ObjectId(),
            "email": email.lower(),
            "full_name": full_name,
            "password_hash": hash_password(password),
            "role": role,
            "status": status,
            "patient_id": patient_id,
            "created_at": datetime.now(UTC),
        }
        await mock_database["users"].insert_one(user)
        return user

    return create_user
