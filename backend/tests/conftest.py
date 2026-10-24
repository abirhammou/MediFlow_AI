import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient
from pydantic import SecretStr
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings
from app.core.db import DOCUMENT_MODELS, create_client, get_db, init_db
from app.llm.client import litellm_module
from app.main import app
from app.modules.auth.models import Role, User
from app.security import create_access_token, hash_password

DATABASE_SCRIPTS = Path(__file__).resolve().parents[2] / "database"
MONGO_IMAGE = "mongo:7"
APP_USER = "mediflow_app"
APP_PASSWORD = "test-app-password"
DB_NAME = "mediflow"

# ---------------------------------------------------------------------
# LLM: tests never call a real provider
# ---------------------------------------------------------------------

PRIMARY_MODEL = "gemini/primary-test"
FALLBACK_MODEL = "groq/fallback-test"
TEST_GEMINI_KEY = "test-gemini-key-0123456789"
TEST_GROQ_KEY = "test-groq-key-0123456789"
FAKE_SUMMARY = (
    "Identité\n- Dossier PAT-2026-00001, 36 ans, Femme\n"
    "Couverture\n- CNAM\n"
    "Points administratifs\n- Préfère les rendez-vous le matin.\n"
    "À vérifier\n- Rien à signaler"
)


class FakeLLM:
    """Stands in for `litellm.acompletion`.

    `outcomes[model]` is a list consumed one call at a time (the last item
    repeats): a string is the answer, an exception is raised.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.outcomes: dict[str, list[str | Exception]] = {}

    def set(self, model: str, *outcomes: str | Exception) -> None:
        self.outcomes[model] = list(outcomes)

    def models_called(self) -> list[str]:
        return [call["model"] for call in self.calls]

    async def __call__(self, *, model: str, messages: list[dict[str, str]], **kwargs: Any):
        self.calls.append({"model": model, "messages": messages, **kwargs})
        queue = self.outcomes.get(model, [FAKE_SUMMARY])
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(outcome, Exception):
            raise outcome
        return litellm_module().ModelResponse(
            model=model.split("/", 1)[1],
            choices=[
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": outcome},
                }
            ],
            usage={"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
        )


@pytest.fixture(autouse=True)
def no_real_llm_calls(monkeypatch):
    """Any test reaching LiteLLM without `fake_llm` fails instead of calling the network."""

    async def forbidden(**_: Any):
        raise AssertionError("Real LLM call in a test: use the fake_llm fixture.")

    monkeypatch.setattr(litellm_module(), "acompletion", forbidden)


@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLM:
    """Real (non-mock) LLM settings, Gemini primary then Groq fallback, fake answers."""
    fake = FakeLLM()
    monkeypatch.setattr(litellm_module(), "acompletion", fake)
    monkeypatch.setattr(settings, "llm_mock", False)
    monkeypatch.setattr(settings, "llm_model", PRIMARY_MODEL)
    monkeypatch.setattr(settings, "llm_fallback_models", FALLBACK_MODEL)
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr(TEST_GEMINI_KEY))
    monkeypatch.setattr(settings, "groq_api_key", SecretStr(TEST_GROQ_KEY))
    monkeypatch.setattr(settings, "llm_max_retries", 1)
    return fake


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


# ---------------------------------------------------------------------
# Real MongoDB (Testcontainers): same image and init scripts as docker-compose.yml
# ---------------------------------------------------------------------


def _mongosh(container, *args: str) -> tuple[int, str]:
    command = [
        "mongosh",
        "--quiet",
        "-u",
        container.username,
        "-p",
        container.password,
        "--authenticationDatabase",
        "admin",
        DB_NAME,
        *args,
    ]
    exit_code, output = container.exec(command)
    return exit_code, output.decode(errors="replace")


@pytest.fixture(scope="session")
def mongo_container() -> Iterator:
    try:
        import docker

        docker.from_env().ping()
    except Exception as exc:
        pytest.skip(f"Docker is not reachable, MongoDB tests skipped: {exc}")

    from testcontainers.community.mongodb import MongoDbContainer

    container = MongoDbContainer(MONGO_IMAGE).with_env("MONGO_APP_PASSWORD", APP_PASSWORD)
    with container:
        # The entrypoint restarts mongod after creating the root user: wait for the final one.
        deadline = time.monotonic() + 60
        while _mongosh(container, "--eval", "db.adminCommand('ping')")[0] != 0:
            if time.monotonic() > deadline:
                raise RuntimeError("MongoDB test container did not become ready")
            time.sleep(0.5)
        for script in ("00-create-user.js", "mongo-init.js"):
            source = (DATABASE_SCRIPTS / script).read_text(encoding="utf-8")
            exit_code, output = _mongosh(container, "--eval", source)
            if exit_code != 0:
                raise RuntimeError(f"{script} failed:\n{output}")
        yield container


@pytest.fixture(scope="session")
def app_mongodb_uri(mongo_container) -> str:
    """Connection string of the application user (not root), like backend/.env."""
    host = mongo_container.get_container_host_ip()
    port = mongo_container.get_exposed_port(27017)
    return f"mongodb://{APP_USER}:{APP_PASSWORD}@{host}:{port}/{DB_NAME}?authSource={DB_NAME}"


@pytest_asyncio.fixture(scope="session")
async def mongo_client(app_mongodb_uri: str) -> AsyncIterator[AsyncMongoClient]:
    client = create_client(app_mongodb_uri)
    yield client
    await client.close()


@pytest_asyncio.fixture(scope="session")
async def reference_ids(mongo_client: AsyncMongoClient) -> dict[str, list]:
    """_id of the reference documents seeded by mongo-init.js (kept between tests)."""
    database = mongo_client[DB_NAME]
    return {
        name: await database[name].distinct("_id") for name in ("counters", "document_categories")
    }


@pytest_asyncio.fixture
async def db(
    mongo_client: AsyncMongoClient, reference_ids: dict[str, list]
) -> AsyncIterator[AsyncDatabase]:
    database = mongo_client[DB_NAME]
    await init_db(database)
    yield database
    for model in DOCUMENT_MODELS:
        name = model.Settings.name
        await database[name].delete_many({"_id": {"$nin": reference_ids.get(name, [])}})


# ---------------------------------------------------------------------
# Auth helpers (real MongoDB: the users validator is enforced)
# ---------------------------------------------------------------------


@pytest_asyncio.fixture
async def api_client(db: AsyncDatabase) -> AsyncIterator[AsyncClient]:
    """HTTP client whose routes use the Testcontainers database."""
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def token_factory():
    def create_token(user: User) -> str:
        return create_access_token(str(user.id), user.role.value)

    return create_token


@pytest.fixture
def user_factory(db: AsyncDatabase):
    async def create_user(
        *,
        email: str = "user@example.test",
        first_name: str = "Test",
        last_name: str = "User",
        password: str = "password-123",
        role: Role = Role.PATIENT,
        is_active: bool = True,
        patient_id: PydanticObjectId | None = None,
    ) -> User:
        user = User(
            email=email,
            password_hash=hash_password(password),
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=is_active,
            patient_id=patient_id,
        )
        return await user.insert()

    return create_user
