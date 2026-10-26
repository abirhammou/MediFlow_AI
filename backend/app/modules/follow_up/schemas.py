from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    pending = "pending"
    done = "done"
    cancelled = "cancelled"


# ── CRUD ──────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    description: str = Field(min_length=1, max_length=1000)
    due_date: date
    patient_id: str = Field(min_length=1, description="ID MongoDB du patient existant")
    appointment_date: date
    appointment_reason: str = Field(min_length=1, max_length=500)


class TaskUpdate(BaseModel):
    description: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    due_date: Optional[date] = None
    status: Optional[TaskStatus] = None


class TaskListParams(BaseModel):
    """Paramètres de filtrage pour la liste des tâches."""
    status: TaskStatus | None = None


class TaskStats(BaseModel):
    """Compteurs par statut."""
    total: int
    pending: int
    done: int
    cancelled: int


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    description: str
    due_date: date
    status: TaskStatus
    # Patient lié (vide pour les anciennes tâches sans patient_id)
    patient_id: str = ""
    patient_name: str = ""
    patient_record_number: str = ""
    appointment_date: date
    appointment_reason: str


# ── LLM ───────────────────────────────────────────────────────────────────────

class ReminderRequest(BaseModel):
    """Données d'un rendez-vous confirmé à partir desquelles générer le rappel."""
    patient_name: str = Field(min_length=1, max_length=200)
    appointment_date: date
    appointment_reason: str = Field(min_length=1, max_length=500)


class ReminderDraft(BaseModel):
    """Brouillon de rappel administratif généré par le LLM."""
    subject: str = Field(
        description="Objet court du rappel (max 120 caractères)", max_length=120
    )
    body: str = Field(
        description="Corps du message de rappel (quelques phrases concises)"
    )


# ── Rappels sauvegardés ────────────────────────────────────────────────────────

class ReminderStep(str, Enum):
    """Étapes du workflow de validation d'un rappel."""
    draft     = "draft"      # 1. Brouillon généré par le LLM
    reviewed  = "reviewed"   # 2. Vérifié par un agent
    approved  = "approved"   # 3. Approuvé pour envoi
    exported  = "exported"   # 4. Exporté (PDF / Word / Email)


class SavedReminderCreate(BaseModel):
    """Données pour sauvegarder un rappel généré."""
    patient_name:       str  = Field(min_length=1, max_length=200)
    appointment_date:   date
    appointment_reason: str  = Field(min_length=1, max_length=500)
    subject:            str  = Field(min_length=1, max_length=120)
    body:               str  = Field(min_length=1)


class SavedReminderUpdate(BaseModel):
    """Mise à jour d'un rappel sauvegardé (étape ou contenu)."""
    subject: Optional[str]        = Field(default=None, min_length=1, max_length=120)
    body:    Optional[str]        = Field(default=None, min_length=1)
    step:    Optional[ReminderStep] = None


class SavedReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                 str
    patient_name:       str
    appointment_date:   date
    appointment_reason: str
    subject:            str
    body:               str
    step:               ReminderStep
    created_at:         str  # ISO datetime


# ── Priorité IA ───────────────────────────────────────────────────────────────

class PriorityLevel(str, Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


class PrioritizedTask(BaseModel):
    """Une tâche avec sa priorité évaluée par Gemini."""
    task_id:            str
    patient_name:       str
    appointment_date:   str
    appointment_reason: str
    due_date:           str
    status:             str
    priority:           str = Field(description="HIGH, MEDIUM ou LOW")
    justification:      str = Field(description="Explication courte de la priorité (1 phrase)")


class PriorityResponse(BaseModel):
    """Liste triée par priorité décroissante."""
    tasks: list[PrioritizedTask]


# ── 1. Résumé historique ──────────────────────────────────────────────────────

class PatientSummaryRequest(BaseModel):
    patient_id: str
    patient_name: str


class PatientHistorySummary(BaseModel):
    patient_name: str
    summary: str = Field(description="Résumé administratif en 2-3 phrases")
    task_count: int
    last_activity: Optional[str] = None


# ── 2. Prédiction no-show ─────────────────────────────────────────────────────

class NoShowRequest(BaseModel):
    patient_id: str
    patient_name: str
    next_appointment: str
    next_reason: str


class NoShowPrediction(BaseModel):
    patient_name: str
    probability: PriorityLevel  # réutilise HIGH / MEDIUM / LOW
    justification: str
    recommendation: str = Field(description="Action concrète recommandée")


# ── 3. Planification automatique ──────────────────────────────────────────────

class ScheduleRequest(BaseModel):
    start_date: str = Field(description="Date de début YYYY-MM-DD")
    end_date:   str = Field(description="Date de fin YYYY-MM-DD")


class ScheduledCall(BaseModel):
    task_id:      str
    patient_name: str
    suggested_day: str
    time_slot:    str = Field(description="matin / après-midi / soir")
    reason:       str = Field(description="Pourquoi ce positionnement")


class ScheduleResponse(BaseModel):
    calls: list[ScheduledCall]


# ── 4. Rappel à ton adaptatif ────────────────────────────────────────────────

class AdaptiveToneRequest(BaseModel):
    patient_id:         str
    patient_name:       str
    appointment_date:   str
    appointment_reason: str


class AdaptiveReminderDraft(BaseModel):
    subject:    str = Field(max_length=120)
    body:       str
    tone_used:  str = Field(description="formel / chaleureux / urgent — ton choisi par l'IA")
    tone_reason: str = Field(description="Pourquoi ce ton a été choisi")


# ── 5. Patients perdus de vue ─────────────────────────────────────────────────

class LostPatientMessage(BaseModel):
    patient_name: str
    days_inactive: int
    last_reason:  Optional[str] = None
    message:      str = Field(description="Message de reprise de contact")


class LostPatientsResponse(BaseModel):
    patients: list[LostPatientMessage]


# ── 6. Rapport hebdomadaire ───────────────────────────────────────────────────

class WeeklyReportRequest(BaseModel):
    week_start: str = Field(description="Date de début YYYY-MM-DD")
    week_end:   str = Field(description="Date de fin YYYY-MM-DD")


class WeeklyReport(BaseModel):
    week_start:      str
    week_end:        str
    activity_summary: str
    at_risk_patients: str
    trends:          str
    recommendations: str
