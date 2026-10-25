from datetime import timedelta
from types import SimpleNamespace

import pytest
from beanie import PydanticObjectId

from app.core.models import AiReviewStatus
from app.core.time import utcnow
from app.errors import APIError
from app.modules.auth.models import Role, User
from app.modules.documents.models import ExtractedField, MedicalDocument
from app.modules.documents.schemas import (
    DocumentExtraction,
    DocumentReview,
    ExtractedFieldProposal,
    ReviewedField,
)
from app.modules.documents.service import DocumentService, document_status


def test_document_status_is_derived_from_all_fields():
    assert document_status([]) == AiReviewStatus.DRAFT
    assert document_status([ExtractedField(name="date", status=AiReviewStatus.DRAFT)]) == AiReviewStatus.DRAFT
    assert (
        document_status(
            [
                ExtractedField(name="date", status=AiReviewStatus.VALIDATED),
                ExtractedField(name="value", status=AiReviewStatus.VALIDATED),
            ]
        )
        == AiReviewStatus.VALIDATED
    )
    assert (
        document_status(
            [
                ExtractedField(name="date", status=AiReviewStatus.VALIDATED),
                ExtractedField(name="value", status=AiReviewStatus.REJECTED),
            ]
        )
        == AiReviewStatus.REJECTED
    )


@pytest.fixture
def auth(token_factory):
    def headers(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_factory(user)}"}

    return headers


@pytest.fixture
async def doctor(user_factory) -> User:
    return await user_factory(email="meddoc.doctor@example.test", role=Role.DOCTOR)


@pytest.fixture
async def secretary(user_factory) -> User:
    return await user_factory(email="meddoc.secretary@example.test", role=Role.SECRETARY)


@pytest.fixture
async def admin_staff(user_factory) -> User:
    return await user_factory(email="meddoc.staff@example.test", role=Role.ADMIN_STAFF)


@pytest.fixture
async def admin(user_factory) -> User:
    return await user_factory(email="meddoc.admin@example.test", role=Role.ADMIN)


@pytest.fixture
async def patient(user_factory) -> User:
    return await user_factory(
        email="meddoc.patient@example.test",
        role=Role.PATIENT,
        patient_id=PydanticObjectId(),
    )


@pytest.fixture
def create_document(api_client, auth):
    async def create(user: User, **overrides) -> dict:
        payload = {
            "patient_id": str(PydanticObjectId()),
            "title": "Résultat de laboratoire",
            "raw_text": "Hémoglobine : 13 g/dL.",
        } | overrides
        response = await api_client.post(
            "/api/documents", headers=auth(user), json=payload
        )
        assert response.status_code == 201, response.text
        return response.json()

    return create


async def _set_fields(document_id: str, fields: list[ExtractedField]) -> None:
    document = await MedicalDocument.get(PydanticObjectId(document_id))
    assert document is not None
    document.extracted_fields = fields
    await document.save()


async def test_document_routes_require_authentication(api_client):
    assert (await api_client.get("/api/documents/")).status_code == 401
    assert (await api_client.post("/api/documents", json={})).status_code == 401


