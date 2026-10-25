from beanie import PydanticObjectId
from bson.errors import InvalidId

from app.core.time import utcnow
from app.errors import APIError
from app.llm.service import generate_json
from app.modules.auth.models import Role, User
from app.modules.reports.guardrails import check_content
from app.modules.reports.models import MedicalReport, ReportStatus
from app.modules.reports.prompts import MISSING_SECTION, SYSTEM_PROMPT, report_prompt
from app.modules.reports.repository import ReportRepository
from app.modules.reports.schemas import (
    FinalizeRequest,
    ReportCreate,
    ReportListItem,
    ReportOut,
    ReportPage,
    ReportUpdate,
    StructuredReport,
)

MIN_NOTES_FOR_GENERATION = 20

SECTIONS = (
    ("reason", "Motif de consultation"),
    ("history", "Antécédents et contexte"),
    ("examination", "Examen clinique"),
    ("assessment", "Conclusion"),
    ("plan", "Conduite à tenir"),
)


def render(content: StructuredReport) -> str:
    """Assemble les sections en texte (structured_content est une chaîne en base)."""
    parts = []
    for field, title in SECTIONS:
        text = getattr(content, field).strip() or MISSING_SECTION
        parts.append(f"## {title}\n{text}")
    return "\n\n".join(parts)


def _not_found() -> APIError:
    return APIError(404, "report_not_found", "Compte rendu introuvable.")


def _to_out(report: MedicalReport) -> ReportOut:
    warnings = (
        check_content(report.raw_notes, report.structured_content)
        if report.structured_content
        else []
    )
    return ReportOut(
        id=str(report.id),
        patient_id=str(report.patient_id),
        doctor_id=str(report.doctor_id),
        appointment_id=str(report.appointment_id) if report.appointment_id else None,
        title=report.title,
        raw_notes=report.raw_notes,
        structured_content=report.structured_content,
        status=report.status,
        archived_at=report.archived_at,
        created_at=report.created_at,
        updated_at=report.updated_at,
        warnings=warnings,
    )


