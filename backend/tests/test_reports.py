import pytest
from beanie import PydanticObjectId

from app.modules.auth.models import Role, User
from app.modules.reports.guardrails import check_content
from app.modules.reports.prompts import MISSING_SECTION
from app.modules.reports.schemas import StructuredReport
from app.modules.reports.service import render

NOTES = (
    "Patient de passage pour toux depuis 3 jours. Température 38.5. "
    "Auscultation normale. Repos conseillé, revoir si fièvre persiste."
)


# ── Garde-fou et rendu (sans base de données) ─────────────────────────────────

def test_guardrail_accepts_values_present_in_notes():
    assert check_content("Température 38,5 et tension 120/80", "Fièvre à 38.5, TA 120/80") == []


def test_guardrail_flags_values_missing_from_notes():
    warnings = check_content("Toux depuis 3 jours", "Toux depuis 3 jours, paracétamol 500 mg")
    assert len(warnings) == 1 and "500" in warnings[0]


def test_render_fills_missing_sections():
    content = StructuredReport(
        reason="Toux", history=" ", examination="Normal", assessment="RAS", plan="Repos"
    )
    text = render(content)
    assert "## Motif de consultation\nToux" in text
    assert f"## Antécédents et contexte\n{MISSING_SECTION}" in text


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def auth(token_factory):
    def headers(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_factory(user)}"}

    return headers


@pytest.fixture
async def doctor(user_factory) -> User:
    return await user_factory(email="dr.one@example.test", role=Role.DOCTOR)


@pytest.fixture
async def other_doctor(user_factory) -> User:
    return await user_factory(email="dr.two@example.test", role=Role.DOCTOR)


@pytest.fixture
async def admin(user_factory) -> User:
    return await user_factory(email="admin@example.test", role=Role.ADMIN)


@pytest.fixture
async def secretary(user_factory) -> User:
    return await user_factory(email="secretary@example.test", role=Role.SECRETARY)


class FakeLLM:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.output = StructuredReport(
            reason="Toux depuis 3 jours.",
            history=MISSING_SECTION,
            examination="Température à 38.5. Auscultation normale.",
            assessment=MISSING_SECTION,
            plan="Repos conseillé. Revoir si la fièvre persiste.",
        )

    async def __call__(self, *, module, system, user, output_schema):
        self.calls.append({"module": module, "system": system, "user": user})
        return self.output


@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLM:
    fake = FakeLLM()
    monkeypatch.setattr("app.modules.reports.service.generate_json", fake)
    return fake


