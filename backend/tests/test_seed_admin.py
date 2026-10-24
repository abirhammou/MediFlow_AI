import pytest
from mongomock_motor import AsyncMongoMockClient

from scripts.seed_admin import seed_admin


@pytest.mark.asyncio
async def test_seed_admin_rejects_password_shorter_than_twelve_characters():
    client = AsyncMongoMockClient()
    database = client["seed_admin_test"]

    with pytest.raises(ValueError, match="12 caractères"):
        await seed_admin(
            database,
            email="admin@example.test",
            password="short-pass",
        )

    assert await database["users"].count_documents({"role": "admin"}) == 0
    client.close()


@pytest.mark.asyncio
async def test_seed_admin_creates_admin_only_once(capsys):
    client = AsyncMongoMockClient()
    database = client["seed_admin_test"]
    password = "test-admin-password"

    created_id = await seed_admin(
        database,
        email="Admin@Example.test",
        password=password,
    )
    second_result = await seed_admin(
        database,
        email="another-admin@example.test",
        password="another-test-password",
    )

    admin = await database["users"].find_one({"role": "admin"})
    output = capsys.readouterr().out
    assert created_id is not None
    assert second_result is None
    assert await database["users"].count_documents({"role": "admin"}) == 1
    assert admin is not None
    assert admin["email"] == "admin@example.test"
    assert admin["password_hash"] != password
    assert password not in output
    client.close()
