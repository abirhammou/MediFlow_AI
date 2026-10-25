Branch: patient-record-module. Repo: C:\MediFlow_AI (FastAPI + Beanie/MongoDB backend, Angular frontend). Work in 5 sequential steps; finish, test (pytest + ng build) and summarize each step before starting the next. Ask me before any destructive or schema-breaking change.

## Step 0 — Read first (no code yet)
Read: database/mongo-init.js (strict validators, additionalProperties:false — every new collection/field must be added there first), backend/app/dependencies.py (require_roles, owns_patient_record), backend/app/modules/auth/models.py (Role already has ADMIN, SECRETARY, DOCTOR, ADMIN_STAFF, PATIENT; User.patient_id exists), modules/patients (router PATIENT_ROLES, summary_service.py), modules/reports (service.py, router.py, pdf.py), modules/discovery.py (a folder with router.py is auto-mounted at /api/<folder>), app/llm/service.py (generate_json + anonymizer), tests/ and frontend/src/app/features/patients (patient-detail, patient-permissions.ts). modules/documents is the separate MedDoc AI feature: do NOT overload it. Give me a short plan, then implement.

## Step 1 — Reports in the patient card (doctor read-all, edit-own)
URL: http://localhost:4200/patients/:id (features/patients/patient-detail).
- Backend (modules/reports/service.py): today _can_read and list restrict a DOCTOR to reports where doctor_id == user.id. Change: a DOCTOR can read ALL reports of a patient (any author, FINAL and DRAFT, archived hidden); update/generate/finalize/archive stay author-only (admin allowed where already allowed). Secretary and patient stay FINAL-only. Add author name (doctorName) and an "isMine" flag to ReportListItem.
- Frontend: a "Comptes rendus" section in the patient card listing every report (title, author doctor, date, status, open + PDF). Edit/finalize buttons only on the doctor's own reports; others are read-only. Mirror the rule in patient-permissions.ts.
- Tests: doctor B reads doctor A's report for the same patient but gets 403 on edit/finalize; secretary/patient still FINAL-only.

## Step 2 — Patient files with categories (new module modules/patient_files)
- Mongo collection patient_files: patientId, category ADMINISTRATIVE|MEDICAL, type (INSURANCE, ACCOUNT, INVOICE, BILL, SCAN, LAB_RESULT, IMAGING, OTHER), title, storage path, mime, size, sha256, extractedText?, uploadedBy, timestamps, deletedAt. Indexes (patientId, category).
- Storage behind a small storage.py (local volume), mime/size validation, authenticated download endpoint only.
- Access matrix in one dict like PATIENT_ROLES: ADMINISTRATIVE write SECRETARY/ADMIN, read SECRETARY/ADMIN/PATIENT(own), doctor 403. MEDICAL write SECRETARY/ADMIN, read DOCTOR/SECRETARY/ADMIN/PATIENT(own). Filter lists by allowed categories server-side.
- Endpoints: upload, list per patient, download, soft delete. Frontend "Documents" tab in the patient card with category filter; upload for secretary/admin, read-only for doctor.
- Seed demo files; tests for the role x category matrix and cross-patient access.

## Step 3 — AI history summary + patient chat (doctors)
- Text extraction on upload: PDF via pypdf; images via OCR (propose Tesseract in the Dockerfile or the LLM vision model, and ask me).
- Summarize all reports of a patient (timeline) and one report. Patient chat: answers grounded ONLY in the patient's reports, administrativeNotes and extracted MEDICAL file text; cite sources; answer "not found" when absent; never include billing/administrative files. Chunk / summarize-then-answer for long histories.
- Reuse app/llm/service.generate_json (anonymizer + provider fallback) and the summary_service DRAFT->validate pattern for stored summaries; chat is ephemeral and logged to llm_interactions. Roles DOCTOR/ADMIN. Frontend: summary panel + chat drawer in the patient card. Tests with the LLM mocked (see tests/patients/test_summaries_api.py).

## Step 4 — Billing (modules/billing, full)
- Collections invoices (number via core/sequence.py pattern, lines, total, insuranceShare, patientShare, status DRAFT/ISSUED/PARTIAL/PAID/CANCELLED, link to appointment/follow-up) and payments (invoiceId, amount, method cash/card/transfer/cheque, receiptNumber, refundOf, createdBy). Ask me the currency; store money as integers/Decimal128.
- Partial payments, computed balance, overpayment rejected, cancel/refund with audit trail. Invoice and receipt PDFs with reportlab (reuse reports/pdf.py). Revenue-per-period and unpaid-invoices reports.
- Roles: ADMIN/SECRETARY manage; PATIENT read own; DOCTOR none. Frontend module, seed data, tests (totals, partial payments, permissions).

## Step 5 — Patient portal
- Admin/secretary create a PATIENT user linked to patient_id (activation link/temp password + reset); reuse the existing signup/login (check modules/auth and the signup page).
- PATIENT can: view own FINAL reports and MEDICAL + own ADMINISTRATIVE files, appointments/follow-ups, invoices/receipts, and book appointments. modules/appointments has models/repository but no router: build it using doctor availabilities, no double booking, creating an appointment request the secretary confirms. Always scope with owns_patient_record.
- Frontend: patient shell/layout, role guards, pages: my records, appointments + booking, invoices/receipts.
- Security tests: a patient can never read another patient's data (parametrize across all endpoints).

After each step: run backend pytest and ng build, list changed files and manual test steps per role (like prompts/Patient_Records_Manual_Test_Guide), then wait for my OK.
