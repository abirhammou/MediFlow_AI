"""Billing: invoices (DRAFT -> ISSUED -> PARTIAL -> PAID, or CANCELLED), payments, refunds.

Nothing is ever deleted or edited after the fact: a mistake on an issued invoice is
a cancellation (with a reason, only while nothing is paid), a payment mistake is a
refund (a negative payment). `invoices.paidAmount` is changed by one conditional
update per payment / refund, so two concurrent payments can never overpay an
invoice even without transactions (MongoDB is standalone).
"""

import asyncio
import re
from datetime import date, datetime, time, timedelta
from typing import Any

from beanie import PydanticObjectId
from beanie.operators import In
from bson.errors import InvalidId
from pymongo import ReturnDocument

from app.core.sequence import INVOICE_SEQUENCE, RECEIPT_SEQUENCE, next_number
from app.core.time import utcnow
from app.errors import APIError
from app.modules.appointments.models import Appointment
from app.modules.auth.models import Role, User
from app.modules.auth.repository import get_user_names
from app.modules.billing.models import (
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    Payment,
    PaymentMethod,
    format_tnd,
)
from app.modules.billing.pdf import build_invoice_pdf, build_receipt_pdf
from app.modules.billing.schemas import (
    CancelRequest,
    InvoiceCreate,
    InvoiceLineIn,
    InvoiceLineOut,
    InvoiceOut,
    InvoicePage,
    InvoiceUpdate,
    PaymentCreate,
    PaymentOut,
    RefundCreate,
    RevenueReport,
    RevenueRow,
    UnpaidReport,
)
from app.modules.followup.models import FollowupTask
from app.modules.patients import repository as patients
from app.modules.patients.dates import CLINIC_TZ
from app.modules.patients.models import Patient

# Who may do what (the frontend mirrors it in billing-permissions).
BILLING_ROLES: dict[str, tuple[Role, ...]] = {
    "manage": (Role.ADMIN, Role.SECRETARY),
    "read": (Role.ADMIN, Role.SECRETARY, Role.PATIENT),  # PATIENT: own invoices only
}
PAYABLE = [InvoiceStatus.ISSUED.value, InvoiceStatus.PARTIAL.value, InvoiceStatus.PAID.value]
MAX_REPORT_DAYS = 366
UNPAID_LIMIT = 200
CLINIC_OFFSET = "+01:00"  # CLINIC_TZ for MongoDB date operators


def _oid(value: str | None, code: str, detail: str, status: int = 404) -> PydanticObjectId:
    try:
        return PydanticObjectId(value)
    except (InvalidId, TypeError):
        raise APIError(status, code, detail) from None


def _invoice_not_found() -> APIError:
    return APIError(404, "invoice_not_found", "Facture introuvable.")


def _payment_not_found() -> APIError:
    return APIError(404, "payment_not_found", "Paiement introuvable.")


def _lines(lines: list[InvoiceLineIn]) -> list[InvoiceLine]:
    return [
        InvoiceLine(label=line.label, quantity=line.quantity, unit_price=line.unit_price)
        for line in lines
    ]


def _totals(lines: list[InvoiceLine], insurance_share: int) -> dict[str, int]:
    total = sum(line.amount for line in lines)
    if insurance_share > total:
        raise APIError(
            422, "insurance_share_too_high", "La part assurance dépasse le total de la facture."
        )
    return {
        "total": total,
        "insurance_share": insurance_share,
        "patient_share": total - insurance_share,
    }


def _status_after(paid_field: str = "$paidAmount") -> dict[str, Any]:
    """Status from the (new) paid amount, inside an update pipeline."""
    return {
        "$cond": [
            {"$gte": [paid_field, "$patientShare"]},
            InvoiceStatus.PAID.value,
            {
                "$cond": [
                    {"$gt": [paid_field, 0]},
                    InvoiceStatus.PARTIAL.value,
                    InvoiceStatus.ISSUED.value,
                ]
            },
        ]
    }


async def _add_paid(
    invoice_id: PydanticObjectId, delta: int, guard: dict[str, Any]
) -> Invoice | None:
    """paidAmount += delta and status recomputed, only if `guard` still matches (atomic)."""
    document = await Invoice.get_pymongo_collection().find_one_and_update(
        {"_id": invoice_id, **guard},
        [
            {"$set": {"paidAmount": {"$add": ["$paidAmount", delta]}, "updatedAt": utcnow()}},
            {"$set": {"status": _status_after()}},
        ],
        return_document=ReturnDocument.AFTER,
    )
    return Invoice.model_validate(document) if document else None


