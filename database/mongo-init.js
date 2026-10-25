// =====================================================================
// MediFlow AI — MongoDB schema (MongoDB 7+)
// Run with:  mongosh "mongodb://localhost:27017/mediflow" mongo-init.js
// Creates every collection with a $jsonSchema validator + its indexes.
// Re-runnable: existing collections get their validator updated (collMod).
// All patient data is FICTITIOUS (academic project).
// =====================================================================

const DB_NAME = "mediflow";
const mediflow = db.getSiblingDB(DB_NAME);

// ---------------------------------------------------------------------
// Shared enums (keep in sync with the Python enums)
// ---------------------------------------------------------------------
const ROLES              = ["ADMIN", "SECRETARY", "DOCTOR", "ADMIN_STAFF", "PATIENT"];
const GENDERS            = ["MALE", "FEMALE", "OTHER"];
const APPOINTMENT_STATUS = ["PENDING", "CONFIRMED", "CANCELLED", "COMPLETED", "NO_SHOW"];
const AI_REVIEW_STATUS   = ["DRAFT", "VALIDATED", "REJECTED"];
// patient_summaries only: a VALIDATED summary replaced by a newer one becomes SUPERSEDED
const SUMMARY_STATUS     = [...AI_REVIEW_STATUS, "SUPERSEDED"];
const REPORT_STATUS      = ["DRAFT", "FINAL", "ARCHIVED"];
const TASK_STATUS        = ["TODO", "IN_PROGRESS", "DONE", "CANCELLED"];
const REMINDER_STATUS    = ["DRAFT", "APPROVED", "SENT", "DISCARDED"];
const LLM_MODULES        = ["APPOINTMENT", "PATIENT_RECORD", "REPORT", "MEDDOC", "FOLLOWUP", "FAQ"];
const BLOOD_TYPES        = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];

// Small helpers to keep validators readable
const str      = (extra = {}) => ({ bsonType: "string", ...extra });
const optStr   = (extra = {}) => ({ bsonType: ["string", "null"], ...extra });
const oid      = { bsonType: "objectId" };
const optOid   = { bsonType: ["objectId", "null"] };
const date     = { bsonType: "date" };
const optDate  = { bsonType: ["date", "null"] };
const bool     = { bsonType: "bool" };
const int      = (extra = {}) => ({ bsonType: "int", ...extra });
const oneOf    = (values) => ({ bsonType: "string", enum: values });
const optOneOf = (values) => ({ bsonType: ["string", "null"], enum: [...values, null] });
const timestamps = { createdAt: date, updatedAt: date };
const HHMM = "^([01][0-9]|2[0-3]):[0-5][0-9]$";

// Create or update a collection with its validator
function defineCollection(name, required, properties) {
  const validator = {
    $jsonSchema: {
      bsonType: "object",
      required,
      properties: { _id: oid, ...properties },
      additionalProperties: false,
    },
  };
  const exists = mediflow.getCollectionNames().includes(name);
  if (exists) {
    mediflow.runCommand({ collMod: name, validator, validationLevel: "strict", validationAction: "error" });
  } else {
    mediflow.createCollection(name, { validator, validationLevel: "strict", validationAction: "error" });
  }
  print(`✔ ${name}`);
  return mediflow.getCollection(name);
}

// =====================================================================
// AUTH
// =====================================================================

// users — doctors keep their profile + weekly availability embedded;
// PATIENT accounts point to their record with patientId
const users = defineCollection(
  "users",
  ["email", "passwordHash", "firstName", "lastName", "role", "isActive", "failedLoginAttempts", "createdAt", "updatedAt"],
  {
    email: str({ pattern: "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", description: "stored lowercase" }),
    passwordHash: str({ minLength: 50, description: "BCrypt hash, never plain text" }),
    firstName: str({ maxLength: 80 }),
    lastName: str({ maxLength: 80 }),
    role: oneOf(ROLES),
    isActive: bool,
    failedLoginAttempts: int({ minimum: 0 }),
    lockedUntil: optDate,
    lastLoginAt: optDate,
    patientId: { ...optOid, description: "patients._id, only when role = PATIENT" },
    doctorProfile: {
      bsonType: ["object", "null"],
      description: "only when role = DOCTOR",
      required: ["specialty"],
      additionalProperties: false,
      properties: {
        specialty: str({ maxLength: 100 }),
        phone: optStr(),
        officeRoom: optStr(),
        availabilities: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["dayOfWeek", "startTime", "endTime", "slotMinutes"],
            additionalProperties: false,
            properties: {
              dayOfWeek: int({ minimum: 1, maximum: 7, description: "1 = Monday" }),
              startTime: str({ pattern: HHMM }),
              endTime: str({ pattern: HHMM }),
              slotMinutes: int({ minimum: 5, maximum: 240 }),
            },
          },
        },
      },
    },
    ...timestamps,
  }
);
users.createIndex({ email: 1 }, { unique: true, name: "uq_users_email" });
users.createIndex({ role: 1, isActive: 1 }, { name: "idx_users_role" });

