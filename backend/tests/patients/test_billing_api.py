"""Billing: totals, numbering, partial payments, overpayment, refunds, cancel, PDFs, reports, roles."""

import asyncio
import re

import pytest

from app.core.time import utcnow
from app.modules.auth.models import Role
from app.modules.billing.models import Invoice, Payment
from app.modules.patients.dates import clinic_today

CONSULTATION = {"label": "Consultation de médecine générale", "quantity": 1, "unitPrice": 45_000}
ECG = {"label": "ECG", "quantity": 2, "unitPrice": 12_500}


@pytest.fixture
async def patient(create_patient):
    return await create_patient()


@pytest.fixture
async def other_patient(create_patient):
    return await create_patient(firstName="Karim", lastName="Jaziri", nationalId="07654321")


@pytest.fixture
def billing(api_client, auth, secretary):
    """Small client: billing("post", "/invoices", json=...) as the secretary by default."""

    async def call(method: str, path: str, user=None, **kwargs):
        return await api_client.request(
            method.upper(), f"/api/billing{path}", headers=auth(user or secretary), **kwargs
        )

    return call


@pytest.fixture
def invoice(billing, patient):
    """An invoice of `patient` (ISSUED unless issue=False): its JSON."""

    async def create(*, lines=None, insurance=0, issue=True, patient_id=None):
        response = await billing(
            "post",
            "/invoices",
            json={
                "patientId": patient_id or patient["id"],
                "lines": lines or [CONSULTATION, ECG],
                "insuranceShare": insurance,
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        if issue:
            body = (await billing("post", f"/invoices/{body['id']}/issue")).json()
        return body

    return create


async def pay(billing, invoice_id, amount, method="CASH", user=None):
    return await billing(
        "post",
        f"/invoices/{invoice_id}/payments",
        user=user,
        json={"amount": amount, "method": method},
    )


# --- invoices -----------------------------------------------------------------


async def test_create_computes_totals_and_numbers(invoice, billing):
    first = await invoice(insurance=30_000, issue=False)
    second = await invoice(issue=False)

    assert first["status"] == "DRAFT"
    assert first["total"] == 70_000  # 45 000 + 2 x 12 500
    assert first["insuranceShare"] == 30_000 and first["patientShare"] == 40_000
    assert first["balance"] == 40_000 and first["paidAmount"] == 0
    assert [line["amount"] for line in first["lines"]] == [45_000, 25_000]
    assert first["patientName"] == "Leila Haddad" and first["recordNumber"].startswith("PAT-")
    year = utcnow().year
    assert re.fullmatch(rf"FAC-{year}-\d{{5}}", first["number"])
    assert int(second["number"][-5:]) == int(first["number"][-5:]) + 1


async def test_create_validation(billing, patient):
    too_much_insurance = await billing(
        "post",
        "/invoices",
        json={"patientId": patient["id"], "lines": [CONSULTATION], "insuranceShare": 50_000},
    )
    no_lines = await billing("post", "/invoices", json={"patientId": patient["id"], "lines": []})
    negative = await billing(
        "post",
        "/invoices",
        json={"patientId": patient["id"], "lines": [{**CONSULTATION, "unitPrice": -1}]},
    )
    unknown = await billing(
        "post", "/invoices", json={"patientId": "0" * 24, "lines": [CONSULTATION]}
    )

    assert too_much_insurance.status_code == 422
    assert too_much_insurance.json()["code"] == "insurance_share_too_high"
    assert no_lines.status_code == 422 and negative.status_code == 422
    assert unknown.status_code == 404


async def test_only_drafts_are_edited_and_issued_once(invoice, billing):
    draft = await invoice(issue=False)
    edited = await billing(
        "patch",
        f"/invoices/{draft['id']}",
        json={"lines": [CONSULTATION], "insuranceShare": 31_500},
    )
    issued = await billing("post", f"/invoices/{draft['id']}/issue")
    again = await billing("post", f"/invoices/{draft['id']}/issue")
    locked = await billing("patch", f"/invoices/{draft['id']}", json={"note": "x"})

    assert edited.json()["total"] == 45_000 and edited.json()["patientShare"] == 13_500
    assert issued.json()["status"] == "ISSUED" and issued.json()["issuedAt"]
    assert again.status_code == 409 and locked.status_code == 409


async def test_fully_insured_invoice_is_paid_when_issued(invoice):
    issued = await invoice(lines=[CONSULTATION], insurance=45_000)
    assert issued["status"] == "PAID" and issued["balance"] == 0


# --- payments -----------------------------------------------------------------


async def test_partial_then_full_payment(invoice, billing):
    issued = await invoice()  # 70 000 to pay

    partial = await pay(billing, issued["id"], 20_000, "CARD")
    full = await pay(billing, issued["id"], 50_000, "CHEQUE")

    assert partial.status_code == 201
    assert partial.json()["status"] == "PARTIAL" and partial.json()["balance"] == 50_000
    assert full.json()["status"] == "PAID" and full.json()["balance"] == 0
    receipts = [p["receiptNumber"] for p in full.json()["payments"]]
    assert len(receipts) == 2 and all(r.startswith("REC-") for r in receipts)
    assert full.json()["payments"][0]["createdByName"] == "Test User"


async def test_overpayment_and_unpayable_invoices(invoice, billing):
    issued = await invoice()
    draft = await invoice(issue=False)

    over = await pay(billing, issued["id"], 70_001)
    on_draft = await pay(billing, draft["id"], 1_000)
    await pay(billing, issued["id"], 70_000)
    on_paid = await pay(billing, issued["id"], 1)
    zero = await pay(billing, issued["id"], 0)

    assert over.status_code == 409 and over.json()["code"] == "overpayment"
    assert "70,000 TND" in over.json()["detail"]
    assert on_draft.status_code == 409 and on_paid.status_code == 409
    assert zero.status_code == 422


async def test_concurrent_payments_never_overpay(invoice, billing):
    issued = await invoice()  # 70 000

    results = await asyncio.gather(*(pay(billing, issued["id"], 40_000) for _ in range(3)))

    assert sorted(r.status_code for r in results) == [201, 409, 409]
    stored = await Invoice.get(issued["id"])
    assert stored.paid_amount == 40_000 and stored.status.value == "PARTIAL"
    assert await Payment.find({"invoiceId": stored.id}).count() == 1


# --- refunds and cancellation -------------------------------------------------


async def test_refunds(invoice, billing):
    issued = await invoice()
    paid = (await pay(billing, issued["id"], 70_000)).json()
    payment_id = paid["payments"][0]["id"]

    partial = await billing(
        "post", f"/payments/{payment_id}/refund", json={"amount": 20_000, "note": "Erreur"}
    )
    too_much = await billing("post", f"/payments/{payment_id}/refund", json={"amount": 60_000})
    rest = await billing("post", f"/payments/{payment_id}/refund", json={})
    nothing_left = await billing("post", f"/payments/{payment_id}/refund", json={})
    refund_id = rest.json()["payments"][-1]["id"]
    refund_of_refund = await billing("post", f"/payments/{refund_id}/refund", json={})

    assert partial.status_code == 201
    assert partial.json()["status"] == "PARTIAL" and partial.json()["balance"] == 20_000
    assert too_much.status_code == 409
    assert rest.json()["status"] == "ISSUED" and rest.json()["paidAmount"] == 0
    amounts = [p["amount"] for p in rest.json()["payments"]]
    assert amounts == [70_000, -20_000, -50_000]
    assert rest.json()["payments"][1]["refundOf"] == payment_id
    assert rest.json()["payments"][0]["refundable"] == 0
    assert nothing_left.status_code == 409 and refund_of_refund.status_code == 409


async def test_cancel_rules(invoice, billing):
    issued = await invoice()
    with_payment = await invoice()
    await pay(billing, with_payment["id"], 10_000)

    no_reason = await billing("post", f"/invoices/{issued['id']}/cancel", json={"reason": " "})
    cancelled = await billing(
        "post", f"/invoices/{issued['id']}/cancel", json={"reason": "Doublon"}
    )
    twice = await billing("post", f"/invoices/{issued['id']}/cancel", json={"reason": "Doublon"})
    blocked = await billing(
        "post", f"/invoices/{with_payment['id']}/cancel", json={"reason": "Erreur"}
    )
    pay_cancelled = await pay(billing, issued["id"], 1_000)

    assert no_reason.status_code == 422
    assert (
        cancelled.json()["status"] == "CANCELLED" and cancelled.json()["cancelReason"] == "Doublon"
    )
    assert cancelled.json()["balance"] == 0
    assert twice.status_code == 409
    assert blocked.status_code == 409 and blocked.json()["code"] == "invoice_has_payments"
    assert pay_cancelled.status_code == 409


# --- PDFs and reports ---------------------------------------------------------


async def test_invoice_and_receipt_pdfs(invoice, billing):
    issued = await invoice()
    paid = (await pay(billing, issued["id"], 20_000)).json()

    invoice_pdf = await billing("get", f"/invoices/{issued['id']}/pdf")
    receipt_pdf = await billing("get", f"/payments/{paid['payments'][0]['id']}/pdf")

    assert invoice_pdf.status_code == 200 and invoice_pdf.content.startswith(b"%PDF-")
    assert f"facture-{issued['number']}.pdf" in invoice_pdf.headers["content-disposition"]
    assert invoice_pdf.headers["cache-control"] == "no-store"
    assert receipt_pdf.status_code == 200 and receipt_pdf.content.startswith(b"%PDF-")


async def test_revenue_and_unpaid_reports(invoice, billing):
    first = await invoice()
    second = await invoice()
    await invoice(issue=False)  # drafts are not unpaid invoices
    paid = (await pay(billing, first["id"], 70_000, "CARD")).json()
    await pay(billing, second["id"], 10_000, "CASH")
    await billing("post", f"/payments/{paid['payments'][0]['id']}/refund", json={"amount": 5_000})

    revenue = (await billing("get", "/reports/revenue")).json()
    by_month = (await billing("get", "/reports/revenue", params={"groupBy": "month"})).json()
    unpaid = (await billing("get", "/reports/unpaid")).json()
    bad_period = await billing(
        "get", "/reports/revenue", params={"from": "2026-10-10", "to": "2026-10-01"}
    )

    today = clinic_today().isoformat()
    [row] = revenue["rows"]
    assert row["period"] == today and row["payments"] == 3
    assert (row["collected"], row["refunded"], row["net"]) == (80_000, 5_000, 75_000)
    assert row["byMethod"] == {"CARD": 65_000, "CASH": 10_000}
    assert revenue["net"] == 75_000 and revenue["from"] == today[:8] + "01"
    assert by_month["rows"][0]["period"] == today[:7]
    assert unpaid["count"] == 2 and unpaid["outstanding"] == 5_000 + 60_000
    assert {i["number"] for i in unpaid["items"]} == {first["number"], second["number"]}
    assert bad_period.status_code == 422


# --- roles --------------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.DOCTOR, Role.ADMIN_STAFF])
async def test_staff_without_billing_access(billing, invoice, user_factory, role):
    issued = await invoice()
    user = await user_factory(email=f"{role.value.lower()}@x.test", role=role)
    responses = [
        await billing("get", "/invoices", user=user),
        await billing("get", f"/invoices/{issued['id']}", user=user),
        await billing("get", f"/invoices/{issued['id']}/pdf", user=user),
        await billing("get", "/reports/unpaid", user=user),
        await pay(billing, issued["id"], 1_000, user=user),
    ]
    assert {r.status_code for r in responses} == {403}


async def test_admin_manages_billing(billing, invoice, admin):
    issued = await invoice()
    assert (await pay(billing, issued["id"], 1_000, user=admin)).status_code == 201
    assert (await billing("get", "/reports/revenue", user=admin)).status_code == 200


async def test_patient_reads_only_own_invoices(
    billing, invoice, user_factory, patient, other_patient
):
    mine = await invoice()
    paid = (await pay(billing, mine["id"], 10_000)).json()
    theirs = await invoice(patient_id=other_patient["id"])
    me = await user_factory(email="leila@x.test", role=Role.PATIENT, patient_id=patient["id"])

    listing = await billing("get", "/invoices", user=me, params={"patientId": other_patient["id"]})
    own = await billing("get", f"/invoices/{mine['id']}", user=me)
    own_receipt = await billing("get", f"/payments/{paid['payments'][0]['id']}/pdf", user=me)
    foreign = await billing("get", f"/invoices/{theirs['id']}", user=me)
    foreign_pdf = await billing("get", f"/invoices/{theirs['id']}/pdf", user=me)
    create = await billing(
        "post", "/invoices", user=me, json={"patientId": patient["id"], "lines": [CONSULTATION]}
    )
    self_pay = await pay(billing, mine["id"], 1_000, user=me)
    reports = await billing("get", "/reports/unpaid", user=me)

    assert [i["id"] for i in listing.json()["items"]] == [mine["id"]]  # patientId ignored
    assert own.status_code == 200 and own_receipt.status_code == 200
    assert foreign.status_code == 404 and foreign_pdf.status_code == 404
    assert create.status_code == 403 and self_pay.status_code == 403 and reports.status_code == 403


async def test_no_token_is_401(api_client):
    assert (await api_client.get("/api/billing/invoices")).status_code == 401
