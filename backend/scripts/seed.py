"""Demo data for development: one account per role, patients, appointments and FAQ entries.

Run from backend/:  .\\.venv\\Scripts\\python -m scripts.seed

Works on whichever MongoDB `MONGODB_URI` points to (Docker or local); the schema must
already exist (database/mongo-init.js). Idempotent: every record is looked up by a natural
key (email, nationalId, appointment reason, FAQ question) and only inserted when missing,
so running it again never duplicates anything and never resets a changed password.
Appointment dates are relative to the day of the first run. All data is fictitious.
"""

import argparse
import asyncio
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Any

from beanie import PydanticObjectId
from beanie.operators import Eq

from app.core.config import settings
from app.core.db import create_client, init_db
from app.core.sequence import next_record_number
from app.core.time import utcnow
from app.modules.appointments.models import Appointment, AppointmentStatus
from app.modules.auth.models import Availability, DoctorProfile, Role, User
from app.modules.faq.models import FaqEntry
from app.modules.patients.models import (
    Address,
    BloodType,
    EmergencyContact,
    Gender,
    Insurance,
    Patient,
)
from app.security import hash_password

DEFAULT_PASSWORD = "MediFlow2026!"
# Tunisia: UTC+1 all year. Appointment times below are local clinic times.
CLINIC_TZ = timezone(timedelta(hours=1))
WEEKDAYS = range(1, 6)

ACCOUNTS: list[dict[str, Any]] = [
    {"email": "admin@mediflow.local", "first_name": "Sami", "last_name": "Admin", "role": Role.ADMIN},
    {
        "email": "dr.benali@mediflow.local",
        "first_name": "Hela",
        "last_name": "Benali",
        "role": Role.DOCTOR,
        "doctor_profile": DoctorProfile(
            specialty="Médecine générale",
            phone="+216 71 000 101",
            office_room="A12",
            availabilities=[
                Availability(day_of_week=day, start_time="08:30", end_time="12:30", slot_minutes=30)
                for day in WEEKDAYS
            ],
        ),
    },
    {
        "email": "dr.trabelsi@mediflow.local",
        "first_name": "Mehdi",
        "last_name": "Trabelsi",
        "role": Role.DOCTOR,
        "doctor_profile": DoctorProfile(
            specialty="Cardiologie",
            phone="+216 71 000 102",
            office_room="B03",
            availabilities=[
                Availability(day_of_week=day, start_time="14:00", end_time="18:00", slot_minutes=20)
                for day in (2, 4)
            ],
        ),
    },
    {"email": "secretariat@mediflow.local", "first_name": "Ines", "last_name": "Mejri", "role": Role.SECRETARY},
    {"email": "gestion@mediflow.local", "first_name": "Rami", "last_name": "Khelifi", "role": Role.ADMIN_STAFF},
    # Inactive doctor: shows the approval flow (PATCH /api/users/{id}/approve).
    {
        "email": "medecin.attente@mediflow.local",
        "first_name": "Sarra",
        "last_name": "Attente",
        "role": Role.DOCTOR,
        "is_active": False,
        "doctor_profile": DoctorProfile(specialty="Pédiatrie"),
    },
]
# Created after the patients: linked to the first patient record.
PATIENT_ACCOUNT = {
    "email": "patient@mediflow.local",
    "first_name": "Leila",
    "last_name": "Haddad",
    "role": Role.PATIENT,
}