// refresh_tokens — expired documents are removed automatically by the TTL index
const refreshTokens = defineCollection(
  "refresh_tokens",
  ["userId", "tokenHash", "expiresAt", "createdAt"],
  {
    userId: oid,
    tokenHash: str({ description: "SHA-256 of the raw token" }),
    expiresAt: date,
    revokedAt: optDate,
    replacedByTokenHash: optStr(),
    userAgent: optStr({ maxLength: 255 }),
    ipAddress: optStr({ maxLength: 45 }),
    createdAt: date,
  }
);
refreshTokens.createIndex({ tokenHash: 1 }, { unique: true, name: "uq_refresh_token_hash" });
refreshTokens.createIndex({ userId: 1 }, { name: "idx_refresh_user" });
refreshTokens.createIndex({ expiresAt: 1 }, { expireAfterSeconds: 0, name: "ttl_refresh_expires" });

// counters — sequence generator (patient record numbers PAT-2026-00001)
defineCollection("counters", ["seq"], { _id: str(), seq: { bsonType: ["int", "long"] } });

// =====================================================================
// MODULE 2 — PATIENT RECORDS AI
// =====================================================================
const patients = defineCollection(
  "patients",
  ["recordNumber", "firstName", "lastName", "dateOfBirth", "gender", "createdAt", "updatedAt"],
  {
    recordNumber: str({ pattern: "^PAT-[0-9]{4}-[0-9]{5}$" }),
    firstName: str({ maxLength: 80 }),
    lastName: str({ maxLength: 80 }),
    dateOfBirth: date,
    gender: oneOf(GENDERS),
    nationalId: optStr({ maxLength: 30, description: "fictitious CIN" }),
    phone: optStr(),
    email: optStr(),
    address: {
      bsonType: ["object", "null"],
      additionalProperties: false,
      properties: { street: optStr(), city: optStr(), postalCode: optStr() },
    },
    bloodType: optOneOf(BLOOD_TYPES),
    insurance: {
      bsonType: ["object", "null"],
      additionalProperties: false,
      properties: { provider: optStr(), number: optStr() },
    },
    emergencyContact: {
      bsonType: ["object", "null"],
      additionalProperties: false,
      properties: { name: optStr(), phone: optStr(), relation: optStr() },
    },
    administrativeNotes: optStr({ maxLength: 5000, description: "input for the LLM summary" }),
    currentSummaryId: { ...optOid, description: "points to the VALIDATED patient_summaries doc" },
    createdBy: optOid,
    updatedBy: optOid,
    deletedAt: { ...optDate, description: "soft delete" },
    ...timestamps,
  }
);
patients.createIndex({ recordNumber: 1 }, { unique: true, name: "uq_patients_record" });
patients.createIndex(
  { nationalId: 1 },
  { unique: true, name: "uq_patients_national_id", partialFilterExpression: { nationalId: { $type: "string" } } }
);
patients.createIndex({ lastName: 1, firstName: 1 }, { name: "idx_patients_name" });
patients.createIndex({ deletedAt: 1 }, { name: "idx_patients_deleted" });
patients.createIndex(
  { firstName: "text", lastName: "text", recordNumber: "text" },
  { name: "txt_patients_search", default_language: "french" }
);