@pytest.mark.parametrize("role", [Role.DOCTOR, Role.SECRETARY, Role.ADMIN_STAFF, Role.ADMIN])
async def test_staff_roles_can_create_documents(api_client, user_factory, auth, role):
    user = await user_factory(email=f"meddoc-create-{role.value.lower()}@example.test", role=role)
    response = await api_client.post(
        "/api/documents",
        headers=auth(user),
        json={
            "patient_id": str(PydanticObjectId()),
            "title": "Ordonnance",
            "raw_text": "Prendre le traitement selon la prescription.",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "DRAFT"
    assert response.json()["uploaded_by"] == str(user.id)
    assert response.json()["extracted_fields"] == []


async def test_patient_cannot_create_or_modify_documents(api_client, patient, auth):
    payload = {
        "patient_id": str(PydanticObjectId()),
        "title": "Document",
        "raw_text": "Texte médical.",
    }
    create = await api_client.post("/api/documents", headers=auth(patient), json=payload)
    update = await api_client.patch(
        f"/api/documents/{PydanticObjectId()}",
        headers=auth(patient),
        json={"title": "Autre titre"},
    )

    assert create.status_code == 403
    assert update.status_code == 403


async def test_staff_list_filters_by_patient_and_sorts_by_creation_date(
    api_client, doctor, auth, create_document
):
    patient_id = str(PydanticObjectId())
    older = await create_document(doctor, patient_id=patient_id, title="Ancien")
    newer = await create_document(doctor, patient_id=patient_id, title="Récent")
    other = await create_document(doctor, title="Autre patient")
    older_model = await MedicalDocument.get(PydanticObjectId(older["id"]))
    newer_model = await MedicalDocument.get(PydanticObjectId(newer["id"]))
    assert older_model is not None and newer_model is not None
    older_model.created_at = utcnow() - timedelta(days=1)
    newer_model.created_at = utcnow()
    await older_model.save()
    await newer_model.save()

    response = await api_client.get(
        f"/api/documents/?patient_id={patient_id}", headers=auth(doctor)
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert [item["id"] for item in response.json()["items"]] == [newer["id"], older["id"]]
    assert other["id"] not in [item["id"] for item in response.json()["items"]]
    assert "raw_text" not in response.json()["items"][0]


async def test_patient_list_is_server_filtered_to_own_validated_documents(
    api_client, patient, doctor, auth, create_document
):
    own = await create_document(doctor, patient_id=str(patient.patient_id))
    await _set_fields(
        own["id"],
        [ExtractedField(name="hemoglobin", value="13 g/dL", status=AiReviewStatus.VALIDATED)],
    )
    draft = await create_document(doctor, patient_id=str(patient.patient_id))
    await _set_fields(
        draft["id"],
        [ExtractedField(name="hemoglobin", value="13 g/dL", status=AiReviewStatus.DRAFT)],
    )
    foreign = await create_document(doctor)
    await _set_fields(
        foreign["id"],
        [ExtractedField(name="hemoglobin", value="14 g/dL", status=AiReviewStatus.VALIDATED)],
    )

    response = await api_client.get(
        f"/api/documents/?patient_id={foreign['patient_id']}", headers=auth(patient)
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [own["id"]]
    assert response.json()["items"][0]["status"] == "VALIDATED"


async def test_patient_without_linked_record_sees_empty_list(api_client, user_factory, auth):
    patient_without_record = await user_factory(
        email="meddoc.unlinked@example.test", role=Role.PATIENT
    )

    response = await api_client.get("/api/documents/", headers=auth(patient_without_record))

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


async def test_patient_cannot_read_another_patients_document(
    api_client, patient, doctor, auth, create_document
):
    document = await create_document(doctor)
    await _set_fields(
        document["id"],
        [ExtractedField(name="result", value="normal", status=AiReviewStatus.VALIDATED)],
    )

    response = await api_client.get(
        f"/api/documents/{document['id']}", headers=auth(patient)
    )

    assert response.status_code == 404
    assert response.json()["code"] == "document_not_found"


async def test_updating_source_text_clears_extracted_data_and_category(
    api_client, doctor, auth, create_document
):
    document = await create_document(doctor)
    await _set_fields(
        document["id"],
        [ExtractedField(name="result", value="normal", status=AiReviewStatus.DRAFT)],
    )
    stored = await MedicalDocument.get(PydanticObjectId(document["id"]))
    assert stored is not None
    stored.category_code = "LAB_RESULT"
    stored.ai_suggested_category_code = "LAB_RESULT"
    await stored.save()

    response = await api_client.patch(
        f"/api/documents/{document['id']}",
        headers=auth(doctor),
        json={"raw_text": "Texte corrigé."},
    )

    assert response.status_code == 200
    assert response.json()["raw_text"] == "Texte corrigé."
    assert response.json()["extracted_fields"] == []
    assert response.json()["category_code"] is None
    assert response.json()["ai_suggested_category_code"] is None


async def test_only_admin_can_delete_documents(
    api_client, doctor, admin, auth, create_document
):
    forbidden_doc = await create_document(doctor)
    forbidden = await api_client.delete(
        f"/api/documents/{forbidden_doc['id']}", headers=auth(doctor)
    )
    assert forbidden.status_code == 403

    deletable_doc = await create_document(doctor)
    deleted = await api_client.delete(
        f"/api/documents/{deletable_doc['id']}", headers=auth(admin)
    )
    missing = await api_client.get(
        f"/api/documents/{deletable_doc['id']}", headers=auth(admin)
    )

    assert deleted.status_code == 204
    assert missing.status_code == 404


class FakeDocumentRepository:
    def __init__(self, document, categories: list[SimpleNamespace]) -> None:
        self.document = document
        self.categories = categories
        self.save_count = 0

    async def get(self, document_id: PydanticObjectId):
        return self.document if document_id == self.document.id else None

    async def list_categories(self) -> list[SimpleNamespace]:
        return self.categories

    async def save(self, document):
        self.save_count += 1
        return document


def _service_user(role: Role = Role.DOCTOR) -> SimpleNamespace:
    return SimpleNamespace(
        id=PydanticObjectId(),
        role=role,
    )


def _service_document() -> SimpleNamespace:
    return SimpleNamespace(
        id=PydanticObjectId(),
        patient_id=PydanticObjectId(),
        title="Confidentiel titre patient",
        raw_text="Hémoglobine : 13 g/dL. Résultat validé.",
        category_code=None,
        ai_suggested_category_code=None,
        extracted_fields=[],
        created_at=utcnow(),
        updated_at=utcnow(),
        file_path=None,
        uploaded_by=None,
    )


async def test_extraction_uses_only_document_text_and_categories_without_saving(monkeypatch):
    document = _service_document()
    category = SimpleNamespace(code="LAB_RESULT", label="Résultat de laboratoire", description=None)
    repository = FakeDocumentRepository(document, [category])
    service = DocumentService(repository)
    calls: list[dict] = []

    async def fake_generate_json(*, module, system, user, output_schema):
        calls.append(
            {"module": module, "system": system, "user": user, "output_schema": output_schema}
        )
        return DocumentExtraction(
            fields=[
                ExtractedFieldProposal(name="hémoglobine", value="13 g/dL"),
                ExtractedFieldProposal(name="dose", value="500 mg"),
                ExtractedFieldProposal(name="autre", value=None),
            ],
            suggested_category_code="LAB_RESULT",
        )

    monkeypatch.setattr("app.modules.documents.service.generate_json", fake_generate_json)

    result = await service.extract(_service_user(), str(document.id))

    assert len(calls) == 1
    assert calls[0]["module"] == "documents"
    assert calls[0]["output_schema"] is DocumentExtraction
    assert "Hémoglobine : 13 g/dL." in calls[0]["user"]
    assert "LAB_RESULT" in calls[0]["user"]
    assert document.title not in calls[0]["user"]
    assert str(document.patient_id) not in calls[0]["user"]
    assert [field.value for field in result.fields] == ["13 g/dL", None, None]
    assert result.suggested_category_code == "LAB_RESULT"
    assert len(result.warnings) == 1
    assert repository.save_count == 0


async def test_extraction_discards_unknown_category(monkeypatch):
    document = _service_document()
    repository = FakeDocumentRepository(document, [])
    service = DocumentService(repository)

    async def fake_generate_json(*, module, system, user, output_schema):
        return DocumentExtraction(
            fields=[],
            suggested_category_code="UNKNOWN",
        )

    monkeypatch.setattr("app.modules.documents.service.generate_json", fake_generate_json)

    result = await service.extract(_service_user(), str(document.id))

    assert result.suggested_category_code is None
    assert result.warnings == ["La catégorie proposée n'existe pas; elle a été ignorée."]
    assert repository.save_count == 0


async def test_review_validates_all_fields_with_actor_and_timestamp():
    document = _service_document()
    category = SimpleNamespace(code="LAB_RESULT", label="Résultat de laboratoire", description=None)
    repository = FakeDocumentRepository(document, [category])
    service = DocumentService(repository)
    doctor = _service_user()

    result = await service.review(
        doctor,
        str(document.id),
        DocumentReview(
            status=AiReviewStatus.VALIDATED,
            fields=[
                ReviewedField(name="hémoglobine", value="13 g/dL"),
                ReviewedField(name="résultat", value="validé"),
            ],
            category_code="LAB_RESULT",
            ai_suggested_category_code="LAB_RESULT",
        ),
    )

    assert repository.save_count == 1
    assert result.status == AiReviewStatus.VALIDATED
    assert result.category_code == "LAB_RESULT"
    assert result.ai_suggested_category_code == "LAB_RESULT"
    assert all(field.status == AiReviewStatus.VALIDATED for field in document.extracted_fields)
    assert all(field.validated_by == doctor.id for field in document.extracted_fields)
    assert all(field.validated_at is not None for field in document.extracted_fields)


async def test_review_rejects_all_fields_and_clears_selected_category():
    document = _service_document()
    category = SimpleNamespace(code="LAB_RESULT", label="Résultat de laboratoire", description=None)
    repository = FakeDocumentRepository(document, [category])
    service = DocumentService(repository)

    result = await service.review(
        _service_user(),
        str(document.id),
        DocumentReview(
            status=AiReviewStatus.REJECTED,
            fields=[ReviewedField(name="hémoglobine", value="13 g/dL")],
            category_code="LAB_RESULT",
            ai_suggested_category_code="LAB_RESULT",
        ),
    )

    assert result.status == AiReviewStatus.REJECTED
    assert result.category_code is None
    assert result.ai_suggested_category_code == "LAB_RESULT"
    assert document.extracted_fields[0].status == AiReviewStatus.REJECTED
    assert document.extracted_fields[0].validated_by is not None
    assert document.extracted_fields[0].validated_at is not None
    assert repository.save_count == 1


async def test_review_rejects_unsupported_values_without_saving():
    document = _service_document()
    repository = FakeDocumentRepository(document, [])
    service = DocumentService(repository)

    with pytest.raises(APIError) as error:
        await service.review(
            _service_user(),
            str(document.id),
            DocumentReview(
                status=AiReviewStatus.REJECTED,
                fields=[ReviewedField(name="dose", value="500 mg")],
            ),
        )

    assert error.value.code == "unsupported_extracted_value"
    assert repository.save_count == 0


async def test_secretary_cannot_review_document():
    document = _service_document()
    repository = FakeDocumentRepository(document, [])
    service = DocumentService(repository)

    with pytest.raises(APIError) as error:
        await service.review(
            _service_user(Role.SECRETARY),
            str(document.id),
            DocumentReview(
                status=AiReviewStatus.REJECTED,
                fields=[ReviewedField(name="hémoglobine", value="13 g/dL")],
            ),
        )

    assert error.value.code == "role_forbidden"
    assert repository.save_count == 0