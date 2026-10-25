"""Patient files: role x category matrix, cross-patient access, type and size checks."""

import pytest

from app.core.config import settings
from app.modules.auth.models import Role

PDF = b"%PDF-1.4\n% fichier de test\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
async def patient_record(create_patient):
    return await create_patient()


@pytest.fixture
async def other_record(create_patient):
    return await create_patient(firstName="Karim", lastName="Jaziri", nationalId="07654321")


@pytest.fixture
async def patient_user(user_factory, patient_record):
    return await user_factory(
        email="leila@example.test", role=Role.PATIENT, patient_id=patient_record["id"]
    )


@pytest.fixture
def upload(api_client, auth):
    async def send(user, patient_id, *, category="MEDICAL", data=PDF, name="bilan.pdf", **form):
        fields = {"category": category, "type": "LAB_RESULT", "title": "Bilan sanguin"} | form
        return await api_client.post(
            f"/api/patients/{patient_id}/files",
            headers=auth(user),
            data=fields,
            files={"file": (name, data, "application/octet-stream")},
        )

    return send


@pytest.fixture
def uploaded(upload, secretary):
    async def create(patient_id, category="MEDICAL", **form):
        response = await upload(secretary, patient_id, category=category, **form)
        assert response.status_code == 201, response.text
        return response.json()

    return create


async def test_upload_stores_the_file_and_hides_the_path(
    upload, secretary, patient_record, files_dir, db
):
    response = await upload(secretary, patient_record["id"], name="../../etc/passwd.pdf")

    body = response.json()
    assert response.status_code == 201
    assert body["category"] == "MEDICAL" and body["type"] == "LAB_RESULT"
    assert body["mime"] == "application/pdf" and body["size"] == len(PDF)
    assert body["uploadedByName"] == "Test User"
    assert "storagePath" not in body and "extractedText" not in body
    stored = await db.patient_files.find_one()
    assert stored["storagePath"].startswith(f"{patient_record['id']}/")
    assert ".." not in stored["storagePath"]
    assert (files_dir / stored["storagePath"]).read_bytes() == PDF


@pytest.mark.parametrize(
    ("role", "category", "expected"),
    [
        (Role.SECRETARY, "ADMINISTRATIVE", 201),
        (Role.SECRETARY, "MEDICAL", 201),
        (Role.ADMIN, "ADMINISTRATIVE", 201),
        (Role.ADMIN, "MEDICAL", 201),
        (Role.DOCTOR, "MEDICAL", 403),
        (Role.DOCTOR, "ADMINISTRATIVE", 403),
        (Role.ADMIN_STAFF, "MEDICAL", 403),
    ],
)
async def test_upload_roles(upload, user_factory, patient_record, role, category, expected):
    user = await user_factory(email=f"{role.value.lower()}@x.test", role=role)

    response = await upload(user, patient_record["id"], category=category)

    assert response.status_code == expected


async def test_patient_cannot_upload(upload, patient_user, patient_record):
    response = await upload(patient_user, patient_record["id"])
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("role", "visible"),
    [
        (Role.SECRETARY, {"ADMINISTRATIVE", "MEDICAL"}),
        (Role.ADMIN, {"ADMINISTRATIVE", "MEDICAL"}),
        (Role.DOCTOR, {"MEDICAL"}),
    ],
)
async def test_list_and_download_by_role_and_category(
    api_client, auth, user_factory, uploaded, patient_record, role, visible
):
    admin_file = await uploaded(patient_record["id"], "ADMINISTRATIVE", type="INSURANCE")
    medical_file = await uploaded(patient_record["id"], "MEDICAL")
    user = await user_factory(email=f"{role.value.lower()}@x.test", role=role)
    base = f"/api/patients/{patient_record['id']}/files"

    listing = await api_client.get(base, headers=auth(user))
    downloads = {
        f["category"]: await api_client.get(f"{base}/{f['id']}/download", headers=auth(user))
        for f in (admin_file, medical_file)
    }

    assert {f["category"] for f in listing.json()} == visible
    for category, response in downloads.items():
        assert response.status_code == (200 if category in visible else 403), category


