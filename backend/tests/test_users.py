from datetime import date

import pytest
from beanie import PydanticObjectId

from app.core.sequence import next_record_number
from app.errors import APIError
from app.modules.auth.models import Role, User
from app.modules.patients.models import Gender, Patient
from app.modules.users.service import UsersService


@pytest.fixture
def auth(token_factory):
    def headers(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_factory(user)}"}

    return headers


@pytest.fixture
async def admin(user_factory) -> User:
    return await user_factory(email="admin@example.test", role=Role.ADMIN)


@pytest.mark.parametrize("role", [Role.DOCTOR, Role.SECRETARY, Role.ADMIN_STAFF, Role.PATIENT])
async def test_user_management_is_admin_only(api_client, user_factory, auth, role):
    user = await user_factory(email=f"{role.value.lower()}@example.test", role=role)

    response = await api_client.get("/api/users", headers=auth(user))
    unauthenticated = await api_client.get("/api/users")

    assert response.status_code == 403
    assert unauthenticated.status_code == 401


async def test_inactive_admin_cannot_use_users_routes(api_client, user_factory, auth):
    user = await user_factory(email="inactive-admin@example.test", role=Role.ADMIN, is_active=False)

    response = await api_client.get("/api/users", headers=auth(user))

    assert response.status_code == 403
    assert response.json()["detail"] == "Le compte n'est pas actif."


async def test_list_users_filters_and_paginates(api_client, user_factory, admin, auth):
    for email in ("doctor-one@example.test", "doctor-two@example.test"):
        await user_factory(email=email, role=Role.DOCTOR, is_active=False)
    await user_factory(email="secretary@example.test", role=Role.SECRETARY, is_active=False)

    query = "/api/users?is_active=false&role=DOCTOR&size=1"
    first_page = await api_client.get(f"{query}&page=1", headers=auth(admin))
    second_page = await api_client.get(f"{query}&page=2", headers=auth(admin))

    assert first_page.status_code == second_page.status_code == 200
    assert first_page.json()["total"] == 2
    assert first_page.json()["size"] == 1
    items = first_page.json()["items"] + second_page.json()["items"]
    assert len({item["id"] for item in items}) == 2
    assert all("password_hash" not in item for item in items)