@pytest.fixture
def create_report(api_client, auth):
    async def create(doctor: User, **overrides) -> dict:
        payload = {
            "patient_id": str(PydanticObjectId()),
            "title": "Consultation du jour",
            "raw_notes": NOTES,
        } | overrides
        response = await api_client.post("/api/reports", headers=auth(doctor), json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return create


# ── Droits ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", [Role.PATIENT, Role.ADMIN_STAFF])
async def test_other_roles_cannot_use_reports(api_client, user_factory, auth, role):
    user = await user_factory(email=f"{role.value.lower()}@example.test", role=role)

    assert (await api_client.get("/api/reports", headers=auth(user))).status_code == 403
    assert (await api_client.get("/api/reports")).status_code == 401


async def test_only_doctors_can_create(api_client, admin, secretary, auth):
    payload = {"patient_id": str(PydanticObjectId()), "title": "T", "raw_notes": NOTES}
    for user in (admin, secretary):
        response = await api_client.post("/api/reports", headers=auth(user), json=payload)
        assert response.status_code == 403


async def test_doctor_sees_only_own_reports(api_client, doctor, other_doctor, admin, auth, create_report):
    report = await create_report(doctor)

    own = await api_client.get(f"/api/reports/{report['id']}", headers=auth(doctor))
    foreign = await api_client.get(f"/api/reports/{report['id']}", headers=auth(other_doctor))
    as_admin = await api_client.get(f"/api/reports/{report['id']}", headers=auth(admin))
    other_list = await api_client.get("/api/reports", headers=auth(other_doctor))

    assert own.status_code == 200
    assert foreign.status_code == 404
    assert as_admin.status_code == 200
    assert other_list.json()["total"] == 0


async def test_secretary_only_sees_finalized_reports(
    api_client, doctor, secretary, auth, create_report, fake_llm
):
    draft = await create_report(doctor, title="Brouillon")
    final = await create_report(doctor, title="Final")
    await api_client.post(f"/api/reports/{final['id']}/generate", headers=auth(doctor))
    await api_client.post(f"/api/reports/{final['id']}/finalize", headers=auth(doctor))

    listing = await api_client.get("/api/reports", headers=auth(secretary))
    hidden = await api_client.get(f"/api/reports/{draft['id']}", headers=auth(secretary))

    assert [item["title"] for item in listing.json()["items"]] == ["Final"]
    assert hidden.status_code == 404


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def test_create_sets_author_and_draft_status(doctor, create_report):
    report = await create_report(doctor)

    assert report["status"] == "DRAFT"
    assert report["doctor_id"] == str(doctor.id)
    assert report["structured_content"] is None


async def test_create_rejects_empty_notes(api_client, doctor, auth):
    response = await api_client.post(
        "/api/reports",
        headers=auth(doctor),
        json={"patient_id": str(PydanticObjectId()), "title": "T", "raw_notes": "   "},
    )
    assert response.status_code == 422


async def test_invalid_report_id_returns_not_found(api_client, doctor, auth):
    response = await api_client.get("/api/reports/not-an-id", headers=auth(doctor))
    assert response.status_code == 404 and response.json()["code"] == "report_not_found"


async def test_list_filters_search_and_paginates(api_client, doctor, auth, create_report):
    patient = str(PydanticObjectId())
    for title in ("Toux", "Fièvre", "Contrôle"):
        await create_report(doctor, title=title, patient_id=patient)
    await create_report(doctor, title="Autre patient")

    page = await api_client.get(f"/api/reports?patient_id={patient}&size=2&page=2", headers=auth(doctor))
    search = await api_client.get("/api/reports?q=fièv", headers=auth(doctor))

    assert page.json()["total"] == 3 and len(page.json()["items"]) == 1
    assert [item["title"] for item in search.json()["items"]] == ["Fièvre"]
    assert "raw_notes" not in page.json()["items"][0]


async def test_update_draft_and_notes_change_clears_generated_content(
    api_client, doctor, auth, create_report, fake_llm
):
    report = await create_report(doctor)
    await api_client.post(f"/api/reports/{report['id']}/generate", headers=auth(doctor))

    renamed = await api_client.patch(
        f"/api/reports/{report['id']}", headers=auth(doctor), json={"title": "Nouveau titre"}
    )
    edited = await api_client.patch(
        f"/api/reports/{report['id']}", headers=auth(doctor), json={"raw_notes": NOTES + " Ajout."}
    )

    assert renamed.json()["title"] == "Nouveau titre"
    assert renamed.json()["structured_content"] is not None
    assert edited.json()["structured_content"] is None


async def test_archive_hides_report_and_locks_it(api_client, doctor, admin, auth, create_report):
    report = await create_report(doctor)

    archived = await api_client.post(f"/api/reports/{report['id']}/archive", headers=auth(doctor))
    again = await api_client.post(f"/api/reports/{report['id']}/archive", headers=auth(admin))
    default_list = await api_client.get("/api/reports", headers=auth(doctor))
    archived_list = await api_client.get("/api/reports?status=ARCHIVED", headers=auth(doctor))
    edit = await api_client.patch(
        f"/api/reports/{report['id']}", headers=auth(doctor), json={"title": "X"}
    )

    assert archived.status_code == 200 and archived.json()["archived_at"] is not None
    assert again.status_code == 409 and again.json()["code"] == "already_archived"
    assert default_list.json()["total"] == 0
    assert archived_list.json()["total"] == 1
    assert edit.status_code == 409


# ── LLM et garde-fou ──────────────────────────────────────────────────────────

async def test_generate_structures_notes(api_client, doctor, auth, create_report, fake_llm):
    report = await create_report(doctor)

    response = await api_client.post(f"/api/reports/{report['id']}/generate", headers=auth(doctor))

    body = response.json()
    assert response.status_code == 200
    assert "## Motif de consultation" in body["structured_content"]
    assert body["warnings"] == []
    assert body["status"] == "DRAFT"


async def test_only_notes_are_sent_to_llm(api_client, doctor, auth, create_report, fake_llm):
    report = await create_report(doctor, title="Compte rendu Leila Haddad")

    await api_client.post(f"/api/reports/{report['id']}/generate", headers=auth(doctor))

    sent = fake_llm.calls[0]["system"] + fake_llm.calls[0]["user"]
    assert NOTES in sent
    assert "Leila" not in sent
    assert report["patient_id"] not in sent and report["id"] not in sent
    assert fake_llm.calls[0]["module"] == "reports"


async def test_generate_requires_enough_notes(api_client, doctor, auth, create_report, fake_llm):
    report = await create_report(doctor, raw_notes="Toux.")

    response = await api_client.post(f"/api/reports/{report['id']}/generate", headers=auth(doctor))

    assert response.status_code == 422 and response.json()["code"] == "notes_too_short"
    assert fake_llm.calls == []


async def test_unsupported_value_is_flagged_and_blocks_finalization(
    api_client, doctor, auth, create_report, fake_llm
):
    fake_llm.output.plan = "Paracétamol 500 mg."
    report = await create_report(doctor)

    generated = await api_client.post(f"/api/reports/{report['id']}/generate", headers=auth(doctor))
    blocked = await api_client.post(f"/api/reports/{report['id']}/finalize", headers=auth(doctor))
    confirmed = await api_client.post(
        f"/api/reports/{report['id']}/finalize",
        headers=auth(doctor),
        json={"confirm_warnings": True},
    )

    assert any("500" in warning for warning in generated.json()["warnings"])
    assert blocked.status_code == 409 and blocked.json()["code"] == "unverified_content"
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "FINAL"


async def test_finalize_requires_content_then_locks_report(
    api_client, doctor, auth, create_report, fake_llm
):
    report = await create_report(doctor)
    base = f"/api/reports/{report['id']}"

    empty = await api_client.post(f"{base}/finalize", headers=auth(doctor))
    await api_client.post(f"{base}/generate", headers=auth(doctor))
    final = await api_client.post(f"{base}/finalize", headers=auth(doctor))
    edit = await api_client.patch(base, headers=auth(doctor), json={"title": "X"})
    regenerate = await api_client.post(f"{base}/generate", headers=auth(doctor))

    assert empty.status_code == 409 and empty.json()["code"] == "nothing_to_finalize"
    assert final.status_code == 200 and final.json()["status"] == "FINAL"
    assert edit.status_code == 409 and edit.json()["code"] == "report_locked"
    assert regenerate.status_code == 409
