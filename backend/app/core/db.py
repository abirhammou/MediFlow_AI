from beanie import Document, init_beanie
from fastapi import Request
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.modules.appointments.models import Appointment, AppointmentRequest
from app.modules.auth.models import Counter, RefreshToken, User
from app.modules.documents.models import DocumentCategory, MedicalDocument
from app.modules.faq.models import FaqEntry
from app.modules.followup.models import FollowupTask, Reminder
from app.modules.llm.models import LlmInteraction
from app.modules.patients.models import Patient, PatientSummary
from app.modules.reports.models import MedicalReport

DOCUMENT_MODELS: list[type[Document]] = [
    User,
    RefreshToken,
    Counter,
    Patient,
    PatientSummary,
    Appointment,
    AppointmentRequest,
    MedicalReport,
    DocumentCategory,
    MedicalDocument,
    FollowupTask,
    Reminder,
    FaqEntry,
    LlmInteraction,
]


def create_client(uri: str) -> AsyncMongoClient:
    # tz_aware: dates come back as timezone-aware UTC datetimes.
    return AsyncMongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=5000)


async def init_db(database: AsyncDatabase) -> None:
    # Collections, validators and indexes are owned by database/mongo-init.js.
    await init_beanie(database=database, document_models=DOCUMENT_MODELS, skip_indexes=True)


def get_db(request: Request) -> AsyncDatabase:
    return request.app.state.db
