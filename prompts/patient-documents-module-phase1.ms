# Claude Code prompt — Patient Records module, Phase 1: CRUD (MediFlow AI)

> Run this only after the database phase and the login phase are done (Mongo healthy, `pytest` green, login works).
> Work on my branch `mokhtar_driss`. Copy everything below the line into Claude Code from the repo root.

---

You are implementing the **Patient Records module (CRUD only)** for **MediFlow AI** (clinic management app, academic group project, all patient data fictitious). Earlier phases already created:
- `database/mongo-init.js`: the `patients` collection with a strict `$jsonSchema` validator (`additionalProperties: false`) and indexes (`uq_patients_record`, partial unique `uq_patients_national_id`, `idx_patients_name`, `idx_patients_deleted`, `txt_patients_search`)
- Beanie models in `backend/app/modules/patients/models.py` (`Patient`, embedded `Address`, `Insurance`, `EmergencyContact`)
- `app/core/sequence.py` (`next_record_number()` → `PAT-2026-00001`), the patients repository helpers
- auth: `get_current_user`, `require_roles(...)`, the error format `{timestamp, status, error, message, path}`
- Angular: `AuthService`, `authInterceptor`, `authGuard`, `roleGuard`, layout shell with a placeholder `/patients` page

Reuse all of these. Do not redefine the models or the auth.

## Out of scope (do NOT build)
- Anything LLM / AI: no `patient_summaries` generation, no LLM calls, no `llm_interactions` writes.
- Do not write `currentSummaryId` (leave it `null`; just return it in the API).
- `administrativeNotes` is a plain text field for now.
- Other modules (appointments, documents…).

## Before you write anything
1. Read `database/mongo-init.js` (the `patients` part), the Phase 1 models and repository, and the auth `deps.py`. Every field you save must exist in the validator.
2. Check the Angular app structure and the existing `/patients` placeholder route.
3. Give me a short plan (endpoints, files, Angular components), then implement it.

## Backend (`backend/app/modules/patients/`)

### 1. Schemas (`schemas.py`, Pydantic v2)
- API JSON is camelCase (same convention as the rest of the app).
- `PatientCreate`, `PatientUpdate` (all fields optional, PATCH semantics), `PatientOut`, `PatientListItem` (id, recordNumber, firstName, lastName, dateOfBirth, age, gender, phone, city), generic `Page[T]` `{items, total, page, size}`.
- `dateOfBirth` is a `date` in the API, stored as `datetime` at **midnight UTC** in Mongo (convert both ways in one helper).
- Validation (French error messages):
  - firstName / lastName: trimmed, 1–80 chars
  - dateOfBirth: not in the future, not more than 130 years ago
  - gender: `MALE | FEMALE | OTHER`; bloodType: exact enum from the script or null
  - nationalId: optional, 8 digits (fictitious CIN)
  - email: optional, valid, lowercased
  - phone fields: optional, digits / spaces / `+`, 8–20 chars
  - administrativeNotes: ≤ 5000 chars
  - empty strings → `null`; empty nested objects (`address`, `insurance`, `emergencyContact`) → `null`
- `recordNumber`, `createdBy`, `updatedBy`, `createdAt`, `updatedAt`, `deletedAt`, `currentSummaryId` are **never accepted from the client**.

### 2. Service (`service.py`)
- `create_patient(data, user)`: `recordNumber` from `next_record_number()`, set `createdBy` / `updatedBy`. A `DuplicateKeyError` on `uq_patients_national_id` → **409** "Un patient avec ce CIN existe déjà".
- `get_patient(id)`: excludes soft-deleted. Invalid ObjectId or not found → **404**.
- `list_patients(q, gender, bloodType, city, page, size, sort)`:
  - always excludes `deletedAt != null`
  - `q` search: `$text` does not match prefixes, so use a **case-insensitive anchored regex** (`re.escape`) on `lastName`, `firstName`, `recordNumber` (and `nationalId`) with `$or`. Update the existing repository helper if needed.
  - `size` default 20, max 100. Sort whitelist: `lastName`, `createdAt`, `recordNumber`, `dateOfBirth` (asc/desc), default `lastName, firstName`.
  - list projection: only the `PatientListItem` fields.
- `update_patient(id, data, user)`: partial update with `$set` (only the fields sent; explicit `null` clears an optional field), sets `updatedBy`/`updatedAt`. Deleted patient → 404. `recordNumber` is immutable.
- `soft_delete_patient(id, user)`: sets `deletedAt` and `updatedBy`. No hard delete.
- `restore_patient(id, user)`: sets `deletedAt = null`.
- `find_possible_duplicates(firstName, lastName, dateOfBirth)`: same last name + first name (case-insensitive) + same birth date, not deleted.
- `GET /deleted` list (ADMIN) for restore.

