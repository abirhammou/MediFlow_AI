"""Demo invoices and payments (run by scripts.seed_modules), all fictitious, in millimes.

One invoice per past visit of each demo patient, linked to its appointment: the oldest
is PAID, the next PARTIAL (or PAID), the latest ISSUED; every third patient also has a
DRAFT and a CANCELLED invoice. Insured patients get a 70 % insurance share. Dates are
back-dated to the visit, so the revenue report shows several days. Idempotent: an
invoice is looked up by its appointment (or its note for the extra ones).
"""

from collections import Counter
from datetime import timedelta

from beanie.operators import Eq

from app.core.sequence import INVOICE_SEQUENCE, RECEIPT_SEQUENCE, next_number
from app.core.time import utcnow
from app.modules.appointments.models import Appointment
from app.modules.auth.models import User
from app.modules.billing.models import Invoice, InvoiceLine, InvoiceStatus, Payment, PaymentMethod
from app.modules.patients.models import Patient

CARDIOLOGIST = "dr.trabelsi@mediflow.local"
METHODS = (PaymentMethod.CASH, PaymentMethod.CARD, PaymentMethod.CHEQUE, PaymentMethod.TRANSFER)
INSURANCE_RATE = 0.7


def _lines(appointment: Appointment, cardiology: bool) -> list[InvoiceLine]:
    if cardiology:
        return [
            InvoiceLine(label="Consultation de cardiologie", quantity=1, unit_price=60_000),
            InvoiceLine(label="Électrocardiogramme (ECG)", quantity=1, unit_price=25_000),
        ]
    return [
        InvoiceLine(
            label=f"Consultation : {appointment.reason or 'médecine générale'}"[:200],
            quantity=1,
            unit_price=45_000,
        )
    ]


def _insurance(patient: Patient, total: int) -> int:
    insured = patient.insurance is not None and bool(patient.insurance.provider)
    return int(total * INSURANCE_RATE) // 500 * 500 if insured else 0  # rounded to 0.5 TND


async def _invoice(
    patient: Patient,
    lines: list[InvoiceLine],
    status: InvoiceStatus,
    secretary: User,
    *,
    appointment: Appointment | None,
    note: str | None,
    paid_ratio: float,
    method: PaymentMethod,
    created: Counter,
    existing: Counter,
) -> None:
    lookup = (
        Invoice.find_one(Eq(Invoice.appointment_id, appointment.id))
        if appointment
        else Invoice.find_one(Eq(Invoice.patient_id, patient.id), Eq(Invoice.note, note))
    )
    if await lookup is not None:
        existing["invoices"] += 1
        return
    total = sum(line.amount for line in lines)
    insurance = _insurance(patient, total)
    when = appointment.end_at if appointment else utcnow() - timedelta(days=2)
    paid = (
        int((total - insurance) * paid_ratio) // 500 * 500 if paid_ratio < 1 else total - insurance
    )
    invoice = await Invoice(
        number=await next_number(INVOICE_SEQUENCE, "FAC"),
        patient_id=patient.id,
        lines=lines,
        total=total,
        insurance_share=insurance,
        patient_share=total - insurance,
        paid_amount=paid,
        status=status,
        appointment_id=appointment.id if appointment else None,
        note=note,
        created_by=secretary.id,
    ).insert()
    changes = {"createdAt": when, "updatedAt": when}
    if status != InvoiceStatus.DRAFT:
        changes["issuedAt"] = when
    if status == InvoiceStatus.CANCELLED:
        changes |= {
            "cancelledAt": when + timedelta(hours=1),
            "cancelledBy": secretary.id,
            "cancelReason": "Facture saisie en double",
        }
    await invoice.set(changes)
    created["invoices"] += 1
    if paid:
        payment = await Payment(
            invoice_id=invoice.id,
            patient_id=patient.id,
            amount=paid,
            method=method,
            receipt_number=await next_number(RECEIPT_SEQUENCE, "REC"),
            created_by=secretary.id,
        ).insert()
        await payment.set({"createdAt": when + timedelta(minutes=10)})
        created["payments"] += 1


async def seed_invoices(
    index: int,
    patient: Patient,
    visits: list[Appointment],
    users: dict[str, User],
    secretary: User,
    created: Counter,
    existing: Counter,
) -> None:
    cardiologist = users[CARDIOLOGIST].id
    plan = (
        (InvoiceStatus.PAID, 1.0),
        (InvoiceStatus.PARTIAL, 0.5) if index % 2 == 0 else (InvoiceStatus.PAID, 1.0),
        (InvoiceStatus.ISSUED, 0.0),
    )
    ordered = sorted(visits, key=lambda appointment: appointment.start_at)
    for number, (appointment, (status, ratio)) in enumerate(zip(ordered, plan, strict=False)):
        lines = _lines(appointment, appointment.doctor_id == cardiologist)
        total = sum(line.amount for line in lines)
        if status == InvoiceStatus.PARTIAL and _insurance(patient, total) == total:
            status, ratio = InvoiceStatus.PAID, 1.0  # nothing left for the patient to pay
        await _invoice(
            patient,
            lines,
            status,
            secretary,
            appointment=appointment,
            note=None,
            paid_ratio=ratio,
            method=METHODS[(index + number) % len(METHODS)],
            created=created,
            existing=existing,
        )
    if index % 3 == 0:
        certificate = [InvoiceLine(label="Certificat médical", quantity=1, unit_price=20_000)]
        await _invoice(
            patient,
            certificate,
            InvoiceStatus.DRAFT,
            secretary,
            appointment=None,
            note="Certificat médical à facturer",
            paid_ratio=0.0,
            method=PaymentMethod.CASH,
            created=created,
            existing=existing,
        )
        await _invoice(
            patient,
            certificate,
            InvoiceStatus.CANCELLED,
            secretary,
            appointment=None,
            note="Certificat médical (doublon)",
            paid_ratio=0.0,
            method=PaymentMethod.CASH,
            created=created,
            existing=existing,
        )
