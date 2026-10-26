"""Demo medical documents as text and as patient files (run by scripts.seed_modules).

Each document of scripts.seed_document_data is rendered once (`render_document`): its
text is the MedDoc raw text, and the same document is stored in the patient record the
way an upload is (storage.save, then text extraction for MEDICAL files):
- lab results, imaging reports, letters and invoices: a PDF with a text layer
  (`build_document_pdf`; `build_pdf` makes the one-page PDFs of the tests);
- prescriptions, certificates and administrative papers: a PNG "scan" of the paper;
- MRI, CT, X-ray, ultrasound, ECG and angiography: also a JPEG image of the exam.
Per patient, the insurance certificate (insured patients) and the latest invoice are
added as ADMINISTRATIVE PDFs. All fictitious. Idempotent: looked up by patient + title.
"""

import io
import math
import random
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from beanie.operators import Eq, In
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.time import utcnow
from app.modules.auth.models import User
from app.modules.billing.models import Invoice, InvoiceStatus, format_tnd
from app.modules.patient_files import storage
from app.modules.patient_files.extraction import extract_text
from app.modules.patient_files.models import FileCategory, FileMime, FileType, PatientFile
from app.modules.patients.dates import CLINIC_TZ, from_mongo_date
from app.modules.patients.models import Patient
from scripts.seed_clinical_data import History
from scripts.seed_document_data import CNAM, Doc, Imaging, Lab, Letter, Prescription

SCANNED = {"ORDONNANCE", "CERTIFICAT", "ADMINISTRATIF", "CNAM"}  # paper documents
ADMINISTRATIVE_TYPES = {"CNAM": FileType.INSURANCE, "FINANCIER": FileType.INVOICE}
MODALITY_LABELS = {
    "IRM": "IRM 1,5 T",
    "SCANNER": "TDM",
    "RADIO": "RX",
    "ECHO": "US",
    "ECG": "ECG",
    "ANGIO": "XA",
}
Section = tuple[str | None, list[str]]


def _day(value: date) -> str:
    return f"{value:%d/%m/%Y}"


def _fill(text: str, day: date) -> str:
    return text.replace("{date}", _day(day))


def prescriber(history: History, doc: Doc) -> str:
    """Doctor code of the last visit on or before the document (the first visit for older
    documents)."""
    before = [visit for visit in history.visits if visit.days_ago >= doc.days_ago]
    return (before[-1] if before else history.visits[0]).doctor


@dataclass(frozen=True)
class Rendered:
    doc: Doc
    day: date
    issuer: str
    header: list[str]
    sections: list[Section]
    fields: list[tuple[str, str]]

    @property
    def text(self) -> str:
        lines = [self.issuer, *self.header]
        for heading, body in self.sections:
            lines.append("")
            if heading:
                lines.append(f"{heading} :")
            lines.extend(body)
        return "\n".join(lines)


