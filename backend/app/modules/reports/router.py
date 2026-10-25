from fastapi import APIRouter, Depends, Query, Response, status

from app.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.reports.models import ReportStatus
from app.modules.reports.schemas import (
    FinalizeRequest,
    ReportCreate,
    ReportOut,
    ReportPage,
    ReportUpdate,
)
from app.modules.reports.service import ReportService

router = APIRouter()
PREFIX = "/api/reports"
TAGS = ["reports"]

doctor_only = require_roles(Role.DOCTOR)
readers = require_roles(Role.DOCTOR, Role.ADMIN, Role.SECRETARY, Role.PATIENT)
archivers = require_roles(Role.DOCTOR, Role.ADMIN)


def get_report_service() -> ReportService:
    return ReportService()


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def create_report(
    data: ReportCreate,
    user: User = Depends(doctor_only),
    service: ReportService = Depends(get_report_service),
) -> ReportOut:
    """Créer un compte rendu (brouillon) à partir des notes brutes du médecin."""
    return await service.create(user, data)


@router.get("", response_model=ReportPage)
async def list_reports(
    status_filter: ReportStatus | None = Query(default=None, alias="status"),
    patient_id: str | None = None,
    q: str | None = Query(default=None, max_length=100, description="Recherche dans le titre"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(readers),
    service: ReportService = Depends(get_report_service),
) -> ReportPage:
    """Consulter les comptes rendus. Les archivés n'apparaissent qu'avec status=ARCHIVED."""
    return await service.list(
        user, status=status_filter, patient_id=patient_id, text=q, page=page, size=size
    )


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: str,
    user: User = Depends(readers),
    service: ReportService = Depends(get_report_service),
) -> ReportOut:
    return await service.get(user, report_id)


@router.patch("/{report_id}", response_model=ReportOut)
async def update_report(
    report_id: str,
    data: ReportUpdate,
    user: User = Depends(doctor_only),
    service: ReportService = Depends(get_report_service),
) -> ReportOut:
    """Modifier un brouillon. Modifier les notes efface le contenu généré devenu obsolète."""
    return await service.update(user, report_id, data)


@router.post("/{report_id}/archive", response_model=ReportOut)
async def archive_report(
    report_id: str,
    user: User = Depends(archivers),
    service: ReportService = Depends(get_report_service),
) -> ReportOut:
    """Archiver un compte rendu (pas de suppression)."""
    return await service.archive(user, report_id)


# ── Export ────────────────────────────────────────────────────────────────────

@router.get("/{report_id}/pdf", responses={200: {"content": {"application/pdf": {}}}})
async def export_report_pdf(
    report_id: str,
    user: User = Depends(readers),
    service: ReportService = Depends(get_report_service),
) -> Response:
    """Télécharger le compte rendu en PDF (sans notes brutes ni avertissements)."""
    pdf, filename = await service.export_pdf(user, report_id)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",  # donnée médicale : pas de cache
        },
    )


# ── LLM et validation ─────────────────────────────────────────────────────────

@router.post("/{report_id}/generate", response_model=ReportOut)
async def generate_report(
    report_id: str,
    user: User = Depends(doctor_only),
    service: ReportService = Depends(get_report_service),
) -> ReportOut:
    """Structurer les notes avec le LLM. Seules les notes sont envoyées ; `warnings` liste
    les valeurs absentes des notes."""
    return await service.generate(user, report_id)


@router.post("/{report_id}/finalize", response_model=ReportOut)
async def finalize_report(
    report_id: str,
    data: FinalizeRequest | None = None,
    user: User = Depends(doctor_only),
    service: ReportService = Depends(get_report_service),
) -> ReportOut:
    """Valider le compte rendu : il passe en FINAL et n'est plus modifiable."""
    return await service.finalize(user, report_id, data)