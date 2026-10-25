"""Demo data for development: one account per role, patients, appointments, FAQ entries
and, through scripts.seed_modules, the data of every module (medical reports, AI summaries,
documents, follow-up tasks and reminders, appointment requests, LLM call log).

Run from backend/:  .\\.venv\\Scripts\\python -m scripts.seed

Works on whichever MongoDB `MONGODB_URI` points to (Docker or local); the schema must
already exist (database/mongo-init.js). Idempotent: every record is looked up by a natural
key (email, nationalId, appointment reason, FAQ question) and only inserted when missing,
so running it again never duplicates anything and never resets a changed password
(see scripts.seed_modules for the keys of the module data).
Appointment dates are relative to the day of the first run. All data is fictitious.
Existing patients get the seed's administrative notes when theirs are empty;
`--reset-notes` also replaces notes that differ (see scripts.seed_dev_patients).
"""

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
from scripts.seed_dev_patients import (
    DEV_PATIENTS,
    argument_parser,
    find_existing,
    seed_dev_patients,
    sync_notes,
)
from scripts.seed_modules import patient_key, seed_modules

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
        "administrative_notes": (
            "Motif de suivi : hypertension artérielle découverte en mars 2022. La patiente, "
            "comptable dans une agence bancaire du centre de Tunis, se plaignait depuis "
            "plusieurs semaines de maux de tête en fin de journée et de bourdonnements "
            "d'oreille. Une mesure faite par hasard en pharmacie avait relevé 165/100 ; elle "
            "est venue consulter le lendemain.\n\n"
            "Histoire : antécédents familiaux importants (père décédé d'un AVC à 61 ans, mère"
            " hypertendue). Deux grossesses (2014 et 2018), la seconde compliquée d'une "
            "prééclampsie à 34 semaines avec césarienne en urgence. Tabagisme arrêté en 2018."
            " Surpoids modéré, sédentarité liée au travail de bureau.\n\n"
            "État actuel : sous amlodipine 5 mg depuis 2022. Tension globalement contrôlée au"
            " cabinet (autour de 130/85), mais automesures plus élevées pendant les semaines "
            "de clôture comptable, avec stress et manque de sommeil. Signale des chevilles "
            "gonflées le soir, peut-être dues au traitement, à réévaluer. Bilan de janvier "
            "2026 : reins normaux, cholestérol LDL légèrement élevé.\n\n"
            "Suivi : consultation tous les trois mois et contrôle annuel chez le cardiologue "
            "du cabinet (rendez-vous déjà fixé). Holter tensionnel envisagé si les chiffres "
            "restent élevés.\n\n"
            "Points pratiques : préfère les rendez-vous le matin avant 10h (travaille "
            "l'après-midi). Carnet de soins CNAM renouvelé en janvier 2026. Utilise l'espace "
            "patient : rappels par SMS plutôt que par appel. Son époux est la personne à "
            "prévenir."
        ),
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
        "administrative_notes": (
            "Motif de suivi : diabète de type 2 découvert en 2017 lors d'une visite de "
            "médecine du travail (glycémie à jeun à 1,62 g/l). Le patient, chauffeur de poids"
            " lourd pour une société de transport de Sfax, passe de longues journées sur la "
            "route, mange souvent sur le pouce et dort mal.\n\n"
            "Histoire : pendant les premières années, metformine seule prise de façon "
            "irrégulière ; il arrêtait les comprimés pendant les longs trajets à cause des "
            "troubles digestifs. En 2023, hémoglobine glyquée à 9,4 % et plaie du pied droit "
            "lente à cicatriser, causée par une chaussure de sécurité trop serrée. Cet "
            "épisode lui a fait prendre la maladie au sérieux : ajout de gliclazide, "
            "consultation diététique, chaussures adaptées.\n\n"
            "État actuel : HbA1c à 7,6 % en août 2026, en amélioration mais pas encore à "
            "l'objectif. A perdu 6 kg en un an. Se plaint de fourmillements dans les deux "
            "pieds la nuit : examen des pieds à chaque visite. Fond d'œil de 2024 normal, à "
            "refaire. Tension limite (140/88), pas encore traitée.\n\n"
            "Suivi : renouvellement d'ordonnance tous les trois mois, prise de sang avant "
            "chaque visite.\n\n"
            "Points pratiques : prise en charge CNAM maladie chronique (APCI) valable "
            "jusqu'au 31/03/2027, lancer le renouvellement un mois avant. Deux rendez-vous "
            "manqués en 2026 sans prévenir à cause de déplacements imprévus : l'appeler la "
            "veille pour confirmer."
        ),
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
        "administrative_notes": (
            "Motif : palpitations. La patiente, doctorante en biologie à Sousse, est venue en"
            " juin 2026 pour des épisodes où son cœur s'emballe brutalement, surtout le soir "
            "ou après un café. Ils durent de quelques minutes à une demi-heure, parfois avec "
            "une sensation de malaise, sans perte de connaissance. Le premier épisode remonte"
            " à fin 2025, pendant la rédaction de sa thèse : beaucoup de café, nuits courtes,"
            " forte anxiété.\n\n"
            "Antécédents : asthme dans l'enfance, sans crise depuis l'adolescence. Pas de "
            "traitement en dehors d'une contraception orale. Sa mère aurait une maladie de la"
            " thyroïde (non précisée).\n\n"
            "Examen et bilan : examen normal au cabinet, ECG de repos normal. TSH demandée, "
            "résultat attendu. Adressée en cardiologie pour un Holter ECG et une échographie "
            "cardiaque ; l'échographie prévue en octobre a été annulée (patiente "
            "indisponible), à reprogrammer. En attendant : moins de café, sommeil régulier, "
            "consulter tout de suite en cas de perte de connaissance ou de douleur dans la "
            "poitrine.\n\n"
            "Points pratiques : pas d'assurance déclarée, règlement en espèces, reçu à "
            "remettre à chaque consultation. Disponible le samedi ou en fin de journée. "
            "Courrier du cardiologue attendu, à classer dès réception."
        ),
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
        "administrative_notes": (
            "Motif actuel : douleurs lombaires depuis environ deux mois, descendant parfois "
            "dans la jambe gauche, aggravées en position assise prolongée. Le patient, ancien"
            " mécanicien naval au port de Bizerte, retraité depuis 2022, a toujours eu le dos"
            " fragile après des années à soulever des pièces lourdes. Les douleurs ont "
            "commencé après avoir aidé son fils à déménager.\n\n"
            "Histoire : prothèse totale du genou droit en novembre 2024 dans une clinique "
            "privée de Tunis, avec une rééducation longue. Depuis, il marche avec une canne "
            "sur les longues distances et a pris environ 8 kg. Hypertension traitée depuis "
            "2015 (périndopril), cholestérol sous statine. Ancien gros fumeur, arrêt en 2010.\n\n"
            "État actuel : douleur à 6/10, sommeil perturbé, pas de trouble urinaire ni de "
            "faiblesse de la jambe. Prend du paracétamol et, de lui-même, de l'ibuprofène "
            "acheté en pharmacie, à revoir à cause de la tension. Kinésithérapie prescrite ; "
            "IRM lombaire si pas d'amélioration dans un mois.\n\n"
            "Points pratiques : assurance privée, accord préalable obligatoire avant tout "
            "examen d'imagerie (réponse sous 48 h). Mobilité réduite : prévoir le cabinet du "
            "rez-de-chaussée. Sa fille gère les rendez-vous, joignable au +216 52 111 222. "
            "Facture de mars 2026 non réglée, relance envoyée le 12/04/2026."
        ),
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
        "administrative_notes": (
            "Motif : mise à jour des vaccinations avant un départ à l'étranger. La patiente, "
            "jeune diplômée en informatique, a obtenu un contrat de travail en Allemagne et "
            "doit présenter un carnet de vaccination à jour avant l'été 2027. Première "
            "consultation le 02/09/2026, adressée par une amie.\n\n"
            "Histoire : enfance à Nabeul sans problème de santé particulier. Son carnet de "
            "vaccination a été en partie perdu lors d'un déménagement : seuls les vaccins "
            "jusqu'à 6 ans sont notés. Pas de rappel diphtérie-tétanos depuis l'adolescence "
            "selon ses souvenirs. Varicelle dans l'enfance. Allergie déclarée aux arachides "
            "(urticaire), jamais de réaction grave.\n\n"
            "État actuel : en bonne santé, aucun traitement. Appréhende les piqûres (malaise "
            "lors d'une prise de sang en 2021) : la faire allonger pour les vaccins. "
            "Sérologies demandées (rougeole, hépatite B) pour éviter des doses inutiles. "
            "Rappel DTP prévu dans le mois, puis calendrier selon les résultats.\n\n"
            "Points pratiques : pas d'assurance pour le moment, souhaite s'affilier à la CNAM"
            " (formulaire à lui remettre). Aura besoin d'un certificat de vaccination en "
            "anglais ou en allemand. Préfère être contactée par email : "
            "nour.mansouri@example.test."
        ),
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