def render_document(doc: Doc, patient: Patient, doctor: User, day: date) -> Rendered:
    """Issuer, header and sections of the document, from which the text and the file are
    built."""
    doctor_name = f"Dr {doctor.first_name} {doctor.last_name}"
    specialty = doctor.doctor_profile.specialty if doctor.doctor_profile else "médecine"
    practice = f"{doctor_name}, {specialty.lower()}, clinique MediFlow, Tunis"
    born = _day(from_mongo_date(patient.date_of_birth))
    identity = (
        f"Patient : {patient.first_name} {patient.last_name}, date de naissance {born}, "
        f"dossier {patient.record_number}"
    )
    body = doc.body
    sections: list[Section]
    if isinstance(body, Lab):
        issuer = body.lab
        header = [
            doc.title.upper(),
            f"Date du prélèvement : {_day(day)}",
            identity,
            f"Prescripteur : {doctor_name}",
        ]
        sections = [
            (
                "Résultats",
                [f"- {name} : {result} (référence : {ref})" for name, result, ref in body.rows],
            ),
            (None, [f"Commentaire : {body.comment}"]),
            (None, ["Validé par le biologiste responsable"]),
        ]
    elif isinstance(body, Imaging):
        issuer = body.centre
        header = [
            doc.title.upper(),
            f"Date de l'examen : {_day(day)}",
            identity,
            f"Demandé par : {body.requested_by or doctor_name}",
        ]
        sections = [
            (None, [f"Indication : {body.indication}", f"Technique : {body.technique}"]),
            ("Résultats", [f"- {finding}" for finding in body.findings]),
            (None, [f"Conclusion : {body.conclusion}"]),
            (None, [body.signed_by]),
        ]
    elif isinstance(body, Prescription):
        issuer = practice
        header = ["ORDONNANCE", f"Tunis, le {_day(day)}", identity]
        items = [
            f"{number}. {name} : {instructions}"
            for number, (name, instructions) in enumerate(body.items, start=1)
        ]
        sections = [(None, items)]
        if body.note:
            sections.append((None, [body.note]))
        sections.append((None, [f"{doctor_name}, signature et cachet"]))
    else:
        assert isinstance(body, Letter)
        issuer = body.issuer or practice
        header = [doc.title.upper(), f"Date : {_day(day)}", identity]
        sections = [
            (None, [_fill(paragraph, day) for paragraph in body.paragraphs]),
            (None, [body.signed_by or doctor_name]),
        ]
    fields = [(name, _fill(value, day)) for name, value in doc.fields]
    return Rendered(doc, day, issuer, header, sections, fields)


# ── PDF (text layer: pypdf extracts it at upload) ─────────────────────────────


def build_pdf(title: str, lines: list[str]) -> bytes:
    """One A4 page: clinic header, title, then the text wrapped at ~90 characters (tests)."""
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4, invariant=1)  # invariant: same bytes every run
    page.setTitle(title)
    y = A4[1] - 2 * cm
    page.setFont("Helvetica-Bold", 10)
    page.drawString(2 * cm, y, "Clinique MediFlow - document de démonstration (fictif)")
    y -= 1.2 * cm
    page.setFont("Helvetica-Bold", 14)
    page.drawString(2 * cm, y, title)
    y -= 1 * cm
    page.setFont("Helvetica", 11)
    for line in lines:
        words, current = line.split(), ""
        for word in words:
            if len(current) + len(word) > 90:
                page.drawString(2 * cm, y, current)
                y -= 0.6 * cm
                current = ""
            current = f"{current} {word}".strip()
        page.drawString(2 * cm, y, current)
        y -= 0.8 * cm
    page.showPage()
    page.save()
    return buffer.getvalue()


def build_document_pdf(
    title: str,
    issuer: str,
    header: list[str],
    sections: list[Section],
    table: list[tuple[str, str, str]] | None = None,
) -> bytes:
    """A4 document; `table` replaces the "Résultats" lines (lab results)."""
    base = getSampleStyleSheet()
    issuer_style = ParagraphStyle(
        "I", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#1d4ed8")
    )
    title_style = ParagraphStyle("T", parent=base["Title"], fontSize=15, alignment=0)
    meta_style = ParagraphStyle(
        "M", parent=base["Normal"], fontSize=9, leading=13, textColor=colors.HexColor("#475569")
    )
    heading_style = ParagraphStyle("H", parent=base["Heading3"], spaceBefore=10)
    body_style = ParagraphStyle("B", parent=base["BodyText"], fontSize=10.5, leading=15)
    note_style = ParagraphStyle(
        "N", parent=meta_style, fontSize=7.5, textColor=colors.HexColor("#94a3b8")
    )

    story = [
        Paragraph(escape(issuer), issuer_style),
        Spacer(1, 0.4 * cm),
        Paragraph(escape(header[0]), title_style),
    ]
    story += [Paragraph(escape(line), meta_style) for line in header[1:]]
    story.append(Spacer(1, 0.3 * cm))
    for heading, lines in sections:
        if heading:
            story.append(Paragraph(escape(heading), heading_style))
        if heading == "Résultats" and table:
            grid = Table(
                [("Analyse", "Résultat", "Valeurs de référence"), *table],
                colWidths=[6.5 * cm, 4.5 * cm, 6 * cm],
            )
            grid.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(grid)
            continue
        story += [Paragraph(escape(line), body_style) for line in lines]
        story.append(Spacer(1, 0.15 * cm))
    story += [
        Spacer(1, 0.8 * cm),
        Paragraph("Document de démonstration MediFlow : données fictives.", note_style),
    ]

    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=title,
        author="MediFlow (démo)",
        invariant=1,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
    ).build(story)
    return buffer.getvalue()