async def test_admin_can_create_active_user_without_exposing_password_hash(
    api_client, admin, auth
):
    response = await api_client.post(
        "/api/users",
        headers=auth(admin),
        json={
            "email": "New.User@Example.test",
            "password": "long-enough-password",
            "first_name": "New",
            "last_name": "User",
            "role": "DOCTOR",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "new.user@example.test"
    assert response.json()["is_active"] is True
    assert "password_hash" not in response.json()
    stored = await User.find_one(User.email == "new.user@example.test")
    assert stored.password_hash != "long-enough-password"


async def test_admin_can_read_change_role_disable_enable_and_delete_user(
    api_client, user_factory, admin, auth
):
    target = await user_factory(email="target@example.test", role=Role.SECRETARY)
    base = f"/api/users/{target.id}"

    read = await api_client.get(base, headers=auth(admin))
    role = await api_client.patch(f"{base}/role", headers=auth(admin), json={"role": "DOCTOR"})
    disabled = await api_client.patch(f"{base}/disable", headers=auth(admin))
    enabled = await api_client.patch(f"{base}/enable", headers=auth(admin))
    deleted = await api_client.delete(base, headers=auth(admin))

    assert read.status_code == 200 and read.json()["email"] == "target@example.test"
    assert role.status_code == 200 and role.json()["role"] == "DOCTOR"
    assert disabled.status_code == 200 and disabled.json()["is_active"] is False
    assert enabled.status_code == 200 and enabled.json()["is_active"] is True
    assert deleted.status_code == 200 and deleted.json()["is_active"] is False
    assert await User.get(target.id) is not None


async def test_admin_can_approve_pending_user_then_user_can_login(
    api_client, user_factory, admin, auth
):
    pending = await user_factory(
        email="pending@example.test", password="pending-password", role=Role.DOCTOR, is_active=False
    )
    credentials = {"username": "pending@example.test", "password": "pending-password"}

    before = await api_client.post("/api/auth/login", data=credentials)
    approved = await api_client.patch(f"/api/users/{pending.id}/approve", headers=auth(admin))
    again = await api_client.patch(f"/api/users/{pending.id}/approve", headers=auth(admin))
    after = await api_client.post("/api/auth/login", data=credentials)

    assert before.status_code == 403
    assert approved.status_code == 200 and approved.json()["is_active"] is True
    assert again.status_code == 400 and again.json()["code"] == "already_active"
    assert after.status_code == 200


async def test_admin_cannot_deactivate_self_or_remove_own_admin_role(api_client, admin, auth):
    disable = await api_client.patch(f"/api/users/{admin.id}/disable", headers=auth(admin))
    demote = await api_client.patch(
        f"/api/users/{admin.id}/role", headers=auth(admin), json={"role": "DOCTOR"}
    )

    assert disable.status_code == 400 and disable.json()["code"] == "self_deactivation"
    assert demote.status_code == 400 and demote.json()["code"] == "self_admin_role"


async def test_service_protects_last_active_admin(user_factory):
    only_admin = await user_factory(email="only-admin@example.test", role=Role.ADMIN)
    other = await user_factory(email="other@example.test", role=Role.SECRETARY)

    with pytest.raises(APIError) as exc_info:
        await UsersService().disable(str(only_admin.id), other)

    assert exc_info.value.code == "last_admin"


async def test_admin_and_secretary_can_link_and_unlink_patient(
    api_client, user_factory, admin, auth
):
    secretary = await user_factory(email="secretary@example.test", role=Role.SECRETARY)
    account = await user_factory(email="patient@example.test", role=Role.PATIENT)
    patient = await Patient(
        record_number=await next_record_number(),
        first_name="Leila",
        last_name="Haddad",
        date_of_birth=date(1990, 5, 1),
        gender=Gender.FEMALE,
    ).insert()

    linked = await api_client.patch(
        f"/api/users/{account.id}/link-patient",
        headers=auth(secretary),
        json={"patient_id": str(patient.id)},
    )
    unlinked = await api_client.patch(f"/api/users/{account.id}/unlink-patient", headers=auth(admin))
    missing = await api_client.patch(
        f"/api/users/{account.id}/link-patient",
        headers=auth(admin),
        json={"patient_id": str(PydanticObjectId())},
    )

    assert linked.status_code == 200 and linked.json()["patient_id"] == str(patient.id)
    assert unlinked.status_code == 200 and unlinked.json()["patient_id"] is None
    assert missing.status_code == 404


async def test_only_patient_accounts_can_be_linked(api_client, user_factory, admin, auth):
    doctor = await user_factory(email="doctor@example.test", role=Role.DOCTOR)

    response = await api_client.patch(
        f"/api/users/{doctor.id}/link-patient",
        headers=auth(admin),
        json={"patient_id": str(PydanticObjectId())},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "not_a_patient"


async def test_only_admin_and_secretary_can_link_patient(api_client, user_factory, auth):
    doctor = await user_factory(email="doctor@example.test", role=Role.DOCTOR)
    account = await user_factory(email="patient@example.test", role=Role.PATIENT)

    response = await api_client.patch(
        f"/api/users/{account.id}/link-patient",
        headers=auth(doctor),
        json={"patient_id": str(PydanticObjectId())},
    )

    assert response.status_code == 403


async def test_invalid_user_id_returns_not_found(api_client, admin, auth):
    invalid = await api_client.get("/api/users/not-an-id", headers=auth(admin))
    unknown = await api_client.get(f"/api/users/{PydanticObjectId()}", headers=auth(admin))

    assert invalid.status_code == unknown.status_code == 404