// patient_summaries — every AI draft is kept; only one VALIDATED per patient
const summaries = defineCollection(
  "patient_summaries",
  ["patientId", "content", "status", "createdAt"],
  {
    patientId: oid,
    content: str({ minLength: 1, maxLength: 4000 }),
    status: oneOf(SUMMARY_STATUS),
    llmModel: optStr(),
    sourceSnapshot: { bsonType: ["object", "null"], description: "patient fields sent to the LLM" },
    generatedBy: optOid,
    reviewedBy: optOid,
    reviewedAt: optDate,
    reviewComment: optStr(),
    createdAt: date,
  }
);
summaries.createIndex({ patientId: 1, createdAt: -1 }, { name: "idx_summaries_patient" });
summaries.createIndex(
  { patientId: 1 },
  { unique: true, name: "uq_one_validated_summary", partialFilterExpression: { status: "VALIDATED" } }
);

// =====================================================================
// MODULE 1 — APPOINTMENT MANAGER AI
// =====================================================================
const appointments = defineCollection(
  "appointments",
  ["patientId", "doctorId", "startAt", "endAt", "status", "createdAt", "updatedAt"],
  {
    patientId: oid,
    doctorId: { ...oid, description: "users._id with role DOCTOR" },
    startAt: date,
    endAt: date,
    reason: optStr({ maxLength: 255 }),
    status: oneOf(APPOINTMENT_STATUS),
    cancelReason: optStr(),
    createdBy: optOid,
    ...timestamps,
  }
);
appointments.createIndex({ doctorId: 1, startAt: 1 }, { name: "idx_appt_doctor_time" });
appointments.createIndex({ patientId: 1, startAt: -1 }, { name: "idx_appt_patient" });
appointments.createIndex({ status: 1, startAt: 1 }, { name: "idx_appt_status" });

const apptRequests = defineCollection(
  "appointment_requests",
  ["rawMessage", "createdAt"],
  {
    rawMessage: str({ maxLength: 2000 }),
    parsed: {
      bsonType: ["object", "null"],
      description: "structured LLM output",
      properties: {
        preferredDate: optDate,
        dayPart: optOneOf(["MORNING", "AFTERNOON", "EVENING"]),
        doctorId: optOid,
        specialty: optStr(),
        reason: optStr(),
      },
    },
    patientId: optOid,
    appointmentId: optOid,
    createdBy: optOid,
    createdAt: date,
  }
);
apptRequests.createIndex({ createdAt: -1 }, { name: "idx_apptreq_date" });

// =====================================================================
// MODULE 3 — REPORTWRITER AI
// =====================================================================
const reports = defineCollection(
  "medical_reports",
  ["patientId", "doctorId", "title", "rawNotes", "status", "createdAt", "updatedAt"],
  {
    patientId: oid,
    doctorId: oid,
    appointmentId: optOid,
    title: str({ maxLength: 200 }),
    rawNotes: str({ description: "professional's notes = source of truth" }),
    structuredContent: optStr({ description: "LLM output, no added medical facts" }),
    status: oneOf(REPORT_STATUS),
    archivedAt: optDate,
    ...timestamps,
  }
);
reports.createIndex({ patientId: 1, createdAt: -1 }, { name: "idx_reports_patient" });
reports.createIndex({ doctorId: 1, status: 1 }, { name: "idx_reports_doctor" });

// =====================================================================
// MODULE 4 — MEDDOC AI (extracted fields embedded in the document)
// =====================================================================
const categories = defineCollection(
  "document_categories",
  ["code", "label"],
  { code: str({ pattern: "^[A-Z_]+$" }), label: str(), description: optStr() }
);
categories.createIndex({ code: 1 }, { unique: true, name: "uq_category_code" });

const documents = defineCollection(
  "medical_documents",
  ["patientId", "title", "rawText", "createdAt", "updatedAt"],
  {
    patientId: oid,
    title: str({ maxLength: 200 }),
    rawText: str(),
    filePath: optStr(),
    categoryCode: optStr({ description: "validated category (document_categories.code)" }),
    aiSuggestedCategoryCode: optStr(),
    extractedFields: {
      bsonType: "array",
      items: {
        bsonType: "object",
        required: ["name", "status"],
        additionalProperties: false,
        properties: {
          name: str({ maxLength: 80 }),
          value: optStr(),
          status: oneOf(AI_REVIEW_STATUS),
          validatedBy: optOid,
          validatedAt: optDate,
        },
      },
    },
    uploadedBy: optOid,
    ...timestamps,
  }
);
documents.createIndex({ patientId: 1, createdAt: -1 }, { name: "idx_docs_patient" });
documents.createIndex({ categoryCode: 1 }, { name: "idx_docs_category" });