# (category, question, answer[, approved]): approved unless False; the assistant only uses approved entries.
FAQ: list[tuple[str, str, str] | tuple[str, str, str, bool]] = [
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
    (
        "Comptes rendus",
        "Comment obtenir le compte rendu de ma consultation ?",
        "Une fois validé par votre médecin, le compte rendu est disponible dans votre espace patient et peut être téléchargé en PDF.",
    ),
    (
        "Résultats",
        "Une autre personne peut-elle récupérer mes résultats ?",
        "Oui, avec une autorisation écrite signée par vous et une pièce d'identité de la personne qui les récupère.",
    ),
    (
        "Paiement",
        "Peut-on payer par carte bancaire ?",
        "Le cabinet accepte les espèces et la carte bancaire. Une facture détaillée est remise sur demande.",
        False,
    ),
    (
        "Certificats",
        "Le cabinet délivre-t-il des certificats pour le sport ?",
        "Oui, après une consultation. Pensez à apporter le formulaire de votre club s'il en a un.",
        False,
    ),
]


@dataclass
class SeedReport:
    created: Counter
    existing: Counter
    notes_updated: int = 0


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


async def seed(password: str = DEFAULT_PASSWORD, *, reset_notes: bool = False) -> SeedReport:
    """Insert the missing demo records. Beanie must be initialised (`init_db`)."""
    report = SeedReport(created=Counter(), existing=Counter())
    password_hash = hash_password(password)

    users = {spec["email"]: await _ensure_user(spec, password_hash, report) for spec in ACCOUNTS}
    admin = users["admin@mediflow.local"]

    patients = {spec["national_id"]: await _ensure_patient(spec, admin.id, report) for spec in PATIENTS}
    users[PATIENT_ACCOUNT["email"]] = await _ensure_user(
        PATIENT_ACCOUNT, password_hash, report, patient_id=patients["DEMO-0001"].id
    )
    created, existing = await seed_dev_patients(admin.id)
    report.created["patients"] += created
    report.existing["patients"] += existing
    report.notes_updated = await sync_notes([*PATIENTS, *DEV_PATIENTS], admin.id, reset=reset_notes)

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

    for category, question, answer, *approved in FAQ:
        if await FaqEntry.find_one(Eq(FaqEntry.question, question)) is not None:
            report.existing["faq_entries"] += 1
            continue
        await FaqEntry(
            question=question,
            answer=answer,
            category=category,
            is_approved=approved[0] if approved else True,
            created_by=admin.id,
        ).insert()
        report.created["faq_entries"] += 1

    all_patients = {patient_key(spec): await find_existing(spec) for spec in [*PATIENTS, *DEV_PATIENTS]}
    await seed_modules(users, all_patients, report.created, report.existing)
    return report


