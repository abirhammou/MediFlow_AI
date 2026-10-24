"""Fictitious dev patients for the patient records module (about 15 records).

Run from backend/:  .\\.venv\\Scripts\\python -m scripts.seed_dev_patients
(also run by scripts.seed).

Idempotent: a patient is looked up by nationalId, or by name + birth date when it
has none, and only inserted when missing. Record numbers come from the shared
sequence. All names, CINs and phone numbers are invented.
"""

import argparse
import asyncio
import re
import sys
from datetime import date
from typing import Any

from beanie import PydanticObjectId
from beanie.operators import Eq, RegEx

from app.core.config import settings
from app.core.db import create_client, init_db
from app.core.sequence import next_record_number
from app.core.time import utc_midnight
from app.modules.auth.models import User
from app.modules.patients.models import (
    Address,
    BloodType,
    EmergencyContact,
    Gender,
    Insurance,
    Patient,
)

ADMIN_EMAIL = "admin@mediflow.local"


def _cnam(number: str) -> Insurance:
    return Insurance(provider="CNAM", number=number)


DEV_PATIENTS: list[dict[str, Any]] = [
    {
        "national_id": "09812345",
        "first_name": "Mohamed",
        "last_name": "Ben Ammar",
        "date_of_birth": date(1958, 4, 12),
        "gender": Gender.MALE,
        "phone": "+216 98 120 340",
        "address": Address(street="14 rue Ibn Khaldoun", city="Tunis", postal_code="1001"),
        "blood_type": BloodType.A_POS,
        "insurance": _cnam("CN-310045"),
        "emergency_contact": EmergencyContact(name="Salma Ben Ammar", phone="+216 98 120 341", relation="Épouse"),
        "administrative_notes": "Retraité. Vient accompagné de son épouse.",
    },
    {
        "national_id": "09823456",
        "first_name": "Fatma",
        "last_name": "Trabelsi",
        "date_of_birth": date(1983, 10, 5),
        "gender": Gender.FEMALE,
        "phone": "+216 22 456 789",
        "email": "fatma.trabelsi@example.test",
        "address": Address(street="3 avenue de la Liberté", city="Ariana", postal_code="2080"),
        "blood_type": BloodType.O_POS,
        "insurance": _cnam("CN-310046"),
    },
    {
        "national_id": "09834567",
        "first_name": "Ahmed",
        "last_name": "Chaabane",
        "date_of_birth": date(1991, 2, 17),
        "gender": Gender.MALE,
        "phone": "+216 55 300 120",
        "address": Address(city="Sfax", postal_code="3027"),
        "blood_type": BloodType.B_NEG,
    },
    {
        "national_id": "09845678",
        "first_name": "Sonia",
        "last_name": "Dridi",
        "date_of_birth": date(1969, 8, 30),
        "gender": Gender.FEMALE,
        "phone": "+216 73 221 908",
        "address": Address(street="Rue de la Corniche", city="Sousse", postal_code="4051"),
        "blood_type": BloodType.AB_POS,
        "insurance": _cnam("CN-310047"),
        "emergency_contact": EmergencyContact(name="Hichem Dridi", phone="+216 73 221 909", relation="Frère"),
    },
    {
        "national_id": "09856789",
        "first_name": "Rania",
        "last_name": "Bouazizi",
        "date_of_birth": date(2012, 6, 3),
        "gender": Gender.FEMALE,
        "address": Address(city="Monastir", postal_code="5000"),
        "blood_type": BloodType.O_NEG,
        "insurance": _cnam("CN-310048"),
        "emergency_contact": EmergencyContact(name="Lotfi Bouazizi", phone="+216 97 654 321", relation="Père"),
        "administrative_notes": "Patiente mineure : rendez-vous avec un parent.",
    },
    {
        "national_id": "09867890",
        "first_name": "Hamza",
        "last_name": "Khemiri",
        "date_of_birth": date(2000, 12, 24),
        "gender": Gender.MALE,
        "phone": "+216 50 777 888",
        "email": "hamza.khemiri@example.test",
        "address": Address(city="Tunis", postal_code="1053"),
        "blood_type": BloodType.A_NEG,
    },
    {
        "national_id": "09878901",
        "first_name": "Claire",
        "last_name": "Martin",
        "date_of_birth": date(1977, 3, 9),
        "gender": Gender.FEMALE,
        "phone": "+33 6 12 34 56 78",
        "email": "claire.martin@example.test",
        "address": Address(street="Les Berges du Lac", city="Tunis", postal_code="1053"),
        "insurance": Insurance(provider="Assurance privée", number="AP-77001"),
        "administrative_notes": "Ressortissante française, assurance privée internationale.",
    },
    {
        "national_id": "09889012",
        "first_name": "Walid",
        "last_name": "Hammami",
        "date_of_birth": date(1949, 1, 15),
        "gender": Gender.MALE,
        "phone": "+216 74 400 500",
        "address": Address(city="Sfax", postal_code="3000"),
        "blood_type": BloodType.O_POS,
        "insurance": _cnam("CN-310049"),
        "emergency_contact": EmergencyContact(name="Mouna Hammami", phone="+216 74 400 501", relation="Fille"),
        "administrative_notes": "Malentendant : privilégier le contact par la fille.",
    },
    {
        "national_id": "09890123",
        "first_name": "Ines",
        "last_name": "Saidi",
        "date_of_birth": date(1996, 5, 28),
        "gender": Gender.FEMALE,
        "phone": "+216 29 111 333",
        "address": Address(city="Ariana", postal_code="2037"),
        "blood_type": BloodType.B_POS,
    },
    {
        "national_id": "09901234",
        "first_name": "Sami",
        "last_name": "Ferchichi",
        "date_of_birth": date(1986, 9, 11),
        "gender": Gender.MALE,
        "phone": "+216 92 808 606",
        "address": Address(street="Avenue Farhat Hached", city="Gabès", postal_code="6000"),
        "blood_type": BloodType.AB_NEG,
        "insurance": _cnam("CN-310050"),
    },
    {
        "national_id": "09912345",
        "first_name": "Marwa",
        "last_name": "Ben Youssef",
        "date_of_birth": date(1993, 11, 19),
        "gender": Gender.FEMALE,
        "email": "marwa.benyoussef@example.test",
        "address": Address(city="Sousse", postal_code="4000"),
        "blood_type": BloodType.A_POS,
        "emergency_contact": EmergencyContact(name="Anis Ben Youssef", phone="+216 23 456 000", relation="Mari"),
    },
    {
        "national_id": "09923456",
        "first_name": "Alex",
        "last_name": "Mzoughi",
        "date_of_birth": date(2004, 7, 7),
        "gender": Gender.OTHER,
        "phone": "+216 58 222 444",
        "address": Address(city="Bizerte", postal_code="7000"),
    },
    {
        "national_id": "09934567",
        "first_name": "Habib",
        "last_name": "Zouari",
        "date_of_birth": date(1964, 2, 29),
        "gender": Gender.MALE,
        "phone": "+216 72 333 222",
        "address": Address(city="Nabeul", postal_code="8000"),
        "blood_type": BloodType.B_POS,
        "insurance": _cnam("CN-310051"),
    },
    # Without a CIN (e.g. a newborn or a foreign visitor).
    {
        "first_name": "Yasmine",
        "last_name": "Gharsalli",
        "date_of_birth": date(2025, 12, 1),
        "gender": Gender.FEMALE,
        "address": Address(city="Tunis", postal_code="1002"),
        "emergency_contact": EmergencyContact(name="Olfa Gharsalli", phone="+216 21 900 800", relation="Mère"),
        "administrative_notes": "Nouveau-né, CIN non applicable.",
    },
    {
        "first_name": "Julien",
        "last_name": "Lefèvre",
        "date_of_birth": date(1980, 10, 22),
        "gender": Gender.MALE,
        "phone": "+33 7 98 76 54 32",
        "address": Address(city="Sousse"),
        "blood_type": BloodType.O_POS,
        "administrative_notes": "Touriste de passage, pas de CIN.",
    },
]  # fmt: skip


