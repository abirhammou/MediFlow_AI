"""API schemas of billing (camelCase). Amounts are integers in millimes."""

from datetime import date, datetime
from typing import Annotated

from pydantic import Field

from app.modules.billing.models import MAX_UNIT_PRICE, InvoiceStatus, PaymentMethod
from app.modules.patients.schemas import Clean, InputModel, OutputModel, _max_length

Note = Annotated[str | None, Clean, _max_length(500)]
Millimes = Annotated[int, Field(ge=0, le=MAX_UNIT_PRICE * 1000)]


class InvoiceLineIn(InputModel):
    label: Annotated[str, Clean, _max_length(200)]
    quantity: Annotated[int, Field(ge=1, le=1000)] = 1
    unit_price: Annotated[int, Field(ge=0, le=MAX_UNIT_PRICE)]


class InvoiceCreate(InputModel):
    patient_id: str
    lines: list[InvoiceLineIn] = Field(min_length=1, max_length=50)
    insurance_share: Millimes = 0
    appointment_id: str | None = None
    followup_task_id: str | None = None
    note: Note = None


class InvoiceUpdate(InputModel):
    """DRAFT only; a missing field stays unchanged."""

    lines: list[InvoiceLineIn] | None = Field(default=None, min_length=1, max_length=50)
    insurance_share: Millimes | None = None
    appointment_id: str | None = None
    followup_task_id: str | None = None
    note: Note = None


class CancelRequest(InputModel):
    reason: Annotated[str, Clean, _max_length(500)]


class PaymentCreate(InputModel):
    amount: Annotated[int, Field(gt=0, le=MAX_UNIT_PRICE * 1000)]
    method: PaymentMethod
    note: Note = None


class RefundCreate(InputModel):
    """Without `amount`, everything still refundable on that payment."""

    amount: Annotated[int, Field(gt=0, le=MAX_UNIT_PRICE * 1000)] | None = None
    note: Note = None


class InvoiceLineOut(OutputModel):
    label: str
    quantity: int
    unit_price: int
    amount: int


class PaymentOut(OutputModel):
    id: str
    invoice_id: str
    invoice_number: str | None
    amount: int
    method: PaymentMethod
    receipt_number: str
    refund_of: str | None
    refunded_amount: int
    refundable: int
    note: str | None
    created_by_name: str | None
    created_at: datetime


class InvoiceOut(OutputModel):
    id: str
    number: str
    patient_id: str
    patient_name: str | None
    record_number: str | None
    lines: list[InvoiceLineOut]
    total: int
    insurance_share: int
    patient_share: int
    paid_amount: int
    balance: int
    status: InvoiceStatus
    appointment_id: str | None
    followup_task_id: str | None
    note: str | None
    issued_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime
    payments: list[PaymentOut] = Field(default_factory=list, description="detail only")


class InvoicePage(OutputModel):
    items: list[InvoiceOut]
    total: int
    page: int
    size: int


class RevenueRow(OutputModel):
    period: str  # 2026-10-25 or 2026-10
    payments: int
    collected: int
    refunded: int
    net: int
    by_method: dict[PaymentMethod, int]


class RevenueReport(OutputModel):
    date_from: date = Field(serialization_alias="from")
    date_to: date = Field(serialization_alias="to")
    group_by: str
    rows: list[RevenueRow]
    collected: int
    refunded: int
    net: int


class UnpaidReport(OutputModel):
    items: list[InvoiceOut]
    count: int
    outstanding: int