def _to_item(report: MedicalReport) -> ReportListItem:
    return ReportListItem(
        id=str(report.id),
        patient_id=str(report.patient_id),
        doctor_id=str(report.doctor_id),
        appointment_id=str(report.appointment_id) if report.appointment_id else None,
        title=report.title,
        status=report.status,
        has_structured_content=bool(report.structured_content),
        archived_at=report.archived_at,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


class ReportService:
    def __init__(self, repository: ReportRepository | None = None) -> None:
        self.repository = repository or ReportRepository()

    # ── Droits ────────────────────────────────────────────────────────────────
    # Médecin : ses comptes rendus. Admin : lecture de tous + archivage.
    # Secrétaire : lecture des comptes rendus finalisés uniquement.

    @staticmethod
    def _can_read(user: User, report: MedicalReport) -> bool:
        if user.role == Role.ADMIN:
            return True
        if user.role == Role.DOCTOR:
            return report.doctor_id == user.id
        if user.role == Role.SECRETARY:
            return report.status == ReportStatus.FINAL
        return False

    async def _load(
        self,
        user: User,
        report_id: str,
        *,
        author_only: bool = False,
        allow_admin: bool = False,
    ) -> MedicalReport:
        try:
            oid = PydanticObjectId(report_id)
        except (InvalidId, TypeError):
            raise _not_found() from None
        report = await self.repository.get(oid)
        if report is None or not self._can_read(user, report):
            raise _not_found()
        is_author = user.role == Role.DOCTOR and report.doctor_id == user.id
        is_admin = allow_admin and user.role == Role.ADMIN
        if author_only and not (is_author or is_admin):
            raise APIError(403, "not_report_author", "Seul le médecin auteur peut faire cette action.")
        return report

    @staticmethod
    def _ensure_draft(report: MedicalReport) -> None:
        if report.status == ReportStatus.FINAL:
            raise APIError(409, "report_locked", "Un compte rendu finalisé ne peut plus être modifié.")
        if report.status == ReportStatus.ARCHIVED:
            raise APIError(409, "report_archived", "Un compte rendu archivé ne peut plus être modifié.")

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def create(self, user: User, data: ReportCreate) -> ReportOut:
        # TODO: vérifier que patient_id / appointment_id existent sans lire les collections
        # des autres modules (voir la règle de propriété dans AUTH_FOR_MODULES.md).
        report = MedicalReport(
            patient_id=data.patient_id,
            doctor_id=user.id,
            appointment_id=data.appointment_id,
            title=data.title,
            raw_notes=data.raw_notes,
        )
        return _to_out(await self.repository.create(report))

    async def list(
        self,
        user: User,
        *,
        status: ReportStatus | None,
        patient_id: str | None,
        text: str | None,
        page: int,
        size: int,
    ) -> ReportPage:
        statuses = [status] if status else [ReportStatus.DRAFT, ReportStatus.FINAL]  # archivés masqués
        if user.role == Role.SECRETARY:
            statuses = [s for s in statuses if s == ReportStatus.FINAL]
        patient_oid = None
        if patient_id:
            try:
                patient_oid = PydanticObjectId(patient_id)
            except (InvalidId, TypeError):
                raise APIError(422, "invalid_patient_id", "Identifiant patient invalide.") from None

        items, total = [], 0
        if statuses:
            items, total = await self.repository.search(
                statuses=statuses,
                doctor_id=user.id if user.role == Role.DOCTOR else None,
                patient_id=patient_oid,
                text=text,
                page=page,
                size=size,
            )
        return ReportPage(items=[_to_item(r) for r in items], total=total, page=page, size=size)

    async def get(self, user: User, report_id: str) -> ReportOut:
        return _to_out(await self._load(user, report_id))

    async def update(self, user: User, report_id: str, data: ReportUpdate) -> ReportOut:
        report = await self._load(user, report_id, author_only=True)
        self._ensure_draft(report)
        changes = data.model_dump(exclude_none=True)
        notes_changed = "raw_notes" in changes and changes["raw_notes"] != report.raw_notes
        for field, value in changes.items():
            setattr(report, field, value)
        if notes_changed and "structured_content" not in changes:
            report.structured_content = None  # le contenu généré ne correspond plus aux notes
        return _to_out(await self.repository.save(report))

    async def archive(self, user: User, report_id: str) -> ReportOut:
        report = await self._load(user, report_id, author_only=True, allow_admin=True)
        if report.status == ReportStatus.ARCHIVED:
            raise APIError(409, "already_archived", "Ce compte rendu est déjà archivé.")
        report.status = ReportStatus.ARCHIVED
        report.archived_at = utcnow()
        return _to_out(await self.repository.save(report))

    # ── LLM ───────────────────────────────────────────────────────────────────

    async def generate(self, user: User, report_id: str) -> ReportOut:
        report = await self._load(user, report_id, author_only=True)
        self._ensure_draft(report)
        if len(report.raw_notes) < MIN_NOTES_FOR_GENERATION:
            raise APIError(422, "notes_too_short", "Les notes sont trop courtes pour être structurées.")

        # Liste blanche : seules les notes partent vers le LLM. En cas d'échec, le brouillon est intact.
        structured = await generate_json(
            module="reports",
            system=SYSTEM_PROMPT,
            user=report_prompt(report.raw_notes),
            output_schema=StructuredReport,
        )
        report.structured_content = render(structured)
        return _to_out(await self.repository.save(report))

    async def finalize(
        self, user: User, report_id: str, data: FinalizeRequest | None = None
    ) -> ReportOut:
        report = await self._load(user, report_id, author_only=True)
        self._ensure_draft(report)
        if not report.structured_content:
            raise APIError(409, "nothing_to_finalize", "Générez ou rédigez le compte rendu avant de le finaliser.")
        warnings = check_content(report.raw_notes, report.structured_content)
        if warnings and not (data and data.confirm_warnings):
            raise APIError(
                409,
                "unverified_content",
                "Des valeurs du compte rendu sont absentes des notes. "
                "Vérifiez-les puis confirmez avec confirm_warnings=true.",
            )
        report.status = ReportStatus.FINAL
        return _to_out(await self.repository.save(report))