KINDS = (
    "users",
    "patients",
    "appointments",
    "medical_reports",
    "patient_summaries",
    "document_categories",
    "medical_documents",
    "appointment_requests",
    "followup_tasks",
    "followup_reminders",
    "reminders",
    "faq_entries",
    "llm_interactions",
)


def _print_report(report: SeedReport, password: str) -> None:
    for kind in KINDS:
        print(f"  {kind:<20} {report.created[kind]:>3} créé(s), {report.existing[kind]:>3} déjà présent(s)")
    print(f"  {'notes':<20} {report.notes_updated:>3} mise(s) à jour")
    print("\nComptes de démonstration (mot de passe identique pour tous) :")
    for spec in [*ACCOUNTS, PATIENT_ACCOUNT]:
        state = "" if spec.get("is_active", True) else "  (inactif : à approuver)"
        print(f"  {spec['role'].value:<12} {spec['email']}{state}")
    shown = password if password == DEFAULT_PASSWORD else "(SEED_PASSWORD)"
    print(f"  Mot de passe : {shown}")
    print("  Les mots de passe des comptes déjà présents ne sont pas modifiés.")


async def main() -> int:
    args = argument_parser(__doc__.splitlines()[0]).parse_args()
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
        report = await seed(password, reset_notes=args.reset_notes)
    finally:
        await client.close()
    _print_report(report, password)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
