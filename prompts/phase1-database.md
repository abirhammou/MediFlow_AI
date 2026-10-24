# Claude Code prompt — Phase 1: Database setup (MediFlow AI)

> Unzip `mediflow-setup` at the root of your project repo, then copy everything below the line into Claude Code.

---

You are setting up the database layer for **MediFlow AI**, a group academic project: a clinic management web app with 6 modules (Appointment Manager AI, Patient Records AI, ReportWriter AI, MedDoc AI, FollowUp AI, ClinicFAQ AI). Each module = classic CRUD + one LLM task. All patient data is fictitious.

This phase is **database + backend skeleton only**. Do not build auth, CRUD endpoints or UI yet.

## Stack
- Database: MongoDB 7 (Docker Compose)
- Backend: Python 3.12, **FastAPI**, Pydantic v2, **Beanie** ODM (async), `pydantic-settings`, `uv` (or pip + `requirements.txt`)
- Tests: pytest + pytest-asyncio + `testcontainers[mongodb]`
- Frontend (Phase 2): Angular 17+

## Target layout
```
/backend        FastAPI app
/frontend       Angular app (Phase 2)
/database       mongo-init.js (+ 00-create-user.js you write)
/docs           erd.html (data model diagram)
/prompts        these prompts
docker-compose.yml   .env.example   README.md
```

## Before you write anything
1. Inspect the repo. If a backend already exists, extend it instead of creating a new one, and tell me what you found.
2. Read `database/mongo-init.js` completely. It is the **source of truth** for collection names, field names (camelCase), enum values, validators and indexes. Do not rename anything. Every collection has `additionalProperties: false`, so a model field that is not in the validator makes inserts fail.
3. Open `docs/erd.html` for the overview.

## Tasks
1. **Docker Compose** — `docker-compose.yml`:
   - `mongo:7`, root user/password from `.env`, named volume, healthcheck (`mongosh --quiet --eval "db.adminCommand('ping')"`), port 27017, `MONGO_INITDB_DATABASE=mediflow`.
   - Mount `database/` into `/docker-entrypoint-initdb.d/` so the scripts run on first start, in order: `00-create-user.js` (you write it: user `mediflow_app`, `readWrite` on `mediflow` only, password from env) then `mongo-init.js`.
   - `mongo-express` on port 8081 under profile `tools`.
   - `.env.example` with placeholders; `.env` in `.gitignore`.
2. **Backend skeleton** in `backend/app/`:
   - `core/config.py`: `Settings` (pydantic-settings) reading `MONGODB_URI`, `MONGODB_DB=mediflow`, `ENV`.
   - `core/db.py`: create the async client and call `init_beanie` on app startup (FastAPI `lifespan`). The app connects as `mediflow_app`, never root.
   - `main.py`: FastAPI app, CORS for `http://localhost:4200`, `GET /api/health` that pings Mongo.
3. **Beanie models**, one package per module under `app/modules/`:
   - `auth/models.py`: `User` (embedded `DoctorProfile`, `Availability`), `RefreshToken`, `Counter`
   - `patients/models.py`: `Patient` (embedded `Address`, `Insurance`, `EmergencyContact`), `PatientSummary`
   - `appointments/models.py`: `Appointment`, `AppointmentRequest` (embedded `ParsedRequest`)
   - `reports/models.py`: `MedicalReport` · `meddoc/models.py`: `MedicalDocument` (embedded `ExtractedField`), `DocumentCategory`
   - `followup/models.py`: `FollowupTask`, `Reminder` · `faq/models.py`: `FaqEntry` · `llm/models.py`: `LlmInteraction`
   - `class Settings: name = "<exact collection name>"`. **Do not declare indexes in Beanie** (they are owned by `mongo-init.js`).
   - References are `PydanticObjectId` (the validators require `objectId`, not strings). Enums are `str, Enum` classes with the exact values from the script.
   - **Gotchas**: BSON has no date-only type, so store `dateOfBirth` as a `datetime` at midnight UTC and expose it as `date` in API schemas. Use timezone-aware UTC datetimes. Optional fields may be saved as `null` (the validators allow it).
   - Shared `TimestampedDocument` base setting `createdAt`/`updatedAt` with Beanie `@before_event(Insert, Replace, Save)` hooks. Email always lowercased before save.
   - Keep DB field names camelCase as in the script (`first_name: str = Field(alias="firstName")` or camelCase attributes, choose one convention and apply it everywhere).
4. **Sequence service** — `app/core/sequence.py`: `next_record_number()` doing an atomic `find_one_and_update` with `$inc` on `counters` `{_id: "patient_record"}` (upsert, return the new doc), formatted `PAT-{year}-{00001}`.
5. **Repository helpers** (plain async functions, one file per module) for what later phases need:
   - `get_user_by_email`
   - patients: paginated list excluding soft-deleted (`deletedAt: null`), text search on name / record number, `get_patient(id)` excluding deleted
   - summaries: latest by patient, the `VALIDATED` one
   - appointments: overlap check for a doctor (`startAt < end and endAt > start`, status ≠ CANCELLED)
   - faq: approved entries + text search
6. **Tests** (`backend/tests/`) with a `mongo:7` Testcontainer; a session fixture runs `mongo-init.js` inside the container (`mongosh` exec) before `init_beanie`:
   - insert and read back one document of each model (proves models match validators),
   - second `VALIDATED` summary for the same patient raises `DuplicateKeyError`,
   - 20 concurrent `next_record_number()` calls return 20 distinct numbers,
   - soft-deleted patient excluded from the list.
7. `README.md` section **"Database"**: start Mongo, the init scripts run only on first start, reset with `docker compose down -v`, open mongo-express, run the backend (`uvicorn app.main:app --reload`) and the tests.

## Rules
- Schema changes: edit `database/mongo-init.js` (re-runnable, uses `collMod`) and tell me why. Never relax a validator to make a test pass; fix the model.
- No secrets in git. Type hints everywhere, `ruff` for lint/format.
- Code in English, seed data in French.

## Done when
- `docker compose up -d` gives a healthy Mongo with 14 collections and their indexes.
- `uvicorn app.main:app --reload` starts and `GET /api/health` returns ok.
- `pytest` passes.

Finish with a short summary: files created, how to run, and anything in `mongo-init.js` you think should change (suggest it, don't change it).
