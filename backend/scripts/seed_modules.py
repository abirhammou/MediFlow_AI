"""Demo data for every module, built on the seeded users and patients (run by scripts.seed).

For each patient of scripts.seed_clinical_data: three past visits (COMPLETED appointments)
with their medical report (FINAL, ARCHIVED, DRAFT), an upcoming appointment, AI summaries,
medical documents, follow-up tasks and reminders; plus free-text appointment requests and
the LLM call log that goes with all of it.

Idempotent like scripts.seed: each record is looked up by a natural key and only inserted
when missing. Dates are relative to the day of the first run; insert hooks stamp "now",
so past records are back-dated afterwards with set().
"""

import json
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta

from beanie import PydanticObjectId
from beanie.operators import GTE, Eq

from app.core.models import AiReviewStatus
from app.core.time import utc_midnight, utcnow
from app.modules.appointments.models import (
    Appointment,
    AppointmentRequest,
    AppointmentStatus,
    DayPart,
    ParsedRequest,
)
from app.modules.auth.models import User
from app.modules.documents.models import DocumentCategory, ExtractedField, MedicalDocument
from app.modules.followup.models import FollowupTask, Reminder, ReminderStatus
from app.modules.llm.models import LlmInteraction, LlmModule
from app.modules.patients.dates import CLINIC_TZ, clinic_today
from app.modules.patients.models import Patient, PatientSummary, SummaryStatus
from app.modules.patients.summary_prompt import PROMPT_VERSION, SUMMARY_HEADINGS, build_messages
from app.modules.patients.summary_service import build_source_snapshot
from app.modules.reports.models import MedicalReport, ReportStatus
from app.modules.reports.prompts import SYSTEM_PROMPT as REPORT_SYSTEM_PROMPT
from app.modules.reports.prompts import report_prompt
from app.modules.reports.schemas import StructuredReport
from app.modules.reports.service import SECTIONS, render
from scripts.seed_clinical_data import APPOINTMENT_REQUESTS, BENALI, CLINICAL_HISTORY, History
from scripts.seed_files import seed_patient_files

DOCTORS = {BENALI: "dr.benali@mediflow.local", "T": "dr.trabelsi@mediflow.local"}
SECRETARY = "secretariat@mediflow.local"
ADMIN_STAFF = "gestion@mediflow.local"
PATIENT_EMAIL = "patient@mediflow.local"

# Same reference data as database/mongo-init.js (in case the database was created without it).
DOCUMENT_CATEGORIES = [
    ("ORDONNANCE", "Ordonnance"),
    ("ANALYSE", "Analyse biologique"),
    ("IMAGERIE", "Imagerie"),
    ("CERTIFICAT", "Certificat médical"),
    ("COMPTE_RENDU", "Compte rendu"),
    ("ADMINISTRATIF", "Administratif"),
]

REPORT_MODEL = "openai/gpt-oss-20b"
DEFAULT_MODEL = "gemini/gemini-3.8-flash"
REMINDER_STEPS = ("draft", "reviewed", "approved", "exported")
REMINDER_STATUSES = (ReminderStatus.DRAFT, ReminderStatus.APPROVED, ReminderStatus.SENT)
# Questions asked to the clinic FAQ assistant: (question, answer, error)
FAQ_QUESTIONS = [
    ("Quels sont les horaires du cabinet ?", "Du lundi au vendredi de 8h30 à 18h00.", None),
    ("Le cabinet accepte-t-il la CNAM ?", None, "Quota du fournisseur dépassé."),
    ("Où se garer ?", "Je n'ai pas cette information, contactez le secrétariat.", None),
]


def patient_key(spec: dict) -> str:
    """Key of CLINICAL_HISTORY: the CIN, or "First Last" for patients without one."""
    return spec.get("national_id") or f"{spec['first_name']} {spec['last_name']}"


def _full_name(patient: Patient) -> str:
    return f"{patient.first_name} {patient.last_name}"


