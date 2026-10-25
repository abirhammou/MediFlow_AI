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
    patient_name: str = Field(min_length=1, max_length=200)
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
    patient_name: str
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
