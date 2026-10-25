"""Invoices and payments. Every amount is an integer in millimes (1 TND = 1000 millimes)."""

from enum import Enum

from beanie import PydanticObjectId
from pydantic import AwareDatetime, Field

from app.core.models import CamelModel, CreatedAtDocument, TimestampedDocument

INVOICE_NUMBER_PATTERN = r"^FAC-[0-9]{4}-[0-9]{5}$"
RECEIPT_NUMBER_PATTERN = r"^REC-[0-9]{4}-[0-9]{5}$"
MAX_UNIT_PRICE = 100_000_000  # 100 000 TND


class InvoiceStatus(str, Enum):
    DRAFT = "DRAFT"  # lines still editable
    ISSUED = "ISSUED"  # sent to the patient, nothing paid yet
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class PaymentMethod(str, Enum):
    CASH = "CASH"
    CARD = "CARD"
    TRANSFER = "TRANSFER"
    CHEQUE = "CHEQUE"


class InvoiceLine(CamelModel):
    label: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, le=1000)
    unit_price: int = Field(ge=0, le=MAX_UNIT_PRICE)

    @property
    def amount(self) -> int:
        return self.quantity * self.unit_price


class Invoice(TimestampedDocument):
    number: str = Field(pattern=INVOICE_NUMBER_PATTERN)
    patient_id: PydanticObjectId
    lines: list[InvoiceLine] = Field(min_length=1, max_length=50)
    total: int = Field(ge=0)
    insurance_share: int = Field(default=0, ge=0)
    patient_share: int = Field(ge=0, description="total - insurance_share")
    paid_amount: int = Field(default=0, ge=0, description="net of refunds")
    status: InvoiceStatus = InvoiceStatus.DRAFT
    appointment_id: PydanticObjectId | None = None
    followup_task_id: PydanticObjectId | None = None
    note: str | None = Field(default=None, max_length=500)
    issued_at: AwareDatetime | None = None
    cancelled_at: AwareDatetime | None = None
    cancelled_by: PydanticObjectId | None = None
    cancel_reason: str | None = Field(default=None, max_length=500)
    created_by: PydanticObjectId | None = None

    @property
    def balance(self) -> int:
        return (
            0 if self.status == InvoiceStatus.CANCELLED else self.patient_share - self.paid_amount
        )

    class Settings:
        name = "invoices"


class Payment(CreatedAtDocument):
    """Append-only: a refund is a new, negative payment with `refund_of` set."""

    invoice_id: PydanticObjectId
    patient_id: PydanticObjectId
    amount: int
    method: PaymentMethod
    receipt_number: str = Field(pattern=RECEIPT_NUMBER_PATTERN)
    refund_of: PydanticObjectId | None = None
    refunded_amount: int = Field(default=0, ge=0)
    note: str | None = Field(default=None, max_length=500)
    created_by: PydanticObjectId | None = None

    class Settings:
        name = "payments"


def format_tnd(millimes: int) -> str:
    """45500 -> "45,500 TND"; 1234500 -> "1 234,500 TND" (French style, 3 decimals)."""
    sign = "-" if millimes < 0 else ""
    dinars, rest = divmod(abs(millimes), 1000)
    return f"{sign}{dinars:,}".replace(",", " ") + f",{rest:03d} TND"