class BillingService:
    # ── Access ────────────────────────────────────────────────────────────────

    @staticmethod
    def _can_read(
        user: User, patient_id: PydanticObjectId, status: InvoiceStatus | None = None
    ) -> bool:
        """A PATIENT reads their own invoices once issued (never a DRAFT)."""
        if user.role in BILLING_ROLES["manage"]:
            return True
        return (
            user.role == Role.PATIENT
            and user.patient_id == patient_id
            and status != InvoiceStatus.DRAFT
        )

    async def _invoice(self, user: User, invoice_id: str) -> Invoice:
        invoice = await Invoice.get(_oid(invoice_id, "invoice_not_found", "Facture introuvable."))
        if invoice is None or not self._can_read(user, invoice.patient_id, invoice.status):
            raise _invoice_not_found()  # another patient's invoice: same answer as missing
        return invoice

    async def _payment(self, user: User, payment_id: str) -> Payment:
        payment = await Payment.get(_oid(payment_id, "payment_not_found", "Paiement introuvable."))
        if payment is None or not self._can_read(user, payment.patient_id):
            raise _payment_not_found()
        return payment

    # ── Output ────────────────────────────────────────────────────────────────

    async def _patients(self, ids: set[PydanticObjectId]) -> dict[PydanticObjectId, Patient]:
        if not ids:
            return {}
        found = await Patient.find(In(Patient.id, list(ids))).to_list()  # deleted ones too
        return {p.id: p for p in found if p.id}

    @staticmethod
    def _payment_out(payment: Payment, names: dict, numbers: dict | None = None) -> PaymentOut:
        refundable = payment.amount - payment.refunded_amount if payment.amount > 0 else 0
        return PaymentOut(
            id=str(payment.id),
            invoice_id=str(payment.invoice_id),
            invoice_number=(numbers or {}).get(payment.invoice_id),
            amount=payment.amount,
            method=payment.method,
            receipt_number=payment.receipt_number,
            refund_of=str(payment.refund_of) if payment.refund_of else None,
            refunded_amount=payment.refunded_amount,
            refundable=refundable,
            note=payment.note,
            created_by_name=names.get(payment.created_by) if payment.created_by else None,
            created_at=payment.created_at,
        )

    async def _out(
        self, invoices: list[Invoice], *, with_payments: bool = False
    ) -> list[InvoiceOut]:
        people = await self._patients({i.patient_id for i in invoices})
        payments: dict[PydanticObjectId, list[Payment]] = {}
        names: dict = {}
        if with_payments:
            found = (
                await Payment.find(In(Payment.invoice_id, [i.id for i in invoices]))
                .sort([("createdAt", 1)])
                .to_list()
            )
            for payment in found:
                payments.setdefault(payment.invoice_id, []).append(payment)
            names = await get_user_names({p.created_by for p in found if p.created_by})
        result = []
        for invoice in invoices:
            patient = people.get(invoice.patient_id)
            numbers = {invoice.id: invoice.number}
            result.append(
                InvoiceOut(
                    id=str(invoice.id),
                    number=invoice.number,
                    patient_id=str(invoice.patient_id),
                    patient_name=f"{patient.first_name} {patient.last_name}" if patient else None,
                    record_number=patient.record_number if patient else None,
                    lines=[
                        InvoiceLineOut(
                            label=line.label,
                            quantity=line.quantity,
                            unit_price=line.unit_price,
                            amount=line.amount,
                        )
                        for line in invoice.lines
                    ],
                    total=invoice.total,
                    insurance_share=invoice.insurance_share,
                    patient_share=invoice.patient_share,
                    paid_amount=invoice.paid_amount,
                    balance=invoice.balance,
                    status=invoice.status,
                    appointment_id=str(invoice.appointment_id) if invoice.appointment_id else None,
                    followup_task_id=str(invoice.followup_task_id)
                    if invoice.followup_task_id
                    else None,
                    note=invoice.note,
                    issued_at=invoice.issued_at,
                    cancelled_at=invoice.cancelled_at,
                    cancel_reason=invoice.cancel_reason,
                    created_at=invoice.created_at,
                    updated_at=invoice.updated_at,
                    payments=[
                        self._payment_out(p, names, numbers) for p in payments.get(invoice.id, [])
                    ],
                )
            )
        return result

    async def _one(self, invoice: Invoice) -> InvoiceOut:
        return (await self._out([invoice], with_payments=True))[0]

    # ── Links ─────────────────────────────────────────────────────────────────

    async def _links(
        self, patient_id: PydanticObjectId, appointment_id: str | None, task_id: str | None
    ) -> dict[str, PydanticObjectId | None]:
        links: dict[str, PydanticObjectId | None] = {}
        if appointment_id is not None:
            oid = _oid(appointment_id, "invalid_appointment", "Rendez-vous invalide.", 422)
            appointment = await Appointment.get(oid)
            if appointment is None or appointment.patient_id != patient_id:
                raise APIError(
                    422, "invalid_appointment", "Ce rendez-vous n'est pas celui du patient."
                )
            links["appointment_id"] = oid
        if task_id is not None:
            oid = _oid(task_id, "invalid_followup_task", "Tâche de suivi invalide.", 422)
            task = await FollowupTask.get(oid)
            if task is None or (task.patient_id is not None and task.patient_id != patient_id):
                raise APIError(
                    422, "invalid_followup_task", "Cette tâche de suivi n'est pas celle du patient."
                )
            links["followup_task_id"] = oid
        return links

    # ── Invoices ──────────────────────────────────────────────────────────────

    async def list(
        self,
        user: User,
        *,
        patient_id: str | None,
        status: InvoiceStatus | None,
        number: str | None,
        page: int,
        size: int,
    ) -> InvoicePage:
        query: dict[str, Any] = {}
        if user.role == Role.PATIENT:
            if user.patient_id is None:
                return InvoicePage(items=[], total=0, page=page, size=size)
            query["patientId"] = user.patient_id  # never chosen by the patient
            query["status"] = {"$ne": InvoiceStatus.DRAFT.value}
        elif patient_id:
            query["patientId"] = _oid(
                patient_id, "invalid_patient_id", "Identifiant patient invalide.", 422
            )
        if status is not None and not (user.role == Role.PATIENT and status == InvoiceStatus.DRAFT):
            query["status"] = status.value
        if number and number.strip():
            query["number"] = {"$regex": "^" + re.escape(number.strip().upper())}
        finder = Invoice.find(query)
        total = await finder.count()
        items = (
            await finder.sort([("createdAt", -1), ("_id", -1)])
            .skip((page - 1) * size)
            .limit(size)
            .to_list()
        )
        return InvoicePage(items=await self._out(items), total=total, page=page, size=size)

    async def get(self, user: User, invoice_id: str) -> InvoiceOut:
        return await self._one(await self._invoice(user, invoice_id))

    async def create(self, user: User, data: InvoiceCreate) -> InvoiceOut:
        pid = _oid(data.patient_id, "patient_not_found", "Dossier patient introuvable.")
        patient = await patients.get_patient(pid)
        if patient is None:
            raise APIError(404, "patient_not_found", "Dossier patient introuvable.")
        lines = _lines(data.lines)
        invoice = Invoice(
            number=await next_number(INVOICE_SEQUENCE, "FAC"),
            patient_id=pid,
            lines=lines,
            **_totals(lines, data.insurance_share),
            note=data.note,
            created_by=user.id,
            **await self._links(pid, data.appointment_id, data.followup_task_id),
        )
        await invoice.insert()
        return await self._one(invoice)

    async def update(self, user: User, invoice_id: str, data: InvoiceUpdate) -> InvoiceOut:
        invoice = await self._invoice(user, invoice_id)
        if invoice.status != InvoiceStatus.DRAFT:
            raise APIError(
                409, "invoice_locked", "Seule une facture en brouillon peut être modifiée."
            )
        fields = data.model_fields_set
        lines = _lines(data.lines) if data.lines is not None else invoice.lines
        share = (
            data.insurance_share if data.insurance_share is not None else invoice.insurance_share
        )
        changes: dict[str, Any] = {
            "lines": [line.model_dump(by_alias=True) for line in lines],
            **{_camel(k): v for k, v in _totals(lines, share).items()},
            "updatedAt": utcnow(),
        }
        if "note" in fields:
            changes["note"] = data.note
        links = await self._links(
            invoice.patient_id,
            data.appointment_id if "appointment_id" in fields else None,
            data.followup_task_id if "followup_task_id" in fields else None,
        )
        changes.update({_camel(k): v for k, v in links.items()})
        updated = await Invoice.get_pymongo_collection().find_one_and_update(
            {"_id": invoice.id, "status": InvoiceStatus.DRAFT.value},
            {"$set": changes},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            raise APIError(
                409, "invoice_locked", "Seule une facture en brouillon peut être modifiée."
            )
        return await self._one(Invoice.model_validate(updated))

    async def issue(self, user: User, invoice_id: str) -> InvoiceOut:
        invoice = await self._invoice(user, invoice_id)
        status = InvoiceStatus.PAID if invoice.patient_share == 0 else InvoiceStatus.ISSUED
        updated = await Invoice.get_pymongo_collection().find_one_and_update(
            {"_id": invoice.id, "status": InvoiceStatus.DRAFT.value},
            {"$set": {"status": status.value, "issuedAt": utcnow(), "updatedAt": utcnow()}},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            raise APIError(409, "invoice_not_draft", "Cette facture a déjà été émise.")
        return await self._one(Invoice.model_validate(updated))

    async def cancel(self, user: User, invoice_id: str, data: CancelRequest) -> InvoiceOut:
        invoice = await self._invoice(user, invoice_id)
        updated = await Invoice.get_pymongo_collection().find_one_and_update(
            {
                "_id": invoice.id,
                "status": {"$in": [InvoiceStatus.DRAFT.value, InvoiceStatus.ISSUED.value]},
                "paidAmount": 0,
            },
            {
                "$set": {
                    "status": InvoiceStatus.CANCELLED.value,
                    "cancelledAt": utcnow(),
                    "cancelledBy": user.id,
                    "cancelReason": data.reason,
                    "updatedAt": utcnow(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            if invoice.status == InvoiceStatus.CANCELLED:
                raise APIError(409, "invoice_cancelled", "Cette facture est déjà annulée.")
            raise APIError(
                409,
                "invoice_has_payments",
                "Une facture avec des paiements ne peut pas être annulée : remboursez-les d'abord.",
            )
        return await self._one(Invoice.model_validate(updated))

    # ── Payments ──────────────────────────────────────────────────────────────

    async def pay(self, user: User, invoice_id: str, data: PaymentCreate) -> InvoiceOut:
        invoice = await self._invoice(user, invoice_id)
        guard = {
            "status": {"$in": [InvoiceStatus.ISSUED.value, InvoiceStatus.PARTIAL.value]},
            "$expr": {"$lte": [{"$add": ["$paidAmount", data.amount]}, "$patientShare"]},
        }
        updated = await _add_paid(invoice.id, data.amount, guard)  # type: ignore[arg-type]
        if updated is None:
            current = await Invoice.get(invoice.id)
            if current is None or current.status not in (
                InvoiceStatus.ISSUED,
                InvoiceStatus.PARTIAL,
            ):
                raise APIError(
                    409,
                    "invoice_not_payable",
                    "Seule une facture émise et non soldée peut être réglée.",
                )
            raise APIError(
                409,
                "overpayment",
                f"Le montant dépasse le reste à payer ({format_tnd(current.balance)}).",
            )
        payment = Payment(
            invoice_id=updated.id,  # type: ignore[arg-type]
            patient_id=updated.patient_id,
            amount=data.amount,
            method=data.method,
            receipt_number=await next_number(RECEIPT_SEQUENCE, "REC"),
            note=data.note,
            created_by=user.id,
        )
        try:
            await payment.insert()
        except Exception:
            await _add_paid(updated.id, -data.amount, {})  # type: ignore[arg-type]
            raise
        return await self._one(updated)

    async def refund(self, user: User, payment_id: str, data: RefundCreate) -> InvoiceOut:
        original = await self._payment(user, payment_id)
        if original.amount <= 0:
            raise APIError(409, "not_refundable", "Un remboursement ne peut pas être remboursé.")
        remaining = original.amount - original.refunded_amount
        amount = data.amount if data.amount is not None else remaining
        if amount <= 0 or amount > remaining:
            raise APIError(
                409,
                "refund_too_high",
                f"Remboursement possible : {format_tnd(max(remaining, 0))} au plus.",
            )
        # 1. reserve the amount on the original payment (atomic)
        reserved = await Payment.get_pymongo_collection().find_one_and_update(
            {
                "_id": original.id,
                "$expr": {"$lte": [{"$add": ["$refundedAmount", amount]}, "$amount"]},
            },
            {"$inc": {"refundedAmount": amount}},
        )
        if reserved is None:
            raise APIError(409, "refund_too_high", "Ce paiement a déjà été remboursé entre-temps.")
        # 2. lower the invoice's paid amount
        updated = await _add_paid(
            original.invoice_id,
            -amount,
            {"status": {"$in": PAYABLE}, "paidAmount": {"$gte": amount}},
        )
        if updated is None:
            await Payment.get_pymongo_collection().update_one(
                {"_id": original.id}, {"$inc": {"refundedAmount": -amount}}
            )
            raise APIError(409, "not_refundable", "Cette facture ne peut plus être remboursée.")
        # 3. the refund itself, with its own receipt
        await Payment(
            invoice_id=original.invoice_id,
            patient_id=original.patient_id,
            amount=-amount,
            method=original.method,
            receipt_number=await next_number(RECEIPT_SEQUENCE, "REC"),
            refund_of=original.id,
            note=data.note,
            created_by=user.id,
        ).insert()
        return await self._one(updated)

    # ── PDF ───────────────────────────────────────────────────────────────────

    async def invoice_pdf(self, user: User, invoice_id: str) -> tuple[bytes, str]:
        invoice = await self._invoice(user, invoice_id)
        out = await self._one(invoice)
        pdf = await asyncio.to_thread(build_invoice_pdf, out)
        return pdf, f"facture-{invoice.number}.pdf"

    async def receipt_pdf(self, user: User, payment_id: str) -> tuple[bytes, str]:
        payment = await self._payment(user, payment_id)
        invoice = await Invoice.get(payment.invoice_id)
        if invoice is None:
            raise _payment_not_found()
        out = await self._one(invoice)
        names = await get_user_names({payment.created_by} if payment.created_by else set())
        receipt = self._payment_out(payment, names, {invoice.id: invoice.number})
        pdf = await asyncio.to_thread(build_receipt_pdf, receipt, out)
        return pdf, f"recu-{payment.receipt_number}.pdf"

    # ── Reports ───────────────────────────────────────────────────────────────

    async def revenue(self, date_from: date, date_to: date, group_by: str) -> RevenueReport:
        if date_to < date_from:
            raise APIError(422, "invalid_period", "La date de fin précède la date de début.")
        if (date_to - date_from).days > MAX_REPORT_DAYS:
            raise APIError(422, "invalid_period", "La période est limitée à un an.")
        start = datetime.combine(date_from, time.min, CLINIC_TZ)
        end = datetime.combine(date_to + timedelta(days=1), time.min, CLINIC_TZ)
        fmt = "%Y-%m" if group_by == "month" else "%Y-%m-%d"
        pipeline = [
            {"$match": {"createdAt": {"$gte": start, "$lt": end}}},
            {
                "$group": {
                    "_id": {
                        "period": {
                            "$dateToString": {
                                "format": fmt,
                                "date": "$createdAt",
                                "timezone": CLINIC_OFFSET,
                            }
                        },
                        "method": "$method",
                    },
                    "collected": {"$sum": {"$cond": [{"$gt": ["$amount", 0]}, "$amount", 0]}},
                    "refunded": {
                        "$sum": {
                            "$cond": [{"$lt": ["$amount", 0]}, {"$multiply": ["$amount", -1]}, 0]
                        }
                    },
                    "count": {"$sum": 1},
                }
            },
        ]
        rows: dict[str, RevenueRow] = {}
        cursor = await Payment.get_pymongo_collection().aggregate(pipeline)
        async for group in cursor:
            period = group["_id"]["period"]
            row = rows.setdefault(
                period,
                RevenueRow(period=period, payments=0, collected=0, refunded=0, net=0, by_method={}),
            )
            method = PaymentMethod(group["_id"]["method"])
            row.payments += group["count"]
            row.collected += group["collected"]
            row.refunded += group["refunded"]
            row.net = row.collected - row.refunded
            row.by_method[method] = (
                row.by_method.get(method, 0) + group["collected"] - group["refunded"]
            )
        ordered = [rows[key] for key in sorted(rows)]
        collected = sum(r.collected for r in ordered)
        refunded = sum(r.refunded for r in ordered)
        return RevenueReport(
            date_from=date_from,
            date_to=date_to,
            group_by=group_by,
            rows=ordered,
            collected=collected,
            refunded=refunded,
            net=collected - refunded,
        )

    async def unpaid(self) -> UnpaidReport:
        query = {"status": {"$in": [InvoiceStatus.ISSUED.value, InvoiceStatus.PARTIAL.value]}}
        invoices = await Invoice.find(query).sort([("issuedAt", 1)]).limit(UNPAID_LIMIT).to_list()
        outstanding = await Invoice.get_pymongo_collection().aggregate(
            [
                {"$match": query},
                {
                    "$group": {
                        "_id": None,
                        "sum": {"$sum": {"$subtract": ["$patientShare", "$paidAmount"]}},
                        "n": {"$sum": 1},
                    }
                },
            ]
        )
        totals = await outstanding.to_list(1)
        return UnpaidReport(
            items=await self._out(invoices),
            count=totals[0]["n"] if totals else 0,
            outstanding=totals[0]["sum"] if totals else 0,
        )


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)