### 3. Router `/api/patients`
Put the role matrix in one constant so it's easy to change:

| Method | Path | Roles |
|---|---|---|
| GET | `/api/patients` | SECRETARY, DOCTOR, ADMIN |
| GET | `/api/patients/{id}` | SECRETARY, DOCTOR, ADMIN |
| GET | `/api/patients/duplicates?firstName=&lastName=&dateOfBirth=` | SECRETARY, ADMIN |
| POST | `/api/patients` → 201 | SECRETARY, ADMIN |
| PATCH | `/api/patients/{id}` | SECRETARY, ADMIN |
| DELETE | `/api/patients/{id}` → 204 (soft) | SECRETARY, ADMIN |
| GET | `/api/patients/deleted` | ADMIN |
| POST | `/api/patients/{id}/restore` | ADMIN |

Register the router in `main.py`. Use the existing error handler format.

### 4. Dev seed
`app/scripts/seed_dev_patients.py` (`python -m app.scripts.seed_dev_patients`, and on startup only when `ENV=dev`, after the users seeder): ~15 **fictitious** patients with French/Tunisian names, varied ages/genders/blood types/cities (Tunis, Ariana, Sfax, Sousse…), some with insurance (CNAM) and emergency contacts, 2 without nationalId. Idempotent (skip if a patient with that nationalId / name+birthdate already exists). Record numbers via `next_record_number()`.

### 5. Tests (`backend/tests/patients/`, httpx `AsyncClient` + Mongo Testcontainer with `mongo-init.js`)
- create → 201, record number format `PAT-YYYY-NNNNN`, `createdBy` set, dateOfBirth round-trips as the same date
- validation: future birth date, bad CIN, bad email → 422 with field messages
- duplicate nationalId → 409; two patients without nationalId → OK
- get unknown / invalid id → 404
- list: pagination, total, search by name prefix, search by record number, filters, soft-deleted excluded
- PATCH: partial update keeps other fields, `null` clears an optional field, `recordNumber` in body ignored/rejected
- soft delete → 404 on get, appears in `/deleted`, restore works
- roles: DOCTOR can read but gets 403 on POST/PATCH/DELETE; no token → 401; non-ADMIN → 403 on restore

## Frontend (`frontend/src/app/features/patients/`, Angular 17+, standalone, signals, French UI)
1. `patient.model.ts` (interfaces matching the API) and `PatientService` (HttpClient, `withCredentials`, `environment.apiUrl`).
2. Lazy routes under `/patients`, protected by `authGuard` + `roleGuard(['SECRETARY','DOCTOR','ADMIN'])`, replacing the placeholder:
   - `/patients` list · `/patients/new` · `/patients/:id` detail · `/patients/:id/edit` · `/patients/deleted` (ADMIN)
3. **List page**: table (record number, nom, prénom, âge, sexe, téléphone, ville), search box with 300 ms debounce, filters (sexe, groupe sanguin, ville), server-side pagination and sort, click row → detail, "Nouveau patient" button. Keep search/page in the URL query params. Empty state and loading state.
4. **Form** (one reusable component for create and edit, reactive forms): sections Identité, Contact, Adresse, Assurance, Personne à contacter, Notes administratives. Same validation rules as the backend, French messages under each field, server errors (409, 422) shown on the right fields. On create, call `/duplicates` when name + birth date are filled and show a non-blocking warning with links to the matching patients. Edit sends only changed fields (PATCH). Unsaved-changes guard.
5. **Detail page**: all info in cards, age computed, record number shown prominently, buttons Modifier / Supprimer (confirm dialog, then back to list with a snackbar). Leave an empty area in the layout for the future AI summary, but don't implement it.
6. **Deleted page** (ADMIN): list + "Restaurer".
7. Hide buttons the user's role can't use (the backend still enforces it).
8. **Date gotcha**: the clinic is in UTC+1. Send `dateOfBirth` as a `'YYYY-MM-DD'` string and parse it without `new Date('YYYY-MM-DD')` timezone shifts, so a birth date never moves by one day.

## Rules
- Don't change the database schema. If you truly need a field, add it to the validator in `database/mongo-init.js` and tell me why.
- Never relax a validator to make a test pass; fix the code.
- Don't touch other teammates' modules beyond registering the router and the route.
- Type hints everywhere, `ruff` clean. Code in English, UI text and seed data in French.
- Small, focused commits on branch `mokhtar_driss`.

## Done when
- `pytest` passes (old tests too).
- With `uvicorn` and `ng serve`: as the secretary I can create, search, view, edit and delete a patient; as the doctor I can only view; as admin I can restore a deleted patient; a reload keeps my list filters.

Finish with: endpoints table, files created/changed, how to run the seed, and anything you'd suggest changing in the `patients` schema (suggest it, don't change it).