def _exact(value: str) -> str:
    return f"^{re.escape(value)}$"


async def _find_existing(spec: dict[str, Any]) -> Patient | None:
    if spec.get("national_id"):
        return await Patient.find_one(Eq(Patient.national_id, spec["national_id"]))
    return await Patient.find_one(
        RegEx(Patient.first_name, _exact(spec["first_name"]), "i"),
        RegEx(Patient.last_name, _exact(spec["last_name"]), "i"),
        Eq(Patient.date_of_birth, utc_midnight(spec["date_of_birth"])),
    )


async def seed_dev_patients(created_by: PydanticObjectId | None = None) -> tuple[int, int]:
    """Insert the missing dev patients; returns (created, already present).

    Beanie must be initialised (`init_db`).
    """
    created = existing = 0
    for spec in DEV_PATIENTS:
        if await _find_existing(spec) is not None:
            existing += 1
            continue
        await Patient(
            **spec,
            record_number=await next_record_number(),
            created_by=created_by,
            updated_by=created_by,
        ).insert()
        created += 1
    return created, existing


async def main() -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    if settings.env == "prod":
        print("Refusé : le seed de démonstration ne s'exécute pas avec ENV=prod.", file=sys.stderr)
        return 1
    client = create_client(settings.mongodb_uri)
    try:
        database = client[settings.mongodb_db]
        await database.command("ping")
        await init_db(database)
        admin = await User.find_one(Eq(User.email, ADMIN_EMAIL))
        created, existing = await seed_dev_patients(admin.id if admin else None)
    finally:
        await client.close()
    print(f"  patients {created:>2} créé(s), {existing:>2} déjà présent(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