def _slot(doctor: User, day: date, index: int, step: int) -> tuple[datetime, int]:
    """A slot of the doctor's weekly availability on `day`, or the nearest working day
    in the direction `step` (-1 past, +1 future). Returns (UTC start, minutes)."""
    availabilities = {a.day_of_week: a for a in doctor.doctor_profile.availabilities}
    while day.isoweekday() not in availabilities:
        day += timedelta(days=step)
    availability = availabilities[day.isoweekday()]
    start = datetime.combine(day, time.fromisoformat(availability.start_time), tzinfo=CLINIC_TZ)
    end = datetime.combine(day, time.fromisoformat(availability.end_time), tzinfo=CLINIC_TZ)
    length = timedelta(minutes=availability.slot_minutes)
    slot = start + (index % int((end - start) / length)) * length
    return slot.astimezone(UTC), availability.slot_minutes


class ModuleSeeder:
    def __init__(
        self,
        users: dict[str, User],
        patients: dict[str, Patient],
        created: Counter,
        existing: Counter,
    ) -> None:
        self.users = users
        self.patients = patients
        self.created = created
        self.existing = existing
        self.today = clinic_today()
        self.reports: list[MedicalReport] = []
        self.documents: list[MedicalDocument] = []

    def _found(self, kind: str, record: object | None) -> bool:
        if record is not None:
            self.existing[kind] += 1
            return True
        self.created[kind] += 1
        return False

    def _doctor(self, code: str) -> User:
        return self.users[DOCTORS[code]]

    async def run(self) -> None:
        await self._categories()
        for index, (key, history) in enumerate(CLINICAL_HISTORY.items()):
            patient = self.patients[key]
            visits = await self._visits(index, patient, history)
            await self._summaries(patient, history)
            await self._documents(patient, history, visits)
            await seed_patient_files(
                patient, history, self.users[SECRETARY], self.created, self.existing
            )
            await self._tasks(index, patient, history, visits[-1])
        await self._appointment_requests()
        await self._reminders()
        await self._llm_log()

    # ── Appointments and medical reports ──────────────────────────────────────

    async def _appointment(
        self,
        patient: Patient,
        doctor: User,
        reason: str,
        slot: tuple[datetime, int],
        status: AppointmentStatus,
    ) -> Appointment:
        appointment = await Appointment.find_one(
            Eq(Appointment.patient_id, patient.id),
            Eq(Appointment.doctor_id, doctor.id),
            Eq(Appointment.reason, reason),
        )
        if self._found("appointments", appointment):
            return appointment
        start_at, minutes = slot
        appointment = await Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            start_at=start_at,
            end_at=start_at + timedelta(minutes=minutes),
            reason=reason,
            status=status,
            created_by=self.users[SECRETARY].id,
        ).insert()
        if start_at < utcnow():
            booked = start_at - timedelta(days=10)
            await appointment.set({"createdAt": booked, "updatedAt": appointment.end_at})
        return appointment

    async def _visits(self, index: int, patient: Patient, history: History) -> list[Appointment]:
        appointments = []
        for number, visit in enumerate(history.visits):
            doctor = self._doctor(visit.doctor)
            slot = _slot(
                doctor, self.today - timedelta(days=visit.days_ago), index * 3 + number, -1
            )
            appointment = await self._appointment(
                patient, doctor, visit.title, slot, AppointmentStatus.COMPLETED
            )
            appointments.append(appointment)

            report = await MedicalReport.find_one(
                Eq(MedicalReport.patient_id, patient.id),
                Eq(MedicalReport.doctor_id, doctor.id),
                Eq(MedicalReport.title, visit.title),
            )
            if not self._found("medical_reports", report):
                content = None
                if visit.sections:
                    content = render(
                        StructuredReport(
                            **dict(
                                zip((field for field, _ in SECTIONS), visit.sections, strict=True)
                            )
                        )
                    )
                report = await MedicalReport(
                    patient_id=patient.id,
                    doctor_id=doctor.id,
                    appointment_id=appointment.id,
                    title=visit.title,
                    raw_notes=visit.notes,
                    structured_content=content,
                    status=visit.status,
                ).insert()
                written = appointment.end_at
                changes = {"createdAt": written, "updatedAt": written + timedelta(hours=2)}
                if visit.status == ReportStatus.ARCHIVED:
                    changes["archivedAt"] = changes["updatedAt"] = written + timedelta(days=60)
                await report.set(changes)
            self.reports.append(report)

        if history.next_visit:
            days, code, reason, status = history.next_visit
            doctor = self._doctor(code)
            slot = _slot(doctor, self.today + timedelta(days=days), index, 1)
            await self._appointment(patient, doctor, reason, slot, status)
        return appointments

    # ── AI summaries (patient records) ────────────────────────────────────────

    def _summary_text(self, patient: Patient, snapshot: dict, points: tuple[str, ...]) -> str:
        age = snapshot["age"]
        identity = [
            f"Dossier {snapshot['recordNumber']}",
            f"{age} ans" if age else "moins d'un an",
            snapshot["gender"],
            f"groupe {snapshot['bloodType'] or 'Non renseigné'}",
            snapshot["city"] or "ville Non renseigné",
        ]
        coverage = [
            snapshot["insuranceProvider"] or "Assurance : Non renseigné",
            "Personne à contacter : "
            + ("oui" if snapshot["hasEmergencyContact"] else "Non renseigné"),
        ]
        missing = [
            label
            for label, value in (
                ("CIN", patient.national_id),
                ("Téléphone", patient.phone),
                ("Assurance", patient.insurance),
                ("Groupe sanguin", patient.blood_type),
                ("Personne à contacter", patient.emergency_contact),
            )
            if not value
        ]
        to_check = [f"{label} à compléter" for label in missing] or ["Rien à signaler"]
        parts = (
            (", ".join(identity),),
            coverage,
            points or ("Aucune note administrative",),
            to_check,
        )
        return "\n".join(
            f"{heading}\n" + "\n".join(f"- {line}" for line in lines)
            for heading, lines in zip(SUMMARY_HEADINGS, parts, strict=True)
        )

    async def _summaries(self, patient: Patient, history: History) -> None:
        if history.summary is None:
            return
        if await PatientSummary.find_one(Eq(PatientSummary.patient_id, patient.id)) is not None:
            self.existing["patient_summaries"] += 1
            return
        snapshot = build_source_snapshot(patient)
        source = {"promptVersion": PROMPT_VERSION, "patient": snapshot}
        reviewer = self._doctor(BENALI).id
        now = utcnow()
        # (status, points, days ago, review comment)
        versions = {
            "VALIDATED": [(SummaryStatus.VALIDATED, history.points, 12, None)],
            "SUPERSEDED": [
                (SummaryStatus.SUPERSEDED, history.points[:1], 95, None),
                (SummaryStatus.VALIDATED, history.points, 9, None),
            ],
            "DRAFT": [(SummaryStatus.DRAFT, history.points, 2, None)],
            "REJECTED": [
                (
                    SummaryStatus.REJECTED,
                    (*history.points, "Patient à rappeler pour un traitement."),
                    6,
                    "Le résumé contient une consigne médicale absente du dossier.",
                )
            ],
        }[history.summary]
        for status, points, days, comment in versions:
            summary = await PatientSummary(
                patient_id=patient.id,
                content=self._summary_text(patient, snapshot, points),
                status=status,
                llm_model=DEFAULT_MODEL,
                source_snapshot=source,
                generated_by=self.users[SECRETARY].id,
                reviewed_by=None if status == SummaryStatus.DRAFT else reviewer,
                reviewed_at=None
                if status == SummaryStatus.DRAFT
                else now - timedelta(days=days - 1),
                review_comment=comment,
            ).insert()
            await summary.set({"createdAt": now - timedelta(days=days)})
            self.created["patient_summaries"] += 1

    # ── Medical documents (MedDoc) ────────────────────────────────────────────

    async def _categories(self) -> None:
        for code, label in DOCUMENT_CATEGORIES:
            category = await DocumentCategory.find_one(Eq(DocumentCategory.code, code))
            if not self._found("document_categories", category):
                await DocumentCategory(code=code, label=label).insert()

    async def _documents(
        self, patient: Patient, history: History, visits: list[Appointment]
    ) -> None:
        secretary = self.users[SECRETARY].id
        for number, doc in enumerate(history.documents):
            document = await MedicalDocument.find_one(
                Eq(MedicalDocument.patient_id, patient.id), Eq(MedicalDocument.title, doc.title)
            )
            if not self._found("medical_documents", document):
                uploaded = visits[number % len(visits)].end_at + timedelta(hours=1)
                status = AiReviewStatus.VALIDATED if doc.validated else AiReviewStatus.DRAFT
                document = await MedicalDocument(
                    patient_id=patient.id,
                    title=doc.title,
                    raw_text=doc.text,
                    category_code=doc.category if doc.validated else None,
                    ai_suggested_category_code=doc.category,
                    extracted_fields=[
                        ExtractedField(
                            name=name,
                            value=value,
                            status=status,
                            validated_by=secretary if doc.validated else None,
                            validated_at=uploaded + timedelta(days=1) if doc.validated else None,
                        )
                        for name, value in doc.fields
                    ],
                    uploaded_by=secretary,
                ).insert()
                await document.set(
                    {"createdAt": uploaded, "updatedAt": uploaded + timedelta(days=1)}
                )
            self.documents.append(document)

    # ── Follow-up tasks ───────────────────────────────────────────────────────

    async def _tasks(
        self, index: int, patient: Patient, history: History, last_visit: Appointment
    ) -> None:
        upcoming = (
            await Appointment.find(
                Eq(Appointment.patient_id, patient.id), GTE(Appointment.start_at, utcnow())
            )
            .sort(+Appointment.start_at)
            .first_or_none()
        )
        anchor = upcoming or last_visit
        assignees = (self.users[SECRETARY].id, self.users[ADMIN_STAFF].id)
        for number, (description, due_days, status) in enumerate(history.tasks):
            task = await FollowupTask.find_one(Eq(FollowupTask.description, description))
            if self._found("followup_tasks", task):
                continue
            await FollowupTask(
                patient_id=patient.id,
                appointment_id=anchor.id,
                assigned_to=assignees[(index + number) % 2],
                description=description,
                due_date=utc_midnight(self.today + timedelta(days=due_days)),
                status=status,
                patient_name=_full_name(patient),
                appointment_date=utc_midnight(anchor.start_at.astimezone(CLINIC_TZ).date()),
                appointment_reason=anchor.reason,
                created_by=self._doctor(BENALI).id,
            ).insert()

    # ── Appointment requests (Appointment Manager AI) ─────────────────────────

    async def _appointment_requests(self) -> None:
        now = utcnow()
        for message, days_ago, key, parsed in APPOINTMENT_REQUESTS:
            request = await AppointmentRequest.find_one(Eq(AppointmentRequest.raw_message, message))
            if self._found("appointment_requests", request):
                continue
            patient = self.patients[key] if key else None
            result = appointment_id = None
            if parsed:
                days, part, doctor, specialty, reason = parsed
                result = ParsedRequest(
                    preferred_date=utc_midnight(self.today + timedelta(days=days)),
                    day_part=DayPart(part) if part else None,
                    doctor_id=self._doctor(doctor).id if doctor else None,
                    specialty=specialty,
                    reason=reason,
                )
                if patient and doctor:
                    booked = await Appointment.find_one(
                        Eq(Appointment.patient_id, patient.id), Eq(Appointment.reason, reason)
                    )
                    appointment_id = booked.id if booked else None
            request = await AppointmentRequest(
                raw_message=message,
                parsed=result,
                patient_id=patient.id if patient else None,
                appointment_id=appointment_id,
                created_by=self.users[SECRETARY].id,
            ).insert()
            await request.set({"createdAt": now - timedelta(days=days_ago)})

    # ── Reminders of the upcoming confirmed appointments ──────────────────────

    async def _reminders(self) -> None:
        """Two collections: `followup_reminders` (read by the follow-up page, shape of
        app/modules/follow_up/router.py) and `reminders` (canonical model)."""
        saved = Reminder.get_pymongo_collection().database["followup_reminders"]
        confirmed = (
            await Appointment.find(
                Eq(Appointment.status, AppointmentStatus.CONFIRMED),
                GTE(Appointment.start_at, utcnow()),
            )
            .sort(+Appointment.start_at)
            .to_list()
        )
        for number, appointment in enumerate(confirmed):
            patient = await Patient.get(appointment.patient_id)
            doctor = await User.get(appointment.doctor_id)
            local = appointment.start_at.astimezone(CLINIC_TZ)
            when = f"le {local:%d/%m/%Y} à {local:%H:%M}"
            subject = f"Rappel : rendez-vous {when}"
            body = (
                f"Bonjour {_full_name(patient)},\n\nNous vous rappelons votre rendez-vous {when} "
                f"avec le Dr {doctor.last_name} ({appointment.reason}). Merci d'apporter votre "
                "carte d'assurance et vos ordonnances en cours. En cas d'empêchement, prévenez le "
                "secrétariat au moins 24 heures à l'avance.\n\nLe secrétariat MediFlow"
            )

            day = local.date().isoformat()
            key = {"patient_name": _full_name(patient), "appointment_date": day}
            if not self._found("followup_reminders", await saved.find_one(key)):
                await saved.insert_one(
                    {
                        **key,
                        "appointment_reason": appointment.reason,
                        "subject": subject,
                        "body": body,
                        "step": REMINDER_STEPS[number % len(REMINDER_STEPS)],
                        "created_at": (utcnow() - timedelta(days=1 + number % 3)).isoformat(),
                    }
                )

            reminder = await Reminder.find_one(Eq(Reminder.appointment_id, appointment.id))
            if self._found("reminders", reminder):
                continue
            status = REMINDER_STATUSES[number % len(REMINDER_STATUSES)]
            await Reminder(
                appointment_id=appointment.id,
                appointment_snapshot={
                    "patientName": _full_name(patient),
                    "doctorName": f"Dr {doctor.last_name}",
                    "startAt": appointment.start_at.isoformat(),
                    "reason": appointment.reason,
                },
                content=body,
                status=status,
                approved_by=self.users[SECRETARY].id if status != ReminderStatus.DRAFT else None,
                sent_at=utcnow() - timedelta(hours=3) if status == ReminderStatus.SENT else None,
            ).insert()

    # ── LLM call log ──────────────────────────────────────────────────────────

    async def _log(
        self,
        module: LlmModule,
        messages: list[dict[str, str]],
        *,
        at: datetime,
        user_id: PydanticObjectId,
        entity_id: PydanticObjectId | None = None,
        response: str | None = None,
        model: str = DEFAULT_MODEL,
        error: str | None = None,
    ) -> None:
        prompt = json.dumps(messages, ensure_ascii=False)
        logged = await LlmInteraction.find_one(
            Eq(LlmInteraction.module, module),
            Eq(LlmInteraction.entity_id, entity_id),
            Eq(LlmInteraction.prompt, prompt),
        )
        if self._found("llm_interactions", logged):
            return
        tokens_in = len(prompt) // 4
        interaction = await LlmInteraction(
            module=module,
            user_id=user_id,
            entity_id=entity_id,
            prompt=prompt,
            response=response,
            model=model,
            tokens_in=tokens_in,
            tokens_out=len(response) // 4 if response else None,
            latency_ms=900 + tokens_in % 2500,
            success=error is None,
            error_message=error,
        ).insert()
        # At least a day old: the hourly generation quotas (count_interactions) stay free.
        await interaction.set({"createdAt": min(at, utcnow() - timedelta(days=1))})

    async def _llm_log(self) -> None:
        secretary = self.users[SECRETARY].id
        for number, report in enumerate(self.reports):
            if not report.structured_content:
                continue
            messages = [
                {"role": "system", "content": REPORT_SYSTEM_PROMPT},
                {"role": "user", "content": report_prompt(report.raw_notes)},
            ]
            await self._log(
                LlmModule.REPORT,
                messages,
                at=report.created_at - timedelta(minutes=5),
                user_id=report.doctor_id,
                entity_id=report.id,
                response=report.structured_content,
                model=REPORT_MODEL,
            )
            if number % 9 == 0:  # an earlier attempt that timed out
                await self._log(
                    LlmModule.REPORT,
                    messages,
                    at=report.created_at - timedelta(minutes=8),
                    user_id=report.doctor_id,
                    entity_id=None,
                    model=REPORT_MODEL,
                    error="Timeout: le fournisseur n'a pas répondu en 30 s.",
                )

        for summary in await PatientSummary.find_all().to_list():
            await self._log(
                LlmModule.PATIENT_RECORD,
                build_messages((summary.source_snapshot or {}).get("patient", {})),
                at=summary.created_at - timedelta(minutes=1),
                user_id=summary.generated_by or secretary,
                entity_id=summary.id,
                response=summary.content,
            )

        for document in self.documents:
            if document.category_code:  # validated: the suggestion is only logged for the others
                continue
            await self._log(
                LlmModule.MEDDOC,
                [
                    {
                        "role": "system",
                        "content": "Classe le document médical et extrais ses champs.",
                    },
                    {"role": "user", "content": f"<document>\n{document.raw_text}\n</document>"},
                ],
                at=document.created_at,
                user_id=secretary,
                entity_id=document.id,
                response=json.dumps({"category": document.ai_suggested_category_code}),
            )

        for request in await AppointmentRequest.find_all().to_list():
            await self._log(
                LlmModule.APPOINTMENT,
                [
                    {"role": "system", "content": "Extrais la demande de rendez-vous en JSON."},
                    {"role": "user", "content": request.raw_message},
                ],
                at=request.created_at,
                user_id=secretary,
                entity_id=request.id,
                response=request.parsed.model_dump_json(by_alias=True) if request.parsed else None,
                error=None if request.parsed else "Réponse du modèle invalide : JSON attendu.",
            )

        for reminder in await Reminder.find_all().to_list():
            await self._log(
                LlmModule.FOLLOWUP,
                [
                    {"role": "system", "content": "Rédige un rappel administratif de rendez-vous."},
                    {
                        "role": "user",
                        "content": json.dumps(reminder.appointment_snapshot, ensure_ascii=False),
                    },
                ],
                at=reminder.created_at,
                user_id=secretary,
                entity_id=reminder.id,
                response=reminder.content,
            )

        for days, (question, response, error) in enumerate(FAQ_QUESTIONS, start=2):
            await self._log(
                LlmModule.FAQ,
                [
                    {
                        "role": "system",
                        "content": "Réponds uniquement à partir des entrées approuvées de la FAQ.",
                    },
                    {"role": "user", "content": question},
                ],
                at=utcnow() - timedelta(days=days),
                user_id=self.users[PATIENT_EMAIL].id,
                response=response,
                error=error,
            )


async def seed_modules(
    users: dict[str, User], patients: dict[str, Patient], created: Counter, existing: Counter
) -> None:
    """Insert the missing module records. `patients` is keyed by `patient_key`."""
    await ModuleSeeder(users, patients, created, existing).run()
