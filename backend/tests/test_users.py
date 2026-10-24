import pytest
from bson import ObjectId

from app.errors import APIError
from app.modules.users.repository import UsersRepository
from app.modules.users.service import UsersService


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["doctor", "secretary", "patient"])
async def test_user_management_is_admin_only(client, user_factory, token_factory, role):
    user = await user_factory(email=f"{role}@example.test", role=role)
    headers = {"Authorization": f"Bearer {token_factory(str(user['_id']), role)}"}

    response = await client.get("/api/users", headers=headers)
    unauthenticated = await client.get("/api/users")

    assert response.status_code == 403
    assert unauthenticated.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("user_status", ["pending", "disabled"])
async def test_non_active_accounts_cannot_use_users_routes(
    client,
    user_factory,
    token_factory,
    user_status,
):
    user = await user_factory(
        email=f"{user_status}@example.test",
        role="admin",
        status=user_status,
    )
    headers = {"Authorization": f"Bearer {token_factory(str(user['_id']), 'admin')}"}

    response = await client.get("/api/users", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Le compte n'est pas actif."


@pytest.mark.asyncio
async def test_list_users_filters_and_paginates(client, user_factory, token_factory):
    admin = await user_factory(email="admin@example.test", role="admin")
    await user_factory(
        email="doctor-one@example.test",
        role="doctor",
        status="pending",
    )
    await user_factory(
        email="doctor-two@example.test",
        role="doctor",
        status="pending",
    )
    await user_factory(
        email="secretary@example.test",
        role="secretary",
        status="pending",
    )
    headers = {"Authorization": f"Bearer {token_factory(str(admin['_id']), 'admin')}"}

    first_page = await client.get(
        "/api/users?status=pending&role=doctor&page=1&size=1",
        headers=headers,
    )
    second_page = await client.get(
        "/api/users?status=pending&role=doctor&page=2&size=1",
        headers=headers,
    )

    assert first_page.status_code == second_page.status_code == 200
    assert first_page.json()["total"] == 2
    assert first_page.json()["page"] == 1
    assert first_page.json()["size"] == 1
    assert len(first_page.json()["items"]) == len(second_page.json()["items"]) == 1
    assert first_page.json()["items"][0]["id"] != second_page.json()["items"][0]["id"]
    assert all(
        "password_hash" not in item
        for item in first_page.json()["items"] + second_page.json()["items"]
    )


@pytest.mark.asyncio
async def test_admin_can_create_active_user_without_exposing_password_hash(
    client,
    user_factory,
    token_factory,
    mock_database,
):
    admin = await user_factory(email="admin@example.test", role="admin")
    headers = {"Authorization": f"Bearer {token_factory(str(admin['_id']), 'admin')}"}

    response = await client.post(
        "/api/users",
        headers=headers,
        json={
            "email": "New.User@Example.test",
            "password": "long-enough-password",
            "full_name": "New User",
            "role": "doctor",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "new.user@example.test"
    assert response.json()["status"] == "active"
    assert "password_hash" not in response.json()
    stored = await mock_database["users"].find_one({"email": "new.user@example.test"})
    assert stored is not None
    assert stored["password_hash"] != "long-enough-password"


@pytest.mark.asyncio
async def test_admin_can_read_change_role_disable_enable_and_delete_user(
    client,
    user_factory,
    token_factory,
):
    admin = await user_factory(email="admin@example.test", role="admin")
    target = await user_factory(email="target@example.test", role="patient")
    headers = {"Authorization": f"Bearer {token_factory(str(admin['_id']), 'admin')}"}

    read_user = await client.get(f"/api/users/{target['_id']}", headers=headers)
    changed_role = await client.patch(
        f"/api/users/{target['_id']}/role",
        headers=headers,
        json={"role": "secretary"},
    )
    disabled = await client.patch(
        f"/api/users/{target['_id']}/disable",
        headers=headers,
    )
    enabled = await client.patch(
        f"/api/users/{target['_id']}/enable",
        headers=headers,
    )
    deleted = await client.delete(f"/api/users/{target['_id']}", headers=headers)

    assert read_user.status_code == 200
    assert read_user.json()["id"] == str(target["_id"])
    assert changed_role.status_code == 200
    assert changed_role.json()["role"] == "secretary"
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert enabled.status_code == 200
    assert enabled.json()["status"] == "active"
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "disabled"
    assert all(
        "password_hash" not in response.json()
        for response in (read_user, changed_role, disabled, enabled, deleted)
    )


@pytest.mark.asyncio
async def test_admin_can_approve_pending_user_then_user_can_login(
    client,
    user_factory,
    token_factory,
):
    admin = await user_factory(email="admin@example.test", role="admin")
    pending = await user_factory(
        email="doctor@example.test",
        password="doctor-password",
        role="doctor",
        status="pending",
    )
    admin_headers = {"Authorization": f"Bearer {token_factory(str(admin['_id']), 'admin')}"}
    pending_headers = {
        "Authorization": f"Bearer {token_factory(str(pending['_id']), 'doctor')}",
    }

    blocked_before_approval = await client.get("/api/auth/me", headers=pending_headers)
    approval = await client.patch(
        f"/api/users/{pending['_id']}/approve",
        headers=admin_headers,
    )
    login = await client.post(
        "/api/auth/login",
        data={"username": "doctor@example.test", "password": "doctor-password"},
    )

    assert blocked_before_approval.status_code == 403
    assert approval.status_code == 200
    assert approval.json()["status"] == "active"
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_self_or_remove_own_admin_role(
    client,
    user_factory,
    token_factory,
    mock_database,
):
    admin = await user_factory(email="admin@example.test", role="admin")
    headers = {"Authorization": f"Bearer {token_factory(str(admin['_id']), 'admin')}"}

    disabled = await client.patch(
        f"/api/users/{admin['_id']}/disable",
        headers=headers,
    )
    deleted = await client.delete(f"/api/users/{admin['_id']}", headers=headers)
    demoted = await client.patch(
        f"/api/users/{admin['_id']}/role",
        headers=headers,
        json={"role": "doctor"},
    )

    assert disabled.status_code == deleted.status_code == 400
    assert disabled.json()["code"] == "self_deactivation"
    assert deleted.json()["code"] == "self_deactivation"
    assert demoted.status_code == 400
    assert demoted.json()["code"] == "self_admin_role"
    unchanged = await mock_database["users"].find_one({"_id": admin["_id"]})
    assert unchanged is not None
    assert unchanged["role"] == "admin"
    assert unchanged["status"] == "active"


@pytest.mark.asyncio
async def test_service_protects_last_active_admin(mock_database):
    admin = await mock_database["users"].insert_one(
        {
            "_id": ObjectId(),
            "email": "only-admin@example.test",
            "full_name": "Only Admin",
            "password_hash": "irrelevant",
            "role": "admin",
            "status": "active",
            "patient_id": None,
        },
    )
    service = UsersService(UsersRepository(mock_database))

    with pytest.raises(APIError) as exc_info:
        await service.disable(str(admin.inserted_id), {"_id": ObjectId()})

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "last_admin"
    stored_admin = await mock_database["users"].find_one({"_id": admin.inserted_id})
    assert stored_admin is not None
    assert stored_admin["status"] == "active"


@pytest.mark.asyncio
async def test_admin_and_secretary_can_link_and_unlink_patient(
    client,
    user_factory,
    token_factory,
):
    target = await user_factory(email="patient@example.test", role="patient")
    admin = await user_factory(email="admin@example.test", role="admin")
    secretary = await user_factory(email="secretary@example.test", role="secretary")
    patient_id = "unverified-patient-id"

    linked_by_secretary = await client.patch(
        f"/api/users/{target['_id']}/link-patient",
        headers={"Authorization": f"Bearer {token_factory(str(secretary['_id']), 'secretary')}"},
        json={"patient_id": patient_id},
    )
    unlinked_by_admin = await client.patch(
        f"/api/users/{target['_id']}/unlink-patient",
        headers={"Authorization": f"Bearer {token_factory(str(admin['_id']), 'admin')}"},
    )

    assert linked_by_secretary.status_code == 200
    assert linked_by_secretary.json()["patient_id"] == patient_id
    assert unlinked_by_admin.status_code == 200
    assert unlinked_by_admin.json()["patient_id"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["doctor", "patient"])
async def test_only_admin_and_secretary_can_link_patient(
    client,
    user_factory,
    token_factory,
    role,
):
    actor = await user_factory(email=f"{role}@example.test", role=role)
    target = await user_factory(email="target@example.test")
    headers = {"Authorization": f"Bearer {token_factory(str(actor['_id']), role)}"}

    response = await client.patch(
        f"/api/users/{target['_id']}/link-patient",
        headers=headers,
        json={"patient_id": "patient-id"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_invalid_user_id_returns_not_found(client, user_factory, token_factory):
    admin = await user_factory(email="admin@example.test", role="admin")
    headers = {"Authorization": f"Bearer {token_factory(str(admin['_id']), 'admin')}"}

    response = await client.get("/api/users/not-an-object-id", headers=headers)

    assert response.status_code == 404
