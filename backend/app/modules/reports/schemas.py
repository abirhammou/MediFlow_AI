from beanie import PydanticObjectId
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.modules.reports.models import ReportStatus

MAX_NOTES_LENGTH = 20_000


# ── CRUD ──────────────────────────────────────────────────────────────────────

class ReportCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    patient_id: PydanticObjectId
    appointment_id: PydanticObjectId | None = None
    title: str = Field(min_length=1, max_length=200)
    raw_notes: str = Field(min_length=1, max_length=MAX_NOTES_LENGTH)


class ReportUpdate(BaseModel):
    """Champs modifiables d'un brouillon. Un champ absent reste inchangé."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=200)
    raw_notes: str | None = Field(default=None, min_length=1, max_length=MAX_NOTES_LENGTH)
    structured_content: str | None = Field(default=None, min_length=1, max_length=MAX_NOTES_LENGTH)


class FinalizeRequest(BaseModel):
    confirm_warnings: bool = Field(
        default=False,
        description="Le médecin confirme avoir vérifié les avertissements du garde-fou.",
    )


class ReportOut(BaseModel):
    id: str
    patient_id: str
    doctor_id: str
    doctor_name: str | None = Field(default=None, description="« Prénom Nom » du médecin auteur")
    is_mine: bool = Field(default=False, description="Le compte rendu a été rédigé par l'utilisateur connecté")
    appointment_id: str | None
    title: str
    raw_notes: str
    structured_content: str | None
    status: ReportStatus
    archived_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    warnings: list[str] = Field(
        default_factory=list,
        description="Éléments du compte rendu absents des notes (garde-fou), recalculés à chaque lecture.",
    )


class ReportListItem(BaseModel):
    """Version allégée pour les listes : sans les notes ni le contenu."""

    id: str
    patient_id: str
    doctor_id: str
    doctor_name: str | None = None
    is_mine: bool = False
    appointment_id: str | None
    title: str
    status: ReportStatus
    has_structured_content: bool
    archived_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ReportPage(BaseModel):
    items: list[ReportListItem]
    total: int
    page: int
    size: int


# ── LLM ───────────────────────────────────────────────────────────────────────

class StructuredReport(BaseModel):
    """Sortie attendue du LLM : une section par champ."""

    reason: str = Field(min_length=1, description="Motif de consultation")
    history: str = Field(min_length=1, description="Antécédents et contexte")
    examination: str = Field(min_length=1, description="Examen clinique")
    assessment: str = Field(min_length=1, description="Conclusion")
    plan: str = Field(min_length=1, description="Conduite à tenir")
