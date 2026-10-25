from __future__ import annotations

from typing import Optional

from beanie import PydanticObjectId
from bson import ObjectId
from bson.errors import InvalidId

from app.errors import APIError
from app.llm.service import generate_json
from app.modules.follow_up.prompts import (
    ADAPTIVE_TONE_SYSTEM,
    LOST_PATIENTS_SYSTEM,
    NO_SHOW_SYSTEM,
    PATIENT_SUMMARY_SYSTEM,
    PRIORITY_SYSTEM_PROMPT,
    SCHEDULE_SYSTEM,
    SYSTEM_PROMPT,
    WEEKLY_REPORT_SYSTEM,
    adaptive_tone_prompt,
    lost_patients_prompt,
    no_show_prompt,
    patient_summary_prompt,
    priority_prompt,
    reminder_prompt,
    schedule_prompt,
    weekly_report_prompt,
)
from app.modules.follow_up.repository import TaskRepository
from app.modules.follow_up.schemas import (
    AdaptiveToneRequest,
    AdaptiveReminderDraft,
    LostPatientsResponse,
    LostPatientMessage,
    NoShowPrediction,
    NoShowRequest,
    PatientSummaryRequest,
    PatientHistorySummary,
    PriorityResponse,
    ReminderDraft,
    ReminderRequest,
    ScheduleRequest,
    ScheduleResponse,
    TaskCreate,
    TaskOut,
    TaskStats,
    TaskStatus,
    TaskUpdate,
    WeeklyReport,
    WeeklyReportRequest,
)
from app.modules.patients.models import Patient


def _serialize(document: dict) -> TaskOut:
    return TaskOut(
        id=str(document["_id"]),
        description=document["description"],
        due_date=document["due_date"],
        status=TaskStatus(document["status"]),
        patient_id=document.get("patient_id", ""),
        patient_name=document.get("patient_name", ""),
        patient_record_number=document.get("patient_record_number", ""),
        appointment_date=document["appointment_date"],
        appointment_reason=document["appointment_reason"],
    )


