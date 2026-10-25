"""/api/billing: invoices, payments, refunds, PDFs and revenue reports (amounts in millimes)."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status

from app.dependencies import require_roles
from app.modules.auth.models import User
from app.modules.billing.models import InvoiceStatus
from app.modules.billing.schemas import (
    CancelRequest,
    InvoiceCreate,
    InvoiceOut,
    InvoicePage,
    InvoiceUpdate,
    PaymentCreate,
    RefundCreate,
    RevenueReport,
    UnpaidReport,
)
from app.modules.billing.service import BILLING_ROLES, BillingService
from app.modules.patients.dates import clinic_today

router = APIRouter()
PREFIX = "/api/billing"
TAGS = ["billing"]
LLM_ENABLED = False

managers = require_roles(*BILLING_ROLES["manage"])
readers = require_roles(*BILLING_ROLES["read"])


def get_billing_service() -> BillingService:
    return BillingService()


def _pdf(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


# ── Invoices ──────────────────────────────────────────────────────────────────


@router.get("/invoices", response_model=InvoicePage)
async def list_invoices(
    patient_id: str | None = Query(default=None, alias="patientId"),
    status_filter: InvoiceStatus | None = Query(default=None, alias="status"),
    number: str | None = Query(default=None, max_length=20),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(readers),
    service: BillingService = Depends(get_billing_service),
) -> InvoicePage:
    """Newest first. A PATIENT only ever gets their own invoices."""
    return await service.list(
        user, patient_id=patient_id, status=status_filter, number=number, page=page, size=size
    )


@router.post("/invoices", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    data: InvoiceCreate,
    user: User = Depends(managers),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceOut:
    """New DRAFT; total and patient share are computed from the lines."""
    return await service.create(user, data)


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
async def get_invoice(
    invoice_id: str,
    user: User = Depends(readers),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceOut:
    return await service.get(user, invoice_id)


@router.patch("/invoices/{invoice_id}", response_model=InvoiceOut)
async def update_invoice(
    invoice_id: str,
    data: InvoiceUpdate,
    user: User = Depends(managers),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceOut:
    return await service.update(user, invoice_id, data)


@router.post("/invoices/{invoice_id}/issue", response_model=InvoiceOut)
async def issue_invoice(
    invoice_id: str,
    user: User = Depends(managers),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceOut:
    """DRAFT -> ISSUED (PAID at once when the insurance pays everything)."""
    return await service.issue(user, invoice_id)


@router.post("/invoices/{invoice_id}/cancel", response_model=InvoiceOut)
async def cancel_invoice(
    invoice_id: str,
    data: CancelRequest,
    user: User = Depends(managers),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceOut:
    """Only while nothing is paid; the reason is kept."""
    return await service.cancel(user, invoice_id, data)


@router.post(
    "/invoices/{invoice_id}/payments",
    response_model=InvoiceOut,
    status_code=status.HTTP_201_CREATED,
)
async def pay_invoice(
    invoice_id: str,
    data: PaymentCreate,
    user: User = Depends(managers),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceOut:
    """Partial payments allowed; more than the balance is a 409."""
    return await service.pay(user, invoice_id, data)


@router.post(
    "/payments/{payment_id}/refund", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED
)
async def refund_payment(
    payment_id: str,
    data: RefundCreate,
    user: User = Depends(managers),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceOut:
    return await service.refund(user, payment_id, data)


# ── PDF ───────────────────────────────────────────────────────────────────────


@router.get("/invoices/{invoice_id}/pdf", responses={200: {"content": {"application/pdf": {}}}})
async def invoice_pdf(
    invoice_id: str,
    user: User = Depends(readers),
    service: BillingService = Depends(get_billing_service),
) -> Response:
    return _pdf(*await service.invoice_pdf(user, invoice_id))


@router.get("/payments/{payment_id}/pdf", responses={200: {"content": {"application/pdf": {}}}})
async def receipt_pdf(
    payment_id: str,
    user: User = Depends(readers),
    service: BillingService = Depends(get_billing_service),
) -> Response:
    return _pdf(*await service.receipt_pdf(user, payment_id))


# ── Reports ───────────────────────────────────────────────────────────────────


@router.get("/reports/revenue", response_model=RevenueReport, response_model_by_alias=True)
async def revenue(
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    group_by: Literal["day", "month"] = Query(default="day", alias="groupBy"),
    _: User = Depends(managers),
    service: BillingService = Depends(get_billing_service),
) -> RevenueReport:
    """Money received (refunds deducted) per day or month, in clinic time. Default: this month."""
    today = clinic_today()
    return await service.revenue(date_from or today.replace(day=1), date_to or today, group_by)


@router.get("/reports/unpaid", response_model=UnpaidReport)
async def unpaid(
    _: User = Depends(managers),
    service: BillingService = Depends(get_billing_service),
) -> UnpaidReport:
    """Issued invoices with something left to pay, oldest first."""
    return await service.unpaid()
