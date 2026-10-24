from __future__ import annotations

from datetime import date
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