async def _resolve_patient(patient_id: str) -> Patient:
    """Charge le patient depuis MongoDB (Beanie). Lève 404 si introuvable."""
    try:
        oid = PydanticObjectId(patient_id)
    except Exception:
        raise APIError(404, "patient_not_found", "Patient introuvable.") from None
    patient = await Patient.get(oid)
    if patient is None or patient.deleted_at is not None:
        raise APIError(404, "patient_not_found", "Patient introuvable.")
    return patient


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def create(self, task: TaskCreate) -> TaskOut:
        # Résoudre le patient réel
        patient = await _resolve_patient(task.patient_id)
        document = {
            "description":         task.description,
            "due_date":            task.due_date.isoformat(),
            "patient_id":          task.patient_id,
            "patient_name":        f"{patient.first_name} {patient.last_name}",
            "patient_record_number": patient.record_number,
            "appointment_date":    task.appointment_date.isoformat(),
            "appointment_reason":  task.appointment_reason,
            "status":              TaskStatus.pending.value,
        }
        return _serialize(await self.repository.create(document))

    async def list(self, status: Optional[TaskStatus] = None) -> list[TaskOut]:
        if status is not None:
            docs = await self.repository.list_by_status(status.value)
        else:
            docs = await self.repository.list()
        return [_serialize(doc) for doc in docs]

    async def list_by_patient(self, patient_id: str) -> list[TaskOut]:
        docs = await self.repository.list_by_patient(patient_id)
        return [_serialize(doc) for doc in docs]

    async def stats(self) -> TaskStats:
        data = await self.repository.stats()
        return TaskStats(**data)

    async def get(self, task_id: str) -> TaskOut:
        document = await self._get_document(task_id)
        return _serialize(document)

    async def update(self, task_id: str, changes: TaskUpdate) -> TaskOut:
        await self._validate_id(task_id)
        document = await self.repository.update(task_id, changes)
        if document is None:
            raise APIError(404, "task_not_found", "Tâche introuvable.")
        return _serialize(document)

    async def delete(self, task_id: str) -> None:
        await self._validate_id(task_id)
        if not await self.repository.delete(task_id):
            raise APIError(404, "task_not_found", "Tâche introuvable.")

    # ── LLM ───────────────────────────────────────────────────────────────────

    async def generate_reminder(self, request: ReminderRequest) -> ReminderDraft:
        """
        Génère un brouillon de rappel administratif personnalisé à partir
        des données d'un rendez-vous confirmé.
        Garde-fou : seules les données fournies dans `request` sont transmises au LLM.
        """
        return await generate_json(
            module="follow_up",
            system=SYSTEM_PROMPT,
            user=reminder_prompt(
                patient_name=request.patient_name,
                appointment_date=request.appointment_date.isoformat(),
                appointment_reason=request.appointment_reason,
            ),
            output_schema=ReminderDraft,
        )

    # ── Priorité ──────────────────────────────────────────────────────────────

    async def prioritize_tasks(self) -> PriorityResponse:
        """Gemini classe les tâches pending par priorité (HIGH/MEDIUM/LOW)."""
        import json as _json
        from datetime import date as _date

        docs = await self.repository.list_by_status("pending")
        if not docs:
            return PriorityResponse(tasks=[])

        tasks_data = [
            {
                "task_id":           str(doc["_id"]),
                "patient_name":      doc.get("patient_name", ""),
                "appointment_date":  doc.get("appointment_date", ""),
                "appointment_reason": doc.get("appointment_reason", ""),
                "due_date":          doc.get("due_date", ""),
                "status":            doc.get("status", "pending"),
            }
            for doc in docs
        ]

        return await generate_json(
            module="follow_up",
            system=PRIORITY_SYSTEM_PROMPT,
            user=priority_prompt(
                tasks_json=_json.dumps(tasks_data, ensure_ascii=False, indent=2),
                today=_date.today().isoformat(),
            ),
            output_schema=PriorityResponse,
        )

    # ── 1. Résumé historique patient ─────────────────────────────────────────

    async def patient_history_summary(self, req: PatientSummaryRequest) -> PatientHistorySummary:
        """Gemini lit l'historique des tâches du patient et génère un résumé en 2-3 phrases."""
        import json as _json
        docs = await self.repository.list_by_patient(req.patient_id)
        if not docs:
            return PatientHistorySummary(
                patient_name=req.patient_name,
                summary="Aucune tâche de suivi enregistrée pour ce patient.",
                task_count=0,
            )
        last_activity = max((d.get("appointment_date", "") for d in docs), default=None)
        tasks_data = [
            {
                "date": d.get("appointment_date", ""),
                "reason": d.get("appointment_reason", ""),
                "status": d.get("status", ""),
                "due_date": d.get("due_date", ""),
            }
            for d in docs
        ]
        result = await generate_json(
            module="follow_up",
            system=PATIENT_SUMMARY_SYSTEM,
            user=patient_summary_prompt(req.patient_name, _json.dumps(tasks_data, ensure_ascii=False)),
            output_schema=PatientHistorySummary,
        )
        result.task_count = len(docs)
        result.patient_name = req.patient_name
        result.last_activity = last_activity
        return result

    # ── 2. Prédiction no-show ─────────────────────────────────────────────────

    async def predict_no_show(self, req: NoShowRequest) -> NoShowPrediction:
        """Gemini évalue la probabilité que le patient ne se présente pas."""
        import json as _json
        docs = await self.repository.list_by_patient(req.patient_id)
        tasks_data = [
            {"date": d.get("appointment_date", ""), "reason": d.get("appointment_reason", ""), "status": d.get("status", "")}
            for d in docs
        ]
        return await generate_json(
            module="follow_up",
            system=NO_SHOW_SYSTEM,
            user=no_show_prompt(
                patient_name=req.patient_name,
                tasks_json=_json.dumps(tasks_data, ensure_ascii=False),
                next_appointment=req.next_appointment,
                next_reason=req.next_reason,
            ),
            output_schema=NoShowPrediction,
        )

    # ── 3. Planification automatique ─────────────────────────────────────────

    async def schedule_reminders(self, req: ScheduleRequest) -> ScheduleResponse:
        """Gemini propose un calendrier optimisé des rappels pour la période donnée."""
        import json as _json
        docs = await self.repository.list_by_status("pending")
        if not docs:
            return ScheduleResponse(calls=[])
        tasks_data = [
            {
                "task_id": str(d["_id"]),
                "patient_name": d.get("patient_name", ""),
                "due_date": d.get("due_date", ""),
                "appointment_reason": d.get("appointment_reason", ""),
            }
            for d in docs
        ]
        return await generate_json(
            module="follow_up",
            system=SCHEDULE_SYSTEM,
            user=schedule_prompt(
                tasks_json=_json.dumps(tasks_data, ensure_ascii=False),
                start_date=req.start_date,
                end_date=req.end_date,
            ),
            output_schema=ScheduleResponse,
        )

    # ── 4. Rappel à ton adaptatif ─────────────────────────────────────────────

    async def adaptive_reminder(self, req: AdaptiveToneRequest) -> AdaptiveReminderDraft:
        """Gemini choisit le ton (formel/chaleureux/urgent) selon le profil du patient."""
        from datetime import date as _date
        docs = await self.repository.list_by_patient(req.patient_id)
        task_count = len(docs)
        today = _date.today().isoformat()
        is_overdue = any(d.get("due_date", "9999") < today and d.get("status") == "pending" for d in docs)
        # Déduire la priorité depuis les tâches
        priority = "HIGH" if is_overdue else ("MEDIUM" if task_count > 2 else "LOW")
        return await generate_json(
            module="follow_up",
            system=ADAPTIVE_TONE_SYSTEM,
            user=adaptive_tone_prompt(
                patient_name=req.patient_name,
                appointment_date=req.appointment_date,
                appointment_reason=req.appointment_reason,
                task_count=task_count,
                is_overdue=is_overdue,
                priority=priority,
            ),
            output_schema=AdaptiveReminderDraft,
        )

    # ── 5. Patients perdus de vue ─────────────────────────────────────────────

    async def detect_lost_patients(self, inactivity_days: int = 30) -> LostPatientsResponse:
        """Gemini génère des messages de reprise de contact pour les patients inactifs."""
        import json as _json
        from datetime import date as _date, timedelta
        threshold = (_date.today() - timedelta(days=inactivity_days)).isoformat()
        all_docs = await self.repository.list()
        # Grouper par patient_id et trouver la dernière activité
        patients: dict[str, dict] = {}
        for doc in all_docs:
            pid = doc.get("patient_id", "")
            if not pid:
                continue
            appt = doc.get("appointment_date", "")
            if pid not in patients or appt > patients[pid]["last_date"]:
                patients[pid] = {
                    "patient_name": doc.get("patient_name", ""),
                    "last_date": appt,
                    "last_reason": doc.get("appointment_reason", ""),
                    "patient_id": pid,
                }
        # Filtrer ceux dont la dernière activité est avant le seuil
        lost = [p for p in patients.values() if p["last_date"] < threshold]
        if not lost:
            return LostPatientsResponse(patients=[])
        # Calculer jours d'inactivité
        for p in lost:
            from datetime import datetime as _dt
            try:
                delta = (_date.today() - _dt.fromisoformat(p["last_date"]).date()).days
            except Exception:
                delta = inactivity_days
            p["days_inactive"] = delta

        return await generate_json(
            module="follow_up",
            system=LOST_PATIENTS_SYSTEM,
            user=lost_patients_prompt(
                patients_json=_json.dumps(lost, ensure_ascii=False),
                today=_date.today().isoformat(),
                inactivity_days=inactivity_days,
            ),
            output_schema=LostPatientsResponse,
        )

    # ── 6. Rapport hebdomadaire ───────────────────────────────────────────────

    async def weekly_report(self, req: WeeklyReportRequest) -> WeeklyReport:
        """Gemini génère un rapport narratif de la semaine écoulée."""
        import json as _json
        all_docs = await self.repository.list()
        # Filtrer les tâches de la semaine
        week_docs = [
            d for d in all_docs
            if req.week_start <= d.get("appointment_date", "") <= req.week_end
        ]
        stats = {
            "total_tasks": len(week_docs),
            "pending":   sum(1 for d in week_docs if d.get("status") == "pending"),
            "done":      sum(1 for d in week_docs if d.get("status") == "done"),
            "cancelled": sum(1 for d in week_docs if d.get("status") == "cancelled"),
            "patients":  list({d.get("patient_name", "") for d in week_docs}),
            "reasons":   [d.get("appointment_reason", "") for d in week_docs],
        }
        result = await generate_json(
            module="follow_up",
            system=WEEKLY_REPORT_SYSTEM,
            user=weekly_report_prompt(
                stats_json=_json.dumps(stats, ensure_ascii=False),
                week_start=req.week_start,
                week_end=req.week_end,
            ),
            output_schema=WeeklyReport,
        )
        result.week_start = req.week_start
        result.week_end = req.week_end
        return result
        """
        Demande à Gemini de classer toutes les tâches pending par ordre de priorité.
        Garde-fou : seules les données existantes en base sont transmises.
        """
        from datetime import date as _date
        import json as _json

        docs = await self.repository.list_by_status("pending")
        if not docs:
            return PriorityResponse(tasks=[])

        tasks_data = [
            {
                "task_id":          str(doc["_id"]),
                "patient_name":     doc.get("patient_name", ""),
                "appointment_date": doc.get("appointment_date", ""),
                "appointment_reason": doc.get("appointment_reason", ""),
                "due_date":         doc.get("due_date", ""),
                "status":           doc.get("status", "pending"),
            }
            for doc in docs
        ]

        return await generate_json(
            module="follow_up",
            system=PRIORITY_SYSTEM_PROMPT,
            user=priority_prompt(
                tasks_json=_json.dumps(tasks_data, ensure_ascii=False, indent=2),
                today=_date.today().isoformat(),
            ),
            output_schema=PriorityResponse,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_document(self, task_id: str) -> dict:
        await self._validate_id(task_id)
        document = await self.repository.get(task_id)
        if document is None:
            raise APIError(404, "task_not_found", "Tâche introuvable.")
        return document

    @staticmethod
    async def _validate_id(task_id: str) -> None:
        try:
            ObjectId(task_id)
        except (InvalidId, TypeError):
            raise APIError(404, "task_not_found", "Tâche introuvable.") from None
