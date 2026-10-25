"""Génération du PDF d'un compte rendu. Ne contient jamais les notes brutes ni les avertissements."""

import re
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from app.modules.reports.models import MedicalReport, ReportStatus

STATUS_LABEL = {
    ReportStatus.DRAFT: "Brouillon, non validé",
    ReportStatus.FINAL: "Finalisé",
    ReportStatus.ARCHIVED: "Archivé",
}


def _sections(content: str) -> list[tuple[str | None, str]]:
    """Même découpage que le frontend : « ## Titre\\ntexte »."""
    chunks = re.split(r"^## ", content, flags=re.MULTILINE)
    result: list[tuple[str | None, str]] = []
    if chunks[0].strip():  # texte libre sans titre (contenu modifié à la main)
        result.append((None, chunks[0].strip()))
    for chunk in chunks[1:]:
        title, _, body = chunk.partition("\n")
        result.append((title.strip(), body.strip()))
    return result


def _text(value: str) -> str:
    return escape(value).replace("\n", "<br/>")


def build_pdf(report: MedicalReport) -> bytes:
    base = getSampleStyleSheet()
    title_style = ParagraphStyle("T", parent=base["Title"], fontSize=18, alignment=0, spaceAfter=4)
    meta_style = ParagraphStyle("M", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#64748b"), leading=13)
    h_style = ParagraphStyle("H", parent=base["Heading2"], fontSize=12, textColor=colors.HexColor("#1d4ed8"), spaceBefore=14, spaceAfter=4)
    body_style = ParagraphStyle("B", parent=base["BodyText"], fontSize=10.5, leading=15)
    missing_style = ParagraphStyle("X", parent=body_style, textColor=colors.HexColor("#94a3b8"), fontName="Helvetica-Oblique")

    is_final = report.status == ReportStatus.FINAL
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, title=report.title, author="ReportWriter AI",
        leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm, bottomMargin=2.2 * cm,
    )

    story = [
        Paragraph(_text(report.title), title_style),
        Paragraph(
            f"Statut : {STATUS_LABEL[report.status]}<br/>"
            f"Date : {report.updated_at:%d/%m/%Y %H:%M} (UTC)<br/>"
            f"Patient : …{str(report.patient_id)[-6:]} · Médecin : …{str(report.doctor_id)[-6:]}",
            meta_style,
        ),
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#e2e8f0")),
    ]
    from app.modules.reports.prompts import MISSING_SECTION

    for title, body in _sections(report.structured_content or ""):
        if title:
            story.append(Paragraph(_text(title), h_style))
        style = missing_style if body == MISSING_SECTION else body_style
        story.append(Paragraph(_text(body), style))

    def decorate(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawString(2.2 * cm, 1.2 * cm, "Compte rendu structuré à partir des notes du médecin.")
        canvas.drawRightString(A4[0] - 2.2 * cm, 1.2 * cm, f"Page {document.page}")
        if not is_final:  # filigrane : un brouillon ne doit pas circuler comme un document validé
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(45)
            canvas.setFont("Helvetica-Bold", 70)
            canvas.setFillColor(colors.Color(0.8, 0.8, 0.8, alpha=0.35))
            canvas.drawCentredString(0, 0, "BROUILLON")
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()