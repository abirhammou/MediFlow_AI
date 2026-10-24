import re
from datetime import UTC, datetime, timedelta

import pytest
from beanie import PydanticObjectId

from app.modules.auth.models import Role
from app.modules.patients.dates import clinic_today


def field_errors(response) -> dict[tuple, str]:
    """422 body -> {loc without "body": French message}."""
    assert response.status_code == 422, response.text
    return {tuple(error["loc"][1:]): error["msg"] for error in response.json()["detail"]}


# --- create -----------------------------------------------------------


async def test_create_patient(api_client, db, secretary, auth, payload):
    response = await api_client.post("/api/patients", headers=auth(secretary), json=payload())

    assert response.status_code == 201
    body = response.json()
    assert re.fullmatch(rf"PAT-{datetime.now(UTC).year}-\d{{5}}", body["recordNumber"])
    assert body["createdBy"] == body["updatedBy"] == str(secretary.id)
    assert body["dateOfBirth"] == "1990-01-01"
    assert body["currentSummaryId"] is None
    assert body["address"] == {
        "street": "12 rue de Marseille",
        "city": "Tunis",
        "postalCode": "1000",
    }
    assert body["age"] >= 35
    raw = await db.patients.find_one({"_id": PydanticObjectId(body["id"])})
    assert raw["dateOfBirth"] == datetime(1990, 1, 1, tzinfo=UTC)
    assert raw["createdBy"] == secretary.id
    assert raw["deletedAt"] is None


async def test_create_cleans_input(create_patient):
    body = await create_patient(
        firstName="  Amira ",
        email=" Amira.Gharbi@Example.TEST ",
        phone="",
        nationalId=None,
        address={"street": "", "city": " ", "postalCode": None},
        insurance={},
        emergencyContact=...,
    )

    assert body["firstName"] == "Amira"
    assert body["email"] == "amira.gharbi@example.test"
    assert body["phone"] is None
    assert body["nationalId"] is None
    assert body["address"] is None
    assert body["insurance"] is None
    assert body["emergencyContact"] is None


async def test_create_validation_messages(api_client, secretary, auth, payload):
    tomorrow = (clinic_today() + timedelta(days=1)).isoformat()
    response = await api_client.post(
        "/api/patients",
        headers=auth(secretary),
        json=payload(
            dateOfBirth=tomorrow,
            nationalId="1234",
            email="pas-un-email",
            firstName=" ",
            lastName="x" * 81,
            gender="UNKNOWN",
            bloodType="C+",
            phone="12-34",
            emergencyContact={"phone": "abc"},
            administrativeNotes="n" * 5001,
        ),
    )

    errors = field_errors(response)
    assert errors[("dateOfBirth",)] == "La date de naissance ne peut pas être dans le futur."
    assert errors[("nationalId",)] == "Le CIN doit contenir exactement 8 chiffres."
    assert errors[("email",)] == "Adresse email invalide."
    assert errors[("firstName",)] == "Ce champ est obligatoire."
    assert errors[("lastName",)] == "80 caractères maximum."
    assert errors[("gender",)] == "Valeur non autorisée."
    assert errors[("bloodType",)] == "Valeur non autorisée."
    assert errors[("phone",)].startswith("Téléphone invalide")
    assert errors[("emergencyContact", "phone")].startswith("Téléphone invalide")
    assert errors[("administrativeNotes",)] == "5000 caractères maximum."


async def test_create_rejects_too_old_and_missing_fields(api_client, secretary, auth, payload):
    too_old = await api_client.post(
        "/api/patients", headers=auth(secretary), json=payload(dateOfBirth="1880-05-01")
    )
    missing = await api_client.post(
        "/api/patients",
        headers=auth(secretary),
        json=payload(lastName=..., dateOfBirth=..., gender=...),
    )

    assert "130 ans" in field_errors(too_old)[("dateOfBirth",)]
    assert field_errors(missing) == {
        ("lastName",): "Ce champ est obligatoire.",
        ("dateOfBirth",): "Ce champ est obligatoire.",
        ("gender",): "Ce champ est obligatoire.",
    }


@pytest.mark.parametrize(
    "field", ["recordNumber", "createdBy", "createdAt", "deletedAt", "currentSummaryId"]
)
async def test_create_rejects_server_fields(api_client, secretary, auth, payload, field):
    response = await api_client.post(
        "/api/patients", headers=auth(secretary), json=payload(**{field: "x"})
    )

    assert field_errors(response) == {(field,): "Champ non autorisé."}


