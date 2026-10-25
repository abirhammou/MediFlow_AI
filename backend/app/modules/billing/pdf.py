"""Invoice and receipt PDFs (same look as the report PDF of reports/pdf.py)."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.modules.billing.models import InvoiceStatus, PaymentMethod, format_tnd
from app.modules.billing.schemas import InvoiceOut, PaymentOut
from app.modules.patients.dates import CLINIC_TZ

CLINIC = "Clinique MediFlow"
STATUS_LABELS = {
    InvoiceStatus.DRAFT: "Brouillon (non émise)",
    InvoiceStatus.ISSUED: "Émise, à régler",
    InvoiceStatus.PARTIAL: "Partiellement réglée",
    InvoiceStatus.PAID: "Réglée",
    InvoiceStatus.CANCELLED: "Annulée",
}
METHOD_LABELS = {
    PaymentMethod.CASH: "Espèces",
    PaymentMethod.CARD: "Carte bancaire",
    PaymentMethod.TRANSFER: "Virement",
    PaymentMethod.CHEQUE: "Chèque",
}
BLUE = colors.HexColor("#1d4ed8")
GREY = colors.HexColor("#64748b")
LINE = colors.HexColor("#e2e8f0")


def _text(value: str) -> str:
    return escape(value).replace("\n", "<br/>")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("T", parent=base["Title"], fontSize=18, alignment=0, spaceAfter=4),
        "meta": ParagraphStyle("M", parent=base["Normal"], fontSize=9, textColor=GREY, leading=13),
        "h": ParagraphStyle(
            "H", parent=base["Heading2"], fontSize=12, textColor=BLUE, spaceBefore=14, spaceAfter=4
        ),
        "body": ParagraphStyle("B", parent=base["BodyText"], fontSize=10.5, leading=15),
    }


def _day(value) -> str:
    return value.astimezone(CLINIC_TZ).strftime("%d/%m/%Y") if value else "—"


def _table(rows: list[list[str]], widths: list[float], *, header: bool = True) -> Table:
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (-1, 0), GREY),
        ]
    table.setStyle(TableStyle(style))
    return table


def _document(title: str, story: list, watermark: str | None) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=title,
        author=CLINIC,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=2 * cm,
        bottomMargin=2.2 * cm,
    )

    def decorate(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawString(2.2 * cm, 1.2 * cm, f"{CLINIC} · montants en dinars tunisiens (TND)")
        canvas.drawRightString(A4[0] - 2.2 * cm, 1.2 * cm, f"Page {document.page}")
        if watermark:  # a draft or cancelled invoice must not circulate as a valid one
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(45)
            canvas.setFont("Helvetica-Bold", 70)
            canvas.setFillColor(colors.Color(0.8, 0.8, 0.8, alpha=0.35))
            canvas.drawCentredString(0, 0, watermark)
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()


def _patient_line(invoice: InvoiceOut) -> str:
    name = invoice.patient_name or "Patient"
    return f"{_text(name)} · dossier {invoice.record_number or '—'}"


def build_invoice_pdf(invoice: InvoiceOut) -> bytes:
    s = _styles()
    story = [
        Paragraph(f"Facture {invoice.number}", s["title"]),
        Paragraph(
            f"{CLINIC}<br/>Patient : {_patient_line(invoice)}<br/>"
            f"Émise le : {_day(invoice.issued_at)} · Statut : {STATUS_LABELS[invoice.status]}",
            s["meta"],
        ),
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=0.8, color=LINE),
        Paragraph("Prestations", s["h"]),
        _table(
            [["Désignation", "Qté", "Prix unitaire", "Montant"]]
            + [
                [
                    Paragraph(_text(line.label), s["body"]),
                    str(line.quantity),
                    format_tnd(line.unit_price),
                    format_tnd(line.amount),
                ]
                for line in invoice.lines
            ],
            [8.4 * cm, 1.4 * cm, 3.4 * cm, 3.4 * cm],
        ),
        Spacer(1, 10),
        _table(
            [
                ["Total", format_tnd(invoice.total)],
                ["Part assurance", format_tnd(invoice.insurance_share)],
                ["Part patient", format_tnd(invoice.patient_share)],
                ["Déjà réglé", format_tnd(invoice.paid_amount)],
                ["Reste à payer", format_tnd(invoice.balance)],
            ],
            [13.2 * cm, 3.4 * cm],
            header=False,
        ),
    ]
    if invoice.payments:
        story += [
            Paragraph("Règlements", s["h"]),
            _table(
                [["Reçu", "Date", "Mode", "Montant"]]
                + [
                    [
                        p.receipt_number,
                        _day(p.created_at),
                        METHOD_LABELS[p.method],
                        format_tnd(p.amount),
                    ]
                    for p in invoice.payments
                ],
                [4.6 * cm, 3 * cm, 5.6 * cm, 3.4 * cm],
            ),
        ]
    if invoice.status == InvoiceStatus.CANCELLED and invoice.cancel_reason:
        story.append(Paragraph(f"Facture annulée : {_text(invoice.cancel_reason)}", s["meta"]))
    if invoice.note:
        story.append(Paragraph(_text(invoice.note), s["meta"]))
    watermark = {InvoiceStatus.DRAFT: "BROUILLON", InvoiceStatus.CANCELLED: "ANNULÉE"}.get(
        invoice.status
    )
    return _document(f"Facture {invoice.number}", story, watermark)


def build_receipt_pdf(payment: PaymentOut, invoice: InvoiceOut) -> bytes:
    s = _styles()
    is_refund = payment.amount < 0
    title = f"{'Reçu de remboursement' if is_refund else 'Reçu'} {payment.receipt_number}"
    story = [
        Paragraph(title, s["title"]),
        Paragraph(
            f"{CLINIC}<br/>Patient : {_patient_line(invoice)}<br/>Facture : {invoice.number}",
            s["meta"],
        ),
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=0.8, color=LINE),
        Spacer(1, 10),
        _table(
            [
                ["Date", _day(payment.created_at)],
                ["Mode de règlement", METHOD_LABELS[payment.method]],
                [
                    "Montant remboursé" if is_refund else "Montant reçu",
                    format_tnd(abs(payment.amount)),
                ],
                ["Reste à payer sur la facture", format_tnd(invoice.balance)],
            ],
            [10 * cm, 6.6 * cm],
            header=False,
        ),
    ]
    if payment.created_by_name:
        story += [
            Spacer(1, 10),
            Paragraph(f"Encaissé par : {_text(payment.created_by_name)}", s["meta"]),
        ]
    if payment.note:
        story.append(Paragraph(_text(payment.note), s["meta"]))
    return _document(title, story, None)
