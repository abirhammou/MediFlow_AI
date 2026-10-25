from enum import Enum
from typing import Any

from beanie import PydanticObjectId
from pydantic import AwareDatetime, Field

from app.core.models import CreatedAtDocument, TimestampedDocument


class TaskStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class ReminderStatus(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SENT = "SENT"
    DISCARDED = "DISCARDED"


class FollowupTask(TimestampedDocument):
    patient_id: PydanticObjectId | None = None
    appointment_id: PydanticObjectId | None = None
    assigned_to: PydanticObjectId | None = None
    description: str = Field(max_length=2000)
    due_date: AwareDatetime | None = None
    status: TaskStatus = TaskStatus.TODO
    patient_name: str | None = Field(default=None, max_length=200)
    appointment_date: AwareDatetime | None = None
    appointment_reason: str | None = Field(default=None, max_length=500)
    created_by: PydanticObjectId | None = None

    class Settings:
        name = "followup_tasks"


class Reminder(CreatedAtDocument):
    appointment_id: PydanticObjectId = Field(description="must be CONFIRMED (checked in service)")
    appointment_snapshot: dict[str, Any] | None = Field(
        default=None, description="data actually given to the LLM"
    )
    content: str = Field(max_length=2000)
    status: ReminderStatus = ReminderStatus.DRAFT
    approved_by: PydanticObjectId | None = None
    sent_at: AwareDatetime | None = None

    class Settings:
        name = "reminders"