# ── Images (Pillow) ───────────────────────────────────────────────────────────


# Pillow's default font has no accented letters: Bitstream Vera, shipped with reportlab.
FONT = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT), size)


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _jpeg(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    return buffer.getvalue()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    return [*lines, current] if current else lines


def build_scan(rendered: Rendered) -> bytes:
    """Grey "scanned paper": the text, an ink signature, a slight tilt."""
    rng = random.Random(rendered.doc.title)
    width, height = 992, 1403  # A4 at 120 dpi
    page = Image.new("L", (width, height), 246)
    draw = ImageDraw.Draw(page)
    for _ in range(400):  # paper grain
        x, y = rng.randrange(width), rng.randrange(height)
        draw.point((x, y), fill=rng.randrange(205, 235))
    small, normal, large = _font(17), _font(21), _font(30)
    margin, y = 90, 80
    for line in _wrap(draw, rendered.issuer, small, width - 2 * margin):
        draw.text((margin, y), line, font=small, fill=70)
        y += 24
    y += 30
    draw.text((margin, y), rendered.header[0], font=large, fill=20)
    y += 52
    for line in rendered.header[1:]:
        draw.text((margin, y), line, font=small, fill=60)
        y += 26
    y += 20
    for heading, lines in rendered.sections:
        if heading:
            draw.text((margin, y), f"{heading} :", font=normal, fill=20)
            y += 32
        for paragraph in lines:
            for line in _wrap(draw, paragraph, normal, width - 2 * margin):
                draw.text((margin, y), line, font=normal, fill=35)
                y += 30
            y += 10
        y += 14
    # handwritten-like signature and a round stamp
    x0, y0 = width - 380, min(y + 20, height - 220)
    points = [(x0 + i * 6, y0 + 40 + 18 * math.sin(i / 3) + rng.uniform(-6, 6)) for i in range(40)]
    draw.line(points, fill=40, width=3)
    draw.ellipse((x0 + 150, y0 - 10, x0 + 290, y0 + 130), outline=110, width=4)
    draw.text((x0 + 175, y0 + 50), "MediFlow", font=small, fill=110)
    page = page.rotate(rng.uniform(-1.2, 1.2), resample=Image.Resampling.BICUBIC, fillcolor=215)
    return _png(page)


def _noise(size: tuple[int, int], sigma: float) -> Image.Image:
    return Image.effect_noise(size, sigma)


def _overlay(image: Image.Image, rendered: Rendered, patient: Patient, modality: str) -> None:
    draw = ImageDraw.Draw(image)
    font = _font(14)
    fill = 230 if image.mode == "L" else (30, 30, 30)
    width, height = image.size
    title = rendered.doc.title
    draw.text((10, 8), rendered.issuer[:60], font=font, fill=fill)
    draw.text((10, 26), title[:60], font=font, fill=fill)
    draw.text((10, height - 44), f"Dossier {patient.record_number}", font=font, fill=fill)
    draw.text((10, height - 24), _day(rendered.day), font=font, fill=fill)
    label = MODALITY_LABELS[modality]
    draw.text((width - 10 - draw.textlength(label, font=font), 8), label, font=font, fill=fill)
    mark = "Image de démonstration"
    draw.text(
        (width - 10 - draw.textlength(mark, font=font), height - 24), mark, font=font, fill=fill
    )


def _textured(image: Image.Image, blur: float) -> Image.Image:
    """Tissue grain: multiplied by blurred noise, so the black background stays black."""
    grain = _noise(image.size, 80).filter(ImageFilter.GaussianBlur(blur))
    return ImageChops.multiply(image, grain.point(lambda value: 150 + value * 105 // 255))


def _mri(rng: random.Random, title: str) -> Image.Image:
    size = 512
    image = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(image)
    if "cérébr" in title.lower():  # axial brain
        draw.ellipse((86, 60, 426, 460), fill=200)
        draw.ellipse((100, 76, 412, 444), fill=95)
        for _ in range(26):  # sulci
            x, y = rng.randrange(130, 380), rng.randrange(100, 420)
            draw.arc(
                (x - 30, y - 18, x + 30, y + 18), rng.randrange(0, 180), 300, fill=150, width=3
            )
        draw.ellipse((220, 200, 248, 300), fill=15)
        draw.ellipse((264, 200, 292, 300), fill=15)
    elif "cardiaque" in title.lower():  # short axis of a dilated heart
        draw.ellipse((40, 90, 472, 430), fill=70)
        draw.ellipse((150, 150, 390, 380), fill=140)
        draw.ellipse((185, 185, 355, 345), fill=225)
        draw.ellipse((90, 200, 190, 320), fill=200)
    else:  # sagittal knee
        draw.rounded_rectangle((170, 0, 340, 230), radius=60, fill=150)
        draw.rounded_rectangle((180, 270, 330, 512), radius=40, fill=150)
        draw.rectangle((175, 228, 335, 272), fill=60)
        draw.ellipse((330, 150, 400, 260), fill=170)
        draw.ellipse((205, 245, 265, 262), fill=235)  # joint effusion
        draw.ellipse((120, 300, 170, 360), fill=250)  # popliteal cyst
    image = _textured(image.filter(ImageFilter.GaussianBlur(3)), 2.5)
    return Image.blend(image, _noise((size, size), 50), 0.1)


def _ct(rng: random.Random, title: str) -> Image.Image:
    size = 512
    image = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(image)
    if "thorac" in title.lower():
        draw.ellipse((30, 110, 482, 420), fill=95)
        draw.ellipse((70, 140, 240, 380), fill=8)  # collapsed left lung area (dark)
        draw.ellipse((150, 220, 230, 320), fill=70)  # retracted lung
        draw.ellipse((272, 140, 442, 380), fill=25)
        draw.ellipse((210, 190, 300, 290), fill=125)  # heart
        draw.ellipse((232, 330, 280, 378), fill=245)  # spine
    else:
        draw.ellipse((96, 56, 416, 456), fill=250)  # skull
        draw.ellipse((112, 72, 400, 440), fill=105)
        draw.ellipse((222, 210, 246, 290), fill=40)
        draw.ellipse((266, 210, 290, 290), fill=40)
        draw.ellipse((395, 140, 450, 230), fill=125)  # scalp haematoma
    image = _textured(image.filter(ImageFilter.GaussianBlur(2)), 1.5)
    return Image.blend(image, _noise((size, size), 40), 0.08)


def _xray(rng: random.Random, title: str) -> Image.Image:
    size = 512
    image = Image.new("L", (size, size), 20)
    draw = ImageDraw.Draw(image)
    lowered = title.lower()
    if "thorac" in lowered:
        draw.ellipse((50, 60, 462, 500), fill=55)
        draw.ellipse((80, 90, 240, 460), fill=25)
        draw.ellipse((272, 90, 432, 460), fill=25)
        for rib in range(9):
            y = 110 + rib * 38
            draw.arc((70, y, 250, y + 70), 200, 340, fill=150, width=6)
            draw.arc((262, y, 442, y + 70), 200, 340, fill=150, width=6)
        draw.ellipse((200, 230, 330, 420), fill=140)
        draw.rectangle((243, 40, 269, 500), fill=170)
    elif "mains" in lowered:
        for finger in range(5):
            x = 110 + finger * 70
            for bone in range(3):
                top = 60 + bone * 70 + (finger == 0) * 80
                draw.rounded_rectangle((x, top, x + 34, top + 60), radius=12, fill=200)
            draw.rounded_rectangle((x + 4, 280, x + 30, 380), radius=10, fill=190)
        draw.rounded_rectangle((120, 390, 420, 470), radius=30, fill=180)
    else:  # knee or shoulder
        draw.rounded_rectangle((190, 0, 320, 230), radius=50, fill=190)
        draw.rounded_rectangle((200, 262, 310, 512), radius=30, fill=190)
        if "genou" in lowered:  # prosthesis
            draw.rounded_rectangle((180, 190, 330, 240), radius=20, fill=255)
            draw.rectangle((195, 250, 315, 270), fill=255)
            draw.rectangle((240, 270, 270, 360), fill=255)
    image = _textured(image.filter(ImageFilter.GaussianBlur(2.5)), 3)
    return Image.blend(image, _noise((size, size), 30), 0.06)


def _ultrasound(rng: random.Random, title: str) -> Image.Image:
    size = 512
    speckle = _noise((size, size), 70).filter(ImageFilter.GaussianBlur(1.2))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).pieslice((-200, -380, 712, 500), 55, 125, fill=255)
    image = Image.new("L", (size, size), 0)
    image.paste(speckle, (0, 0), mask)
    draw = ImageDraw.Draw(image)
    lowered = title.lower()
    if "cardiaque" in lowered:
        draw.ellipse((200, 180, 290, 330), fill=15)
        draw.ellipse((285, 210, 350, 320), fill=15)
        draw.ellipse((215, 330, 300, 400), fill=20)
    elif "trimestre" in lowered:
        draw.ellipse((170, 200, 320, 330), outline=200, width=6)
        draw.ellipse((300, 270, 390, 370), outline=170, width=5)
        draw.ellipse((120, 330, 400, 460), fill=10)
    else:  # thyroid nodule
        draw.ellipse((150, 230, 250, 300), fill=55)
        draw.ellipse((270, 240, 330, 330), fill=30)
    image = image.filter(ImageFilter.GaussianBlur(1))
    return image


def _ecg(rng: random.Random, title: str) -> Image.Image:
    width, height = 1024, 360
    image = Image.new("RGB", (width, height), (255, 240, 240))
    draw = ImageDraw.Draw(image)
    for x in range(0, width, 10):
        draw.line((x, 0, x, height), fill=(250, 200, 200) if x % 50 else (240, 150, 150))
    for y in range(0, height, 10):
        draw.line((0, y, width, y), fill=(250, 200, 200) if y % 50 else (240, 150, 150))
    effort = "effort" in title.lower()
    baseline, beat = 200, 105 if effort else 150
    points = []
    for x in range(0, width):
        phase = x % beat
        y = 0.0
        y += 12 * math.exp(-((phase - 20) ** 2) / 40)  # P wave
        y += -10 * math.exp(-((phase - 38) ** 2) / 4)  # Q
        y += 95 * math.exp(-((phase - 44) ** 2) / 6)  # R
        y += -22 * math.exp(-((phase - 50) ** 2) / 5)  # S
        st = -16 if effort and 54 < phase < 72 else 0  # ST depression under effort
        y += st + 22 * math.exp(-((phase - 85) ** 2) / 90)  # T wave
        points.append((x, baseline - y + rng.uniform(-1.2, 1.2)))
    draw.line(points, fill=(20, 20, 20), width=2)
    draw.text((12, 48), "DII  25 mm/s  10 mm/mV", font=_font(14), fill=(30, 30, 30))
    return image


def _angio(rng: random.Random, title: str) -> Image.Image:
    size = 512
    image = Image.new("L", (size, size), 165)
    draw = ImageDraw.Draw(image)

    def branch(x: float, y: float, angle: float, length: float, width: int) -> None:
        if width < 2 or length < 14:
            return
        x2, y2 = x + length * math.cos(angle), y + length * math.sin(angle)
        draw.line((x, y, x2, y2), fill=35, width=width)
        branch(x2, y2, angle + rng.uniform(-0.5, 0.1), length * 0.8, width - 2)
        if rng.random() < 0.7:
            branch(x2, y2, angle + rng.uniform(0.3, 0.9), length * 0.6, width - 3)

    branch(120, 80, 0.9, 90, 14)
    branch(130, 90, 1.6, 80, 11)
    draw.line((176, 150, 204, 186), fill=235, width=9)  # stent
    image = image.filter(ImageFilter.GaussianBlur(1.5))
    return Image.blend(image, _noise((size, size), 30), 0.1)


DRAWERS = {
    "IRM": _mri,
    "SCANNER": _ct,
    "RADIO": _xray,
    "ECHO": _ultrasound,
    "ECG": _ecg,
    "ANGIO": _angio,
}


def build_exam_image(rendered: Rendered, patient: Patient, modality: str) -> bytes:
    rng = random.Random(f"{patient.record_number} {rendered.doc.title}")
    image = DRAWERS[modality](rng, rendered.doc.title)
    _overlay(image, rendered, patient, modality)
    return _jpeg(image)


# ── Patient files ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FileSpec:
    category: FileCategory
    file_type: FileType
    title: str
    original_name: str
    mime: FileMime
    data: bytes
    day: date


def _slug(title: str, day: date, extension: str) -> str:
    name = "_".join(title.replace("'", " ").split())[:80]
    return f"{name}_{day.isoformat()}{extension}"


def _document_files(rendered: Rendered, patient: Patient) -> list[FileSpec]:
    doc, body = rendered.doc, rendered.doc.body
    if doc.category in ADMINISTRATIVE_TYPES or doc.category == "ADMINISTRATIF":
        category = FileCategory.ADMINISTRATIVE
        file_type = ADMINISTRATIVE_TYPES.get(doc.category, FileType.OTHER)
    else:
        category = FileCategory.MEDICAL
        file_type = (
            FileType.LAB_RESULT
            if isinstance(body, Lab)
            else FileType.IMAGING
            if isinstance(body, Imaging)
            else FileType.SCAN
            if doc.category in SCANNED
            else FileType.OTHER
        )
    if doc.category in SCANNED:
        main = FileSpec(
            category,
            file_type,
            doc.title,
            _slug(doc.title, rendered.day, ".png"),
            FileMime.PNG,
            build_scan(rendered),
            rendered.day,
        )
    else:
        table = list(body.rows) if isinstance(body, Lab) else None
        data = build_document_pdf(
            doc.title, rendered.issuer, rendered.header, rendered.sections, table
        )
        main = FileSpec(
            category,
            file_type,
            doc.title,
            _slug(doc.title, rendered.day, ".pdf"),
            FileMime.PDF,
            data,
            rendered.day,
        )
    files = [main]
    if isinstance(body, Imaging) and body.modality:
        title = f"{doc.title} (images)"
        files.append(
            FileSpec(
                category,
                FileType.IMAGING,
                title,
                _slug(title, rendered.day, ".jpg"),
                FileMime.JPEG,
                build_exam_image(rendered, patient, body.modality),
                rendered.day,
            )
        )
    return files


def _identity(patient: Patient) -> str:
    return f"Patient : {patient.first_name} {patient.last_name}, dossier {patient.record_number}"


def _insurance_file(patient: Patient, today: date) -> FileSpec | None:
    insurance = patient.insurance
    if insurance is None or not insurance.provider:
        return None
    provider = insurance.provider
    title = f"Attestation d'assurance {provider}"
    day = today.replace(month=1, day=10) if today.month > 1 else today
    lines = [
        f"Organisme : {provider}",
        f"Numéro d'affiliation : {insurance.number or 'non renseigné'}",
        f"Droits ouverts du 01/01/{today.year} au 31/12/{today.year}.",
        "Attestation à présenter à chaque consultation, avec une pièce d'identité.",
    ]
    data = build_document_pdf(
        title,
        CNAM if provider == "CNAM" else provider,
        ["ATTESTATION DE DROITS", f"Date : {_day(day)}", _identity(patient)],
        [(None, lines), (None, ["Le gestionnaire"])],
    )
    return FileSpec(
        FileCategory.ADMINISTRATIVE,
        FileType.INSURANCE,
        title,
        _slug(title, day, ".pdf"),
        FileMime.PDF,
        data,
        day,
    )


async def _invoice_file(patient: Patient) -> FileSpec | None:
    """The latest issued invoice of scripts.seed_billing, as the PDF given to the patient."""
    invoice = (
        await Invoice.find(
            Eq(Invoice.patient_id, patient.id),
            In(Invoice.status, [InvoiceStatus.ISSUED, InvoiceStatus.PARTIAL, InvoiceStatus.PAID]),
        )
        .sort(-Invoice.issued_at)
        .first_or_none()
    )
    if invoice is None:
        return None
    issued = (invoice.issued_at or invoice.created_at).astimezone(CLINIC_TZ).date()
    title = f"Facture {invoice.number}"
    lines = [
        f"- {line.label} : {line.quantity} × {format_tnd(line.unit_price)}"
        for line in invoice.lines
    ]
    totals = [
        f"Total : {format_tnd(invoice.total)}",
        f"Part assurance : {format_tnd(invoice.insurance_share)}",
        f"Reste à charge du patient : {format_tnd(invoice.patient_share)}",
        f"Déjà réglé : {format_tnd(invoice.paid_amount)}",
        f"Solde à payer : {format_tnd(invoice.balance)}",
    ]
    data = build_document_pdf(
        title,
        "Clinique MediFlow, service de facturation, Tunis",
        [f"FACTURE N° {invoice.number}", f"Date : {_day(issued)}", _identity(patient)],
        [("Détail", lines), (None, totals)],
    )
    return FileSpec(
        FileCategory.ADMINISTRATIVE,
        FileType.INVOICE,
        title,
        _slug(title, issued, ".pdf"),
        FileMime.PDF,
        data,
        issued,
    )


async def seed_patient_files(
    patient: Patient,
    documents: list[Rendered],
    uploader: User,
    today: date,
    created: Counter,
    existing: Counter,
) -> None:
    for rendered in documents:
        await _store(patient, _document_files(rendered, patient), uploader, created, existing)
    extra = [_insurance_file(patient, today), await _invoice_file(patient)]
    await _store(patient, [spec for spec in extra if spec], uploader, created, existing)


async def _store(
    patient: Patient,
    specs: list[FileSpec],
    uploader: User,
    created: Counter,
    existing: Counter,
) -> None:
    for spec in specs:
        found = await PatientFile.find_one(
            Eq(PatientFile.patient_id, patient.id), Eq(PatientFile.title, spec.title)
        )
        if found is not None:
            existing["patient_files"] += 1
            continue
        stored = await storage.save(str(patient.id), spec.data, spec.mime)
        # Only MEDICAL files feed the AI, as at upload (OCR needs Tesseract for images).
        text, extraction = (
            extract_text(spec.data, spec.mime)
            if spec.category == FileCategory.MEDICAL
            else (None, None)
        )
        file = await PatientFile(
            patient_id=patient.id,
            category=spec.category,
            file_type=spec.file_type,
            title=spec.title,
            original_name=spec.original_name,
            storage_path=stored.path,
            mime=spec.mime,
            size=stored.size,
            sha256=stored.sha256,
            extracted_text=text,
            extraction_status=extraction,
            uploaded_by=uploader.id,
        ).insert()
        uploaded = datetime.combine(spec.day + timedelta(days=1), time(10), tzinfo=CLINIC_TZ)
        uploaded = min(uploaded.astimezone(UTC), utcnow())
        await file.set({"createdAt": uploaded, "updatedAt": uploaded})
        created["patient_files"] += 1