PATIENTS: list[dict[str, Any]] = [
    {
        "national_id": "DEMO-0001",
        "first_name": "Leila",
        "last_name": "Haddad",
        "date_of_birth": date(1988, 3, 14),
        "gender": Gender.FEMALE,
        "phone": "+216 20 123 456",
        "email": "leila.haddad@example.test",
        "address": Address(street="12 rue de Marseille", city="Tunis", postal_code="1000"),
        "blood_type": BloodType.A_POS,
        "insurance": Insurance(provider="CNAM", number="CN-100245"),
        "emergency_contact": EmergencyContact(name="Karim Haddad", phone="+216 22 987 654", relation="Époux"),
        "administrative_notes": "Hypertension suivie depuis 2022. Préfère les rendez-vous le matin.",
    },
    {
        "national_id": "DEMO-0002",
        "first_name": "Youssef",
        "last_name": "Ben Salah",
        "date_of_birth": date(1975, 11, 2),
        "gender": Gender.MALE,
        "phone": "+216 98 456 123",
        "address": Address(street="5 avenue Habib Bourguiba", city="Sfax", postal_code="3000"),
        "blood_type": BloodType.O_POS,
        "insurance": Insurance(provider="CNAM", number="CN-200871"),
        "administrative_notes": "Diabète de type 2. Renouvellement d'ordonnance tous les trois mois.",
    },
    {
        "national_id": "DEMO-0003",
        "first_name": "Amira",
        "last_name": "Gharbi",
        "date_of_birth": date(1995, 7, 21),
        "gender": Gender.FEMALE,
        "email": "amira.gharbi@example.test",
        "address": Address(city="Sousse", postal_code="4000"),
        "blood_type": BloodType.B_POS,
        "administrative_notes": "Palpitations signalées, adressée en cardiologie.",
    },
    {
        "national_id": "DEMO-0004",
        "first_name": "Karim",
        "last_name": "Jaziri",
        "date_of_birth": date(1962, 1, 30),
        "gender": Gender.MALE,
        "phone": "+216 52 741 852",
        "address": Address(city="Bizerte", postal_code="7000"),
        "blood_type": BloodType.AB_NEG,
        "insurance": Insurance(provider="Assurance privée", number="AP-55120"),
        "emergency_contact": EmergencyContact(name="Nadia Jaziri", phone="+216 52 111 222", relation="Fille"),
    },
    {
        "national_id": "DEMO-0005",
        "first_name": "Nour",
        "last_name": "Mansouri",
        "date_of_birth": date(2001, 9, 9),
        "gender": Gender.FEMALE,
        "email": "nour.mansouri@example.test",
        "address": Address(city="Nabeul", postal_code="8000"),
        "blood_type": BloodType.O_NEG,
    },
]

# (patient national_id, doctor email, days from today, local time, status, reason)
APPOINTMENTS: list[tuple[str, str, int, time, AppointmentStatus, str]] = [
    ("DEMO-0001", "dr.benali@mediflow.local", 0, time(9, 0), AppointmentStatus.CONFIRMED, "Consultation de suivi"),
    ("DEMO-0002", "dr.benali@mediflow.local", 0, time(10, 0), AppointmentStatus.PENDING, "Renouvellement d'ordonnance"),
    ("DEMO-0003", "dr.trabelsi@mediflow.local", 0, time(15, 0), AppointmentStatus.CONFIRMED, "Bilan cardiologique"),
    ("DEMO-0001", "dr.trabelsi@mediflow.local", 3, time(14, 0), AppointmentStatus.CONFIRMED, "Contrôle de la tension artérielle"),
    ("DEMO-0004", "dr.benali@mediflow.local", 2, time(9, 30), AppointmentStatus.PENDING, "Douleurs lombaires"),
    ("DEMO-0005", "dr.benali@mediflow.local", 7, time(11, 0), AppointmentStatus.CONFIRMED, "Vaccination"),
    ("DEMO-0002", "dr.benali@mediflow.local", -7, time(9, 0), AppointmentStatus.COMPLETED, "Première consultation"),
    ("DEMO-0003", "dr.trabelsi@mediflow.local", -3, time(16, 0), AppointmentStatus.CANCELLED, "Échographie cardiaque"),
]
APPOINTMENT_MINUTES = 30

FAQ: list[tuple[str, str, str]] = [
    (
        "Horaires",
        "Quels sont les horaires d'ouverture du cabinet ?",
        "Le cabinet est ouvert du lundi au vendredi de 8h30 à 18h00. Les consultations de cardiologie ont lieu le mardi et le jeudi après-midi.",
    ),
    (
        "Rendez-vous",
        "Quels documents dois-je apporter à mon rendez-vous ?",
        "Votre carte d'identité, votre carte d'assurance (CNAM ou assurance privée), vos ordonnances en cours et vos derniers résultats d'analyses.",
    ),
    (
        "Rendez-vous",
        "Comment annuler ou déplacer un rendez-vous ?",
        "Contactez le secrétariat au moins 24 heures à l'avance par téléphone ou depuis votre espace patient.",
    ),
    (
        "Résultats",
        "Comment recevoir mes résultats d'analyses ?",
        "Les résultats sont ajoutés à votre dossier dès réception et expliqués par votre médecin lors de la consultation suivante.",
    ),
    (
        "Assurance",
        "Le cabinet accepte-t-il la prise en charge CNAM ?",
        "Oui, le cabinet est conventionné CNAM. Pensez à apporter votre carnet de soins à chaque visite.",
    ),
    (
        "Urgences",
        "Que faire en cas d'urgence ?",
        "Le cabinet ne prend pas en charge les urgences. Appelez le SAMU au 190 ou rendez-vous aux urgences les plus proches.",
    ),
]


