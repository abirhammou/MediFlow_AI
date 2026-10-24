# MediFlow AI — setup kit

Stack: **Angular** (frontend) · **Python / FastAPI** (backend) · **MongoDB 7** (database)

## What's in this folder
| Path | What it is |
|---|---|
| `database/mongo-init.js` | Creates the 14 MongoDB collections with validators, indexes and reference data. Re-runnable. |
| `docs/erd.html` | Data model diagram (open in a browser). |
| `prompts/phase1-database.md` | Claude Code prompt: Docker MongoDB + FastAPI skeleton + Beanie models + tests. |
| `prompts/phase2-login.md` | Claude Code prompt: JWT login, roles, refresh tokens + Angular login page and protected layout. |

## How to use
1. Copy this folder's contents to the root of the project repo.
2. Open Claude Code in the repo, paste `prompts/phase1-database.md` (the part below the line). Check that `pytest` passes.
3. Then paste `prompts/phase2-login.md`.

## Run the schema by hand (without Docker init)
```bash
mongosh "mongodb://localhost:27017/mediflow" database/mongo-init.js
```

## Collections by module
- **Auth**: `users` (doctors have an embedded `doctorProfile`), `refresh_tokens`, `counters`
- **Patient Records AI**: `patients`, `patient_summaries`
- **Appointment Manager AI**: `appointments`, `appointment_requests`
- **ReportWriter AI**: `medical_reports`
- **MedDoc AI**: `medical_documents` (embedded `extractedFields`), `document_categories`
- **FollowUp AI**: `followup_tasks`, `reminders`
- **ClinicFAQ AI**: `faq_entries`
- **All modules**: `llm_interactions` (log of every LLM call)

## Rules shared by the team
- Field names are camelCase and must match the validators exactly (unknown fields are rejected).
- AI outputs are saved as `DRAFT` and only count once a user sets them to `VALIDATED`.
- Patients are never hard-deleted (`deletedAt`).