async def test_doctor_filtering_on_administrative_is_403(
    api_client, auth, doctor, uploaded, patient_record
):
    await uploaded(patient_record["id"], "ADMINISTRATIVE", type="INVOICE")
    response = await api_client.get(
        f"/api/patients/{patient_record['id']}/files",
        headers=auth(doctor),
        params={"category": "ADMINISTRATIVE"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "file_category_forbidden"


async def test_category_filter(api_client, auth, secretary, uploaded, patient_record):
    await uploaded(patient_record["id"], "ADMINISTRATIVE", type="INSURANCE")
    await uploaded(patient_record["id"], "MEDICAL")
    response = await api_client.get(
        f"/api/patients/{patient_record['id']}/files",
        headers=auth(secretary),
        params={"category": "MEDICAL"},
    )
    assert [f["category"] for f in response.json()] == ["MEDICAL"]


async def test_patient_reads_only_their_own_record(
    api_client, auth, patient_user, uploaded, patient_record, other_record
):
    own = await uploaded(patient_record["id"], "ADMINISTRATIVE", type="INSURANCE")
    foreign = await uploaded(other_record["id"], "MEDICAL")
    own_base = f"/api/patients/{patient_record['id']}/files"
    other_base = f"/api/patients/{other_record['id']}/files"
    headers = auth(patient_user)

    listing = await api_client.get(own_base, headers=headers)
    download = await api_client.get(f"{own_base}/{own['id']}/download", headers=headers)
    other_list = await api_client.get(other_base, headers=headers)
    other_download = await api_client.get(f"{other_base}/{foreign['id']}/download", headers=headers)
    # Another patient's file id behind your own record id: not found.
    smuggled = await api_client.get(f"{own_base}/{foreign['id']}/download", headers=headers)

    assert [f["id"] for f in listing.json()] == [own["id"]]
    assert download.status_code == 200 and download.content == PDF
    assert other_list.status_code == 403 and other_download.status_code == 403
    assert smuggled.status_code == 404


async def test_download_headers(api_client, auth, secretary, uploaded, patient_record):
    file = await uploaded(
        patient_record["id"], title="Échographie cardiaque", data=PNG, name="x.png"
    )

    response = await api_client.get(
        f"/api/patients/{patient_record['id']}/files/{file['id']}/download", headers=auth(secretary)
    )

    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    assert 'filename="echographie-cardiaque.png"' in response.headers["content-disposition"]
    assert response.content == PNG


@pytest.mark.parametrize(
    ("data", "name"),
    [
        (b"MZ\x90\x00 fake exe", "rapport.pdf"),
        (b"<html><script>", "scan.png"),
        (b"GIF89a", "a.gif"),
    ],
)
async def test_type_is_checked_on_the_content(upload, secretary, patient_record, data, name):
    response = await upload(secretary, patient_record["id"], data=data, name=name)
    assert response.status_code == 415
    assert response.json()["code"] == "file_type_not_allowed"


async def test_size_limit_and_empty_file(upload, secretary, patient_record, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    too_large = await upload(secretary, patient_record["id"], data=PDF + b"0" * (1024 * 1024))
    empty = await upload(secretary, patient_record["id"], data=b"")

    assert too_large.status_code == 413
    assert empty.status_code == 422


async def test_invalid_form_values_are_422(upload, secretary, patient_record):
    bad_category = await upload(secretary, patient_record["id"], category="BILLING")
    no_title = await upload(secretary, patient_record["id"], title="")
    assert bad_category.status_code == 422 and no_title.status_code == 422


async def test_soft_delete(api_client, auth, secretary, doctor, uploaded, patient_record, db):
    file = await uploaded(patient_record["id"])
    base = f"/api/patients/{patient_record['id']}/files"

    by_doctor = await api_client.delete(f"{base}/{file['id']}", headers=auth(doctor))
    deleted = await api_client.delete(f"{base}/{file['id']}", headers=auth(secretary))
    listing = await api_client.get(base, headers=auth(secretary))
    download = await api_client.get(f"{base}/{file['id']}/download", headers=auth(secretary))

    assert by_doctor.status_code == 403
    assert deleted.status_code == 204
    assert listing.json() == [] and download.status_code == 404
    assert (await db.patient_files.find_one())["deletedAt"] is not None  # kept for audit


async def test_deleted_patient_and_unknown_ids(
    api_client, auth, secretary, admin, uploaded, patient_record
):
    file = await uploaded(patient_record["id"])
    base = f"/api/patients/{patient_record['id']}/files"
    unknown_file = await api_client.get(
        f"{base}/000000000000000000000000/download", headers=auth(admin)
    )
    bad_id = await api_client.get("/api/patients/not-an-id/files", headers=auth(admin))
    await api_client.delete(f"/api/patients/{patient_record['id']}", headers=auth(secretary))

    listing = await api_client.get(base, headers=auth(admin))
    download = await api_client.get(f"{base}/{file['id']}/download", headers=auth(admin))

    assert unknown_file.status_code == 404 and bad_id.status_code == 404
    assert listing.status_code == 404 and download.status_code == 404


async def test_no_token_is_401(api_client, patient_record):
    response = await api_client.get(f"/api/patients/{patient_record['id']}/files")
    assert response.status_code == 401