async def test_duplicate_national_id_is_409(api_client, create_patient, secretary, auth, payload):
    await create_patient(nationalId="11112222")

    response = await api_client.post(
        "/api/patients",
        headers=auth(secretary),
        json=payload(nationalId="11112222", firstName="Autre"),
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Un patient avec ce CIN existe déjà",
        "code": "national_id_exists",
    }


async def test_patients_without_national_id_are_allowed(create_patient):
    first = await create_patient(nationalId=None)
    second = await create_patient(nationalId=..., firstName="Omar")

    assert first["nationalId"] is second["nationalId"] is None
    assert first["recordNumber"] != second["recordNumber"]


# --- get --------------------------------------------------------------


@pytest.mark.parametrize("patient_id", [str(PydanticObjectId()), "not-an-id", "123"])
async def test_get_unknown_or_invalid_id_is_404(api_client, secretary, auth, patient_id):
    response = await api_client.get(f"/api/patients/{patient_id}", headers=auth(secretary))

    assert response.status_code == 404
    assert response.json()["detail"] == "Dossier patient introuvable."


async def test_get_patient(api_client, create_patient, doctor, auth):
    created = await create_patient()

    response = await api_client.get(f"/api/patients/{created['id']}", headers=auth(doctor))

    assert response.status_code == 200
    assert response.json() == created


# --- list -------------------------------------------------------------


@pytest.fixture
async def several_patients(create_patient):
    specs = [
        dict(firstName="Youssef", lastName="Ben Salah", gender="MALE", bloodType="O+",
             dateOfBirth="1975-11-02", nationalId="20000001", address={"city": "Sfax"}),
        dict(firstName="Amira", lastName="Benali", gender="FEMALE", bloodType="B+",
             dateOfBirth="1995-07-21", nationalId="20000002", address={"city": "Sousse"}),
        dict(firstName="Karim", lastName="Jaziri", gender="MALE", bloodType="O+",
             dateOfBirth="1962-01-30", nationalId="20000003", address={"city": "sfax"}),
        dict(firstName="Nour", lastName="Mansouri", gender="FEMALE", bloodType=None,
             dateOfBirth="2001-09-09", nationalId=None, address=None),
    ]  # fmt: skip
    return [await create_patient(**spec) for spec in specs]


async def list_patients(api_client, user, auth, query: str = "") -> dict:
    response = await api_client.get(f"/api/patients{query}", headers=auth(user))
    assert response.status_code == 200, response.text
    return response.json()


def last_names(page: dict) -> list[str]:
    return [item["lastName"] for item in page["items"]]


async def test_list_paginates_and_sorts_by_name(api_client, several_patients, doctor, auth):
    first = await list_patients(api_client, doctor, auth, "?size=3")
    second = await list_patients(api_client, doctor, auth, "?size=3&page=2")

    assert (first["total"], first["page"], first["size"]) == (4, 1, 3)
    assert last_names(first) == ["Ben Salah", "Benali", "Jaziri"]
    assert last_names(second) == ["Mansouri"]
    assert set(first["items"][0]) == {
        "id", "recordNumber", "firstName", "lastName", "dateOfBirth", "age", "gender", "phone", "city",
    }  # fmt: skip
    assert first["items"][0]["city"] == "Sfax"
    assert second["items"][0]["city"] is None


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("-lastName", ["Mansouri", "Jaziri", "Benali", "Ben Salah"]),
        ("dateOfBirth", ["Jaziri", "Ben Salah", "Benali", "Mansouri"]),
        ("-createdAt", ["Mansouri", "Jaziri", "Benali", "Ben Salah"]),
        ("recordNumber", ["Ben Salah", "Benali", "Jaziri", "Mansouri"]),
    ],
)
async def test_list_sort(api_client, several_patients, doctor, auth, sort, expected):
    assert last_names(await list_patients(api_client, doctor, auth, f"?sort={sort}")) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("?q=ben", ["Ben Salah", "Benali"]),
        ("?q=BEN%20S", ["Ben Salah"]),
        ("?q=amira%20ben", ["Benali"]),
        ("?q=kar", ["Jaziri"]),
        ("?q=2000000", ["Ben Salah", "Benali", "Jaziri"]),
        ("?q=salah", []),
        ("?q=.*", []),
        ("?gender=FEMALE", ["Benali", "Mansouri"]),
        ("?bloodType=O%2B", ["Ben Salah", "Jaziri"]),
        ("?city=SFAX", ["Ben Salah", "Jaziri"]),
        ("?gender=MALE&city=sfax&q=jaz", ["Jaziri"]),
    ],
)
async def test_list_search_and_filters(api_client, several_patients, doctor, auth, query, expected):
    assert last_names(await list_patients(api_client, doctor, auth, query)) == expected


