import asyncio
import re
from datetime import UTC, date, datetime, timedelta

import pytest
from beanie import PydanticObjectId
from pymongo.errors import DuplicateKeyError

from app.core.models import AiReviewStatus
from app.core.sequence import next_record_number
from app.core.time import utcnow
from app.modules.appointments.models import Appointment, AppointmentStatus
from app.modules.appointments.repository import find_overlapping_appointment
from app.modules.faq.models import FaqEntry
from app.modules.faq.repository import list_approved_faq, search_approved_faq
from app.modules.patients.models import Gender, Patient, PatientSummary
from app.modules.patients.repository import (
    get_latest_summary,
    get_patient,
    get_validated_summary,
    list_patients,
)

NINE = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


async def make_patient(first_name: str, last_name: str, **fields) -> Patient:
    patient = Patient(
        record_number=await next_record_number(),
        first_name=first_name,
        last_name=last_name,
        date_of_birth=date(1980, 1, 1),
        gender=Gender.OTHER,
        **fields,
    )
    return await patient.insert()


# --- sequence ---------------------------------------------------------


async def test_concurrent_record_numbers_are_distinct(db):
    numbers = await asyncio.gather(*(next_record_number() for _ in range(20)))

    assert len(set(numbers)) == 20
    assert all(re.fullmatch(rf"PAT-{utcnow().year}-\d{{5}}", number) for number in numbers)
    sequence = sorted(int(number[-5:]) for number in numbers)
    assert sequence == list(range(sequence[0], sequence[0] + 20))


# --- patients ---------------------------------------------------------


async def test_soft_deleted_patient_is_excluded(db):
    kept = await make_patient("Leila", "Haddad")
    deleted = await make_patient("Omar", "Haddad", deleted_at=utcnow())

    page = await list_patients()

    assert [patient.id for patient in page.items] == [kept.id]
    assert page.total == 1
    assert await get_patient(kept.id) is not None
    assert await get_patient(deleted.id) is None


async def test_list_patients_is_sorted_and_paginated(db):
    for first_name, last_name in [("Nour", "Zouari"), ("Ali", "Amri"), ("Hela", "Masmoudi")]:
        await make_patient(first_name, last_name)

    first = await list_patients(page=1, page_size=2)
    second = await list_patients(page=2, page_size=2)

    assert [p.last_name for p in first.items] == ["Amri", "Masmoudi"]
    assert [p.last_name for p in second.items] == ["Zouari"]
    assert first.total == second.total == 3
    with pytest.raises(ValueError):
        await list_patients(page=0)


async def test_search_patients_by_name_and_record_number(db):
    meriem = await make_patient("Meriem", "Jaziri")
    await make_patient("Hatem", "Bouazizi")
    await make_patient("Meriem", "Deleted", deleted_at=utcnow())

    by_name = await list_patients(search="jaziri")
    by_first_name = await list_patients(search="Meriem")
    by_record = await list_patients(search=meriem.record_number.lower())

    assert [p.id for p in by_name.items] == [meriem.id]
    assert [p.id for p in by_first_name.items] == [meriem.id]
    assert [p.id for p in by_record.items] == [meriem.id]
    assert (await list_patients(search="Inconnu")).total == 0


# --- patient summaries ------------------------------------------------


async def test_second_validated_summary_is_rejected(db):
    patient_id = PydanticObjectId()
    await PatientSummary(
        patient_id=patient_id, content="Résumé validé.", status=AiReviewStatus.VALIDATED
    ).insert()

    with pytest.raises(DuplicateKeyError):
        await PatientSummary(
            patient_id=patient_id, content="Autre résumé.", status=AiReviewStatus.VALIDATED
        ).insert()
    # Drafts are unlimited, and another patient can have its own validated summary.
    await PatientSummary(patient_id=patient_id, content="Brouillon.").insert()
    await PatientSummary(
        patient_id=PydanticObjectId(), content="Résumé.", status=AiReviewStatus.VALIDATED
    ).insert()


async def test_latest_and_validated_summary(db):
    patient_id = PydanticObjectId()
    validated = await PatientSummary(
        patient_id=patient_id,
        content="Résumé validé.",
        status=AiReviewStatus.VALIDATED,
    ).insert()
    draft = await PatientSummary(patient_id=patient_id, content="Nouveau brouillon.").insert()

    assert (await get_latest_summary(patient_id)).id == draft.id
    assert (await get_validated_summary(patient_id)).id == validated.id
    assert await get_latest_summary(PydanticObjectId()) is None
    assert await get_validated_summary(PydanticObjectId()) is None


# --- appointments -----------------------------------------------------


async def test_overlap_check(db):
    doctor_id = PydanticObjectId()
    booked = await Appointment(
        patient_id=PydanticObjectId(),
        doctor_id=doctor_id,
        start_at=NINE,
        end_at=NINE + timedelta(minutes=30),
        status=AppointmentStatus.CONFIRMED,
    ).insert()
    await Appointment(
        patient_id=PydanticObjectId(),
        doctor_id=doctor_id,
        start_at=NINE + timedelta(hours=2),
        end_at=NINE + timedelta(hours=3),
        status=AppointmentStatus.CANCELLED,
    ).insert()

    def check(start_minutes: int, end_minutes: int, **kwargs):
        return find_overlapping_appointment(
            doctor_id,
            NINE + timedelta(minutes=start_minutes),
            NINE + timedelta(minutes=end_minutes),
            **kwargs,
        )

    assert (await check(15, 45)).id == booked.id  # partial overlap
    assert (await check(-15, 60)).id == booked.id  # contains the booked slot
    assert await check(30, 60) is None  # back-to-back
    assert await check(-30, 0) is None
    assert await check(120, 180) is None  # only a cancelled appointment there
    assert await check(15, 45, exclude_id=booked.id) is None  # rescheduling itself
    other_doctor = await find_overlapping_appointment(
        PydanticObjectId(), NINE, NINE + timedelta(minutes=30)
    )
    assert other_doctor is None


async def test_appointment_must_end_after_start():
    with pytest.raises(ValueError):
        Appointment(
            patient_id=PydanticObjectId(), doctor_id=PydanticObjectId(), start_at=NINE, end_at=NINE
        )


# --- faq --------------------------------------------------------------


async def test_faq_approved_entries_and_search(db):
    hours = await FaqEntry(
        question="Quels sont les horaires d'ouverture de la clinique ?",
        answer="Du lundi au vendredi de 8h à 18h, le samedi de 8h à 12h.",
        category="Pratique",
        is_approved=True,
    ).insert()
    parking = await FaqEntry(
        question="Y a-t-il un parking ?",
        answer="Oui, un parking gratuit est ouvert aux horaires de la clinique.",
        category="Accès",
        is_approved=True,
    ).insert()
    await FaqEntry(
        question="Horaires des urgences ?",
        answer="Réponse non validée.",
        is_approved=False,
    ).insert()

    approved = await list_approved_faq()
    results = await search_approved_faq("horaires")

    assert [entry.id for entry in approved] == [parking.id, hours.id]
    assert [entry.id for entry in await list_approved_faq("Pratique")] == [hours.id]
    # Question matches weigh 3x more than answer matches; the unapproved entry is excluded.
    assert [entry.id for entry in results] == [hours.id, parking.id]
    assert await search_approved_faq("   ") == []