@dataclass
class SeedReport:
    created: Counter
    existing: Counter


async def _ensure_user(spec: dict[str, Any], password_hash: str, report: SeedReport, **extra: Any) -> User:
    user = await User.find_one(Eq(User.email, spec["email"]))
    if user is not None:
        report.existing["users"] += 1
        return user
    report.created["users"] += 1
    return await User(**spec, **extra, password_hash=password_hash).insert()


async def _ensure_patient(spec: dict[str, Any], created_by: PydanticObjectId, report: SeedReport) -> Patient:
    patient = await Patient.find_one(Eq(Patient.national_id, spec["national_id"]))
    if patient is not None:
        report.existing["patients"] += 1
        return patient
    report.created["patients"] += 1
    return await Patient(
        **spec, record_number=await next_record_number(), created_by=created_by
    ).insert()


def _start_at(today: date, days: int, local_time: time) -> datetime:
    return datetime.combine(today + timedelta(days=days), local_time, tzinfo=CLINIC_TZ).astimezone(UTC)


async def seed(password: str = DEFAULT_PASSWORD) -> SeedReport:
    """Insert the missing demo records. Beanie must be initialised (`init_db`)."""
    report = SeedReport(created=Counter(), existing=Counter())
    password_hash = hash_password(password)

    users = {spec["email"]: await _ensure_user(spec, password_hash, report) for spec in ACCOUNTS}
    admin = users["admin@mediflow.local"]

    patients = {spec["national_id"]: await _ensure_patient(spec, admin.id, report) for spec in PATIENTS}
    await _ensure_user(PATIENT_ACCOUNT, password_hash, report, patient_id=patients["DEMO-0001"].id)

    today = utcnow().astimezone(CLINIC_TZ).date()
    for national_id, doctor_email, days, local_time, status, reason in APPOINTMENTS:
        patient, doctor = patients[national_id], users[doctor_email]
        existing = await Appointment.find_one(
            Eq(Appointment.patient_id, patient.id),
            Eq(Appointment.doctor_id, doctor.id),
            Eq(Appointment.reason, reason),
        )
        if existing is not None:
            report.existing["appointments"] += 1
            continue
        start_at = _start_at(today, days, local_time)
        await Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            start_at=start_at,
            end_at=start_at + timedelta(minutes=APPOINTMENT_MINUTES),
            reason=reason,
            status=status,
            cancel_reason="Patient indisponible" if status == AppointmentStatus.CANCELLED else None,
            created_by=users["secretariat@mediflow.local"].id,
        ).insert()
        report.created["appointments"] += 1

    for category, question, answer in FAQ:
        if await FaqEntry.find_one(Eq(FaqEntry.question, question)) is not None:
            report.existing["faq_entries"] += 1
            continue
        await FaqEntry(
            question=question, answer=answer, category=category, is_approved=True, created_by=admin.id
        ).insert()
        report.created["faq_entries"] += 1

    return report


def _print_report(report: SeedReport, password: str) -> None:
    for kind in ("users", "patients", "appointments", "faq_entries"):
        print(f"  {kind:<13} {report.created[kind]:>2} créé(s), {report.existing[kind]:>2} déjà présent(s)")
    print("\nComptes de démonstration (mot de passe identique pour tous) :")
    for spec in [*ACCOUNTS, PATIENT_ACCOUNT]:
        state = "" if spec.get("is_active", True) else "  (inactif : à approuver)"
        print(f"  {spec['role'].value:<12} {spec['email']}{state}")
    shown = password if password == DEFAULT_PASSWORD else "(SEED_PASSWORD)"
    print(f"  Mot de passe : {shown}")
    print("  Les mots de passe des comptes déjà présents ne sont pas modifiés.")


async def main() -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    if settings.env == "prod":
        print("Refusé : le seed de démonstration ne s'exécute pas avec ENV=prod.", file=sys.stderr)
        return 1
    password = settings.seed_password or DEFAULT_PASSWORD
    client = create_client(settings.mongodb_uri)
    try:
        database = client[settings.mongodb_db]
        await database.command("ping")
        await init_db(database)
        print(f"Seed de la base « {settings.mongodb_db} »…")
        report = await seed(password)
    finally:
        await client.close()
    _print_report(report, password)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