async def test_search_by_record_number(api_client, several_patients, doctor, auth):
    record_number = several_patients[2]["recordNumber"]

    exact = await list_patients(api_client, doctor, auth, f"?q={record_number.lower()}")

    assert last_names(exact) == ["Jaziri"]


@pytest.mark.parametrize(
    "query", ["?size=101", "?size=0", "?page=0", "?sort=email", "?sort=--lastName"]
)
async def test_list_rejects_bad_paging_and_sort(api_client, doctor, auth, query):
    response = await api_client.get(f"/api/patients{query}", headers=auth(doctor))

    assert response.status_code == 422


# --- update -----------------------------------------------------------


async def test_patch_updates_only_sent_fields(api_client, create_patient, secretary, admin, auth):
    created = await create_patient()

    response = await api_client.patch(
        f"/api/patients/{created['id']}",
        headers=auth(admin),
        json={"phone": "71 000 000", "address": {"city": "Ariana"}, "email": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["phone"] == "71 000 000"
    assert body["address"] == {"street": None, "city": "Ariana", "postalCode": None}
    assert body["email"] is None
    assert body["updatedBy"] == str(admin.id)
    assert body["createdBy"] == str(secretary.id)
    assert body["updatedAt"] >= created["updatedAt"]
    unchanged = {"phone", "address", "email", "updatedBy", "updatedAt"}
    assert {k: v for k, v in body.items() if k not in unchanged} == {
        k: v for k, v in created.items() if k not in unchanged
    }


async def test_patch_dates_enums_and_cleared_objects(api_client, create_patient, secretary, auth):
    created = await create_patient()

    response = await api_client.patch(
        f"/api/patients/{created['id']}",
        headers=auth(secretary),
        json={"dateOfBirth": "1991-02-28", "gender": "OTHER", "bloodType": None, "insurance": {}},
    )

    body = response.json()
    assert response.status_code == 200
    assert (body["dateOfBirth"], body["gender"], body["bloodType"]) == ("1991-02-28", "OTHER", None)
    assert body["insurance"] is None


async def test_patch_rejects_record_number_and_null_required(
    api_client, create_patient, secretary, auth
):
    created = await create_patient()
    url = f"/api/patients/{created['id']}"

    record = await api_client.patch(
        url, headers=auth(secretary), json={"recordNumber": "PAT-2020-00001"}
    )
    nulls = await api_client.patch(
        url, headers=auth(secretary), json={"lastName": None, "gender": None}
    )

    assert field_errors(record) == {("recordNumber",): "Champ non autorisé."}
    assert field_errors(nulls) == {
        ("lastName",): "Ce champ est obligatoire.",
        ("gender",): "Ce champ est obligatoire.",
    }
    current = await api_client.get(url, headers=auth(secretary))
    assert current.json()["recordNumber"] == created["recordNumber"]


async def test_patch_duplicate_national_id_is_409(api_client, create_patient, secretary, auth):
    await create_patient(nationalId="33334444")
    other = await create_patient(nationalId="55556666", firstName="Omar")

    response = await api_client.patch(
        f"/api/patients/{other['id']}", headers=auth(secretary), json={"nationalId": "33334444"}
    )

    assert response.status_code == 409


async def test_patch_unknown_patient_is_404(api_client, secretary, auth):
    response = await api_client.patch(
        f"/api/patients/{PydanticObjectId()}", headers=auth(secretary), json={"phone": None}
    )

    assert response.status_code == 404


# --- soft delete / restore -------------------------------------------


async def test_soft_delete_and_restore(api_client, db, create_patient, secretary, admin, auth):
    kept = await create_patient(nationalId="70000001", lastName="Zouari")
    deleted = await create_patient(nationalId="70000002")
    url = f"/api/patients/{deleted['id']}"

    response = await api_client.delete(url, headers=auth(secretary))

    assert response.status_code == 204
    raw = await db.patients.find_one({"_id": PydanticObjectId(deleted["id"])})
    assert raw is not None and raw["deletedAt"] is not None
    assert (await api_client.get(url, headers=auth(secretary))).status_code == 404
    assert (
        await api_client.patch(url, headers=auth(secretary), json={"phone": None})
    ).status_code == 404
    assert (await api_client.delete(url, headers=auth(secretary))).status_code == 404
    listed = await list_patients(api_client, secretary, auth)
    assert [item["id"] for item in listed["items"]] == [kept["id"]]

    trash = await api_client.get("/api/patients/deleted", headers=auth(admin))
    assert trash.status_code == 200
    assert trash.json()["total"] == 1
    assert trash.json()["items"][0]["id"] == deleted["id"]
    assert trash.json()["items"][0]["deletedAt"]

    restored = await api_client.post(f"{url}/restore", headers=auth(admin))
    assert restored.status_code == 200
    assert restored.json()["updatedBy"] == str(admin.id)
    assert (await api_client.get(url, headers=auth(secretary))).status_code == 200
    assert (await api_client.get("/api/patients/deleted", headers=auth(admin))).json()["total"] == 0
    again = await api_client.post(f"{url}/restore", headers=auth(admin))
    assert again.status_code == 404


# --- duplicates -------------------------------------------------------


async def test_find_duplicates(api_client, create_patient, secretary, auth):
    same = await create_patient(nationalId="80000001")
    await create_patient(nationalId="80000002", dateOfBirth="1990-01-02")
    gone = await create_patient(nationalId="80000003")
    await api_client.delete(f"/api/patients/{gone['id']}", headers=auth(secretary))

    response = await api_client.get(
        "/api/patients/duplicates?firstName=%20leila%20&lastName=HADDAD&dateOfBirth=1990-01-01",
        headers=auth(secretary),
    )
    partial_name = await api_client.get(
        "/api/patients/duplicates?firstName=Lei&lastName=Haddad&dateOfBirth=1990-01-01",
        headers=auth(secretary),
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [same["id"]]
    assert partial_name.json() == []


# --- roles ------------------------------------------------------------


async def test_doctor_can_read_but_not_write(api_client, create_patient, doctor, auth, payload):
    created = await create_patient()
    url = f"/api/patients/{created['id']}"

    assert (await api_client.get("/api/patients", headers=auth(doctor))).status_code == 200
    assert (await api_client.get(url, headers=auth(doctor))).status_code == 200
    forbidden = [
        await api_client.post("/api/patients", headers=auth(doctor), json=payload(nationalId=None)),
        await api_client.patch(url, headers=auth(doctor), json={"phone": None}),
        await api_client.delete(url, headers=auth(doctor)),
        await api_client.get(
            "/api/patients/duplicates?firstName=a&lastName=b&dateOfBirth=1990-01-01",
            headers=auth(doctor),
        ),
    ]
    assert [response.status_code for response in forbidden] == [403] * 4


async def test_restore_and_trash_are_admin_only(
    api_client, create_patient, secretary, doctor, auth
):
    created = await create_patient()
    await api_client.delete(f"/api/patients/{created['id']}", headers=auth(secretary))

    for user in (secretary, doctor):
        restore = await api_client.post(
            f"/api/patients/{created['id']}/restore", headers=auth(user)
        )
        trash = await api_client.get("/api/patients/deleted", headers=auth(user))
        assert (restore.status_code, trash.status_code) == (403, 403)


@pytest.mark.parametrize("role", [Role.ADMIN_STAFF, Role.PATIENT])
async def test_other_roles_cannot_read(api_client, user_factory, auth, role):
    user = await user_factory(email=f"{role.value.lower()}@example.test", role=role)

    assert (await api_client.get("/api/patients", headers=auth(user))).status_code == 403


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/patients"),
        ("POST", "/api/patients"),
        ("GET", f"/api/patients/{PydanticObjectId()}"),
        ("PATCH", f"/api/patients/{PydanticObjectId()}"),
        ("DELETE", f"/api/patients/{PydanticObjectId()}"),
        ("GET", "/api/patients/deleted"),
        ("POST", f"/api/patients/{PydanticObjectId()}/restore"),
    ],
)
async def test_no_token_is_401(api_client, method, path):
    response = await api_client.request(
        method, path, json={} if method in {"POST", "PATCH"} else None
    )

    assert response.status_code == 401