// =====================================================================
// MODULE 5 — FOLLOWUP AI
// =====================================================================
const tasks = defineCollection(
  "followup_tasks",
  ["description", "status", "createdAt", "updatedAt"],
  {
    patientId: optOid,
    appointmentId: optOid,
    assignedTo: optOid,
    description: str({ maxLength: 2000 }),
    dueDate: optDate,
    status: oneOf(TASK_STATUS),
    patientName: optStr({ maxLength: 200, description: "as typed in the follow-up form" }),
    appointmentDate: optDate,
    appointmentReason: optStr({ maxLength: 500 }),
    createdBy: optOid,
    ...timestamps,
  }
);
tasks.createIndex({ assignedTo: 1, status: 1, dueDate: 1 }, { name: "idx_tasks_assignee" });
tasks.createIndex({ patientId: 1 }, { name: "idx_tasks_patient" });

const reminders = defineCollection(
  "reminders",
  ["appointmentId", "content", "status", "createdAt"],
  {
    appointmentId: { ...oid, description: "appointment must be CONFIRMED (checked in service)" },
    appointmentSnapshot: {
      bsonType: ["object", "null"],
      description: "data actually given to the LLM (guardrail traceability)",
    },
    content: str({ maxLength: 2000 }),
    status: oneOf(REMINDER_STATUS),
    approvedBy: optOid,
    sentAt: optDate,
    createdAt: date,
  }
);
reminders.createIndex({ appointmentId: 1 }, { name: "idx_reminders_appt" });

// =====================================================================
// MODULE 6 — CLINICFAQ AI
// =====================================================================
const faq = defineCollection(
  "faq_entries",
  ["question", "answer", "isApproved", "createdAt", "updatedAt"],
  {
    question: str({ maxLength: 500 }),
    answer: str({ maxLength: 4000 }),
    category: optStr(),
    isApproved: { ...bool, description: "the LLM only uses approved entries" },
    createdBy: optOid,
    ...timestamps,
  }
);
faq.createIndex(
  { question: "text", answer: "text" },
  { name: "txt_faq", default_language: "french", weights: { question: 3, answer: 1 } }
);
faq.createIndex({ isApproved: 1, category: 1 }, { name: "idx_faq_approved" });

// =====================================================================
// CROSS-CUTTING — LLM call log
// =====================================================================
const llm = defineCollection(
  "llm_interactions",
  ["module", "prompt", "success", "createdAt"],
  {
    module: oneOf(LLM_MODULES),
    userId: optOid,
    entityId: { ...optOid, description: "patient / report / document concerned" },
    prompt: str(),
    response: optStr(),
    model: optStr(),
    tokensIn: { bsonType: ["int", "null"] },
    tokensOut: { bsonType: ["int", "null"] },
    latencyMs: { bsonType: ["int", "null"] },
    success: bool,
    errorMessage: optStr(),
    createdAt: date,
  }
);
llm.createIndex({ module: 1, createdAt: -1 }, { name: "idx_llm_module_date" });
llm.createIndex({ entityId: 1 }, { name: "idx_llm_entity" });

// =====================================================================
// REFERENCE DATA (idempotent upserts)
// =====================================================================
[
  ["ORDONNANCE", "Ordonnance"],
  ["ANALYSE", "Analyse biologique"],
  ["IMAGERIE", "Imagerie"],
  ["CERTIFICAT", "Certificat médical"],
  ["COMPTE_RENDU", "Compte rendu"],
  ["ADMINISTRATIF", "Administratif"],
].forEach(([code, label]) =>
  categories.updateOne({ code }, { $setOnInsert: { code, label } }, { upsert: true })
);

mediflow.counters.updateOne({ _id: "patient_record" }, { $setOnInsert: { seq: NumberInt(0) } }, { upsert: true });

print(`\nMediFlow AI schema ready in database "${DB_NAME}".`);
