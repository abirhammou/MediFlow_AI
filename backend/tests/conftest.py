import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.database import get_db
from app.main import app


@pytest.fixture
def mock_database():
    client = AsyncMongoMockClient()
    database = client["mediflow_test"]
    app.dependency_overrides[get_db] = lambda: database
    yield database
    app.dependency_overrides.clear()
    client.close()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client
