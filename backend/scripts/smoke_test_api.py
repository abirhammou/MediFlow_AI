"""Smoke test des routes MediFlow avec une base MongoDB temporaire."""

from __future__ import annotations

import os
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIRECTORY))

DATABASE_NAME = "mediflow_smoke_test"
MONGO_URI = "mongodb://localhost:27017"

os.environ["MONGO_URI"] = MONGO_URI
os.environ["MONGO_DB"] = DATABASE_NAME
os.environ["APP_ENV"] = "development"
os.environ["LLM_MOCK"] = "true"
os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"OK  {label}")
        return
    print(f"KO  {label}")
    raise AssertionError(label)


def operation_request_schema(operation: dict[str, Any]) -> str:
    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {})
    for media_type in content.values():
        schema = media_type.get("schema", {})
        reference = schema.get("$ref")
        if reference:
            return reference.rsplit("/", 1)[-1]
        if schema:
            return str(schema)
    return "-"


def report_routes(app: Any) -> None:
    paths = app.openapi()["paths"]
    role_by_route = {
        ("GET", "/api/users"): "admin",
        ("POST", "/api/users"): "admin",
        ("GET", "/api/users/{user_id}"): "admin",
        ("PATCH", "/api/users/{user_id}/approve"): "admin",
        ("PATCH", "/api/users/{user_id}/disable"): "admin",
        ("PATCH", "/api/users/{user_id}/enable"): "admin",
        ("PATCH", "/api/users/{user_id}/role"): "admin",
        ("DELETE", "/api/users/{user_id}"): "admin",
        ("PATCH", "/api/users/{user_id}/link-patient"): "admin, secretary",
        ("PATCH", "/api/users/{user_id}/unlink-patient"): "admin, secretary",
        ("GET", "/api/dashboard/summary"): "authenticated, active",
        ("GET", "/api/auth/me"): "authenticated, active",
        ("POST", "/api/auth/change-password"): "authenticated, active",
    }
    print("Routes OpenAPI (méthode | chemin | rôles | schéma du corps)")
    for route_path, operations in paths.items():
        for method, operation in operations.items():
            if method.lower() not in {
                "get",
                "post",
                "put",
                "patch",
                "delete",
                "options",
                "head",
            }:
                continue
            route_key = (method.upper(), route_path)
            roles = role_by_route.get(route_key, "public")
            body_schema = operation_request_schema(operation)
            print(f"  {method.upper():6} {route_path:42} {roles:23} {body_schema}")


def run_checks(app: Any, mongo_client: Any) -> None:
    from bson import ObjectId
    from fastapi.testclient import TestClient
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo import ASCENDING
    from pymongo.errors import PyMongoError

    from app.modules.auth.schemas import (
        LoginResponse,
        RegistrationResponse,
        UserProfile,
    )
    from app.modules.dashboard.schemas import DashboardSummary
    from app.modules.users.repository import UsersRepository
    from app.modules.users.schemas import UserListResponse, UserResponse
    from app.modules.users.service import UsersService
    from app.security import hash_password
    from app.modules.discovery import discover_module_names
    import jwt

    database = mongo_client[DATABASE_NAME]
    print("\nVérifications de configuration et OpenAPI")
    check(
        "discover_module_names() == ['documents', 'template']",
        discover_module_names() == ["documents", "template"],
    )
    check(
        "LLM_ENABLED=False pour auth, users et dashboard",
        all(
            getattr(
                __import__(f"app.modules.{module}.router", fromlist=["LLM_ENABLED"]),
                "LLM_ENABLED",
                None,
            )
            is False
            for module in ("auth", "users", "dashboard")
        ),
    )
    schema_models = (
        LoginResponse,
        RegistrationResponse,
        UserProfile,
        UserListResponse,
        UserResponse,
        DashboardSummary,
    )
    check(
        "aucun password_hash dans les schémas de réponse",
        all("password_hash" not in model.model_fields for model in schema_models),
    )
    check(
        "les routes /api/notes ne déclarent aucune dépendance de rôle/auth",
        all(
            not route.dependant.security_requirements
            for route in app.routes
            if hasattr(route, "dependant")
            and getattr(route, "path", "").startswith("/api/notes/")
        ),
    )
    print(
        "INFO  Écritures: auth -> users; users -> users; "
        "dashboard -> lecture seule (users, patients, appointments)."
    )
    report_routes(app)

    print("\nScénario HTTP")
    admin_password = "Smoke-admin-password-42"
    patient_password = "Smoke-patient-password-42"
    doctor_password = "Smoke-doctor-password-42"
    secretary_password = "Smoke-secretary-password-42"

    admin_result = database["users"].insert_one(
        {
            "email": "admin@smoke.test",
            "full_name": "Smoke Admin",
            "password_hash": hash_password(admin_password),
            "role": "admin",
            "status": "active",
            "patient_id": None,
            "created_at": datetime.now(UTC),
        },
    )
    admin_id = str(admin_result.inserted_id)

    with TestClient(app) as client:
        health = client.get("/health")
        check("GET /health -> 200", health.status_code == 200 and health.json() == {"status": "ok"})

        llm_status = client.get("/api/llm/status")
        check(
            "GET /api/llm/status -> 200 sans exposer une clé",
            llm_status.status_code == 200 and "api_key" not in llm_status.text,
        )

        admin_login = client.post(
            "/api/auth/login",
            data={"username": "admin@smoke.test", "password": admin_password},
        )
        check("POST /api/auth/login admin -> 200", admin_login.status_code == 200)
        admin_token = admin_login.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        patient_registration = client.post(
            "/api/auth/register",
            json={
                "email": "Patient@Smoke.Test",
                "password": patient_password,
                "full_name": "Smoke Patient",
            },
        )
        check(
            "POST /api/auth/register patient -> 201 active",
            patient_registration.status_code == 201
            and patient_registration.json()["role"] == "patient"
            and patient_registration.json()["status"] == "active",
        )
        patient_id = patient_registration.json()["id"]

        doctor_registration = client.post(
            "/api/auth/register",
            json={
                "email": "Doctor@Smoke.Test",
                "password": doctor_password,
                "full_name": "Smoke Doctor",
                "role_requested": "doctor",
            },
        )
        secretary_registration = client.post(
            "/api/auth/register",
            json={
                "email": "Secretary@Smoke.Test",
                "password": secretary_password,
                "full_name": "Smoke Secretary",
                "role_requested": "secretary",
            },
        )
        check(
            "POST /api/auth/register doctor/secretary -> 201 pending",
            doctor_registration.status_code == secretary_registration.status_code == 201
            and doctor_registration.json()["status"] == "pending"
            and secretary_registration.json()["status"] == "pending",
        )
        doctor_id = doctor_registration.json()["id"]
        secretary_id = secretary_registration.json()["id"]

        register_admin = client.post(
            "/api/auth/register",
            json={
                "email": "forbidden-admin@smoke.test",
                "password": "Smoke-password-42",
                "full_name": "Forbidden Admin",
                "role_requested": "admin",
            },
        )
        duplicate_email = client.post(
            "/api/auth/register",
            json={
                "email": "PATIENT@SMOKE.TEST",
                "password": "Smoke-another-password-42",
                "full_name": "Duplicate Patient",
            },
        )
        short_password = client.post(
            "/api/auth/register",
            json={
                "email": "short@smoke.test",
                "password": "short",
                "full_name": "Short Password",
            },
        )
        invalid_email = client.post(
            "/api/auth/register",
            json={
                "email": "invalid-email",
                "password": "Smoke-password-42",
                "full_name": "Invalid Email",
            },
        )
        check(
            "inscription admin refusée -> 403",
            register_admin.status_code == 403,
        )
        check("email dupliqué en majuscules -> 409", duplicate_email.status_code == 409)
        check("mot de passe d'inscription trop court -> 422", short_password.status_code == 422)
        check("email invalide -> 422", invalid_email.status_code == 422)

        patient_login = client.post(
            "/api/auth/login",
            data={"username": "patient@smoke.test", "password": patient_password},
        )
        doctor_pending_login = client.post(
            "/api/auth/login",
            data={"username": "doctor@smoke.test", "password": doctor_password},
        )
        wrong_password_login = client.post(
            "/api/auth/login",
            data={"username": "patient@smoke.test", "password": "Wrong-password-42"},
        )
        unknown_login = client.post(
            "/api/auth/login",
            data={"username": "unknown@smoke.test", "password": "Wrong-password-42"},
        )
        check("login patient -> 200", patient_login.status_code == 200)
        patient_token = patient_login.json()["access_token"]
        patient_headers = {"Authorization": f"Bearer {patient_token}"}
        check("login doctor en attente -> 403", doctor_pending_login.status_code == 403)
        check(
            "mauvais mot de passe/email inconnu -> même message 401",
            wrong_password_login.status_code == unknown_login.status_code == 401
            and wrong_password_login.json()["detail"] == unknown_login.json()["detail"],
        )

        me_ok = client.get("/api/auth/me", headers=patient_headers)
        me_missing = client.get("/api/auth/me")
        me_forged = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer forged.invalid.token"},
        )
        expired_token = jwt.encode(
            {
                "sub": patient_id,
                "role": "patient",
                "exp": datetime.now(UTC) - timedelta(minutes=1),
            },
            os.environ["JWT_SECRET"],
            algorithm="HS256",
        )
        me_expired = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        check("GET /api/auth/me avec token -> 200", me_ok.status_code == 200)
        check("GET /api/auth/me sans token -> 401", me_missing.status_code == 401)
        check("GET /api/auth/me avec token falsifié -> 401", me_forged.status_code == 401)
        check("GET /api/auth/me avec token expiré -> 401", me_expired.status_code == 401)

        pending_users = client.get(
            "/api/users?status=pending",
            headers=admin_headers,
        )
        check(
            "GET /api/users?status=pending -> 200 avec doctor et secretary",
            pending_users.status_code == 200
            and {user["email"] for user in pending_users.json()["items"]}
            == {"doctor@smoke.test", "secretary@smoke.test"},
        )
        doctor_approval = client.patch(
            f"/api/users/{doctor_id}/approve",
            headers=admin_headers,
        )
        secretary_approval = client.patch(
            f"/api/users/{secretary_id}/approve",
            headers=admin_headers,
        )
        repeat_approval = client.patch(
            f"/api/users/{doctor_id}/approve",
            headers=admin_headers,
        )
        check(
            "approve doctor et secretary -> 200 ; second approve -> 400",
            doctor_approval.status_code == secretary_approval.status_code == 200
            and repeat_approval.status_code == 400,
        )
        doctor_login = client.post(
            "/api/auth/login",
            data={"username": "doctor@smoke.test", "password": doctor_password},
        )
        secretary_login = client.post(
            "/api/auth/login",
            data={"username": "secretary@smoke.test", "password": secretary_password},
        )
        check(
            "login doctor et secretary approuvés -> 200",
            doctor_login.status_code == secretary_login.status_code == 200,
        )
        doctor_token = doctor_login.json()["access_token"]
        secretary_token = secretary_login.json()["access_token"]
        doctor_headers = {"Authorization": f"Bearer {doctor_token}"}
        secretary_headers = {"Authorization": f"Bearer {secretary_token}"}

        doctor_filter = client.get(
            "/api/users?status=active&role=doctor",
            headers=admin_headers,
        )
        page_one = client.get(
            "/api/users?page=1&size=1",
            headers=admin_headers,
        )
        page_two = client.get(
            "/api/users?page=2&size=1",
            headers=admin_headers,
        )
        oversized_page = client.get(
            "/api/users?page=1&size=101",
            headers=admin_headers,
        )
        check(
            "GET /api/users filtres role/status",
            doctor_filter.status_code == 200
            and doctor_filter.json()["total"] == 1
            and doctor_filter.json()["items"][0]["role"] == "doctor",
        )
        check(
            "GET /api/users pagination page/size",
            page_one.status_code == page_two.status_code == 200
            and page_one.json()["size"] == 1
            and page_one.json()["items"][0]["id"] != page_two.json()["items"][0]["id"],
        )
        check("GET /api/users size > 100 -> 422", oversized_page.status_code == 422)

        get_user = client.get(f"/api/users/{doctor_id}", headers=admin_headers)
        invalid_id = client.get("/api/users/not-an-object-id", headers=admin_headers)
        missing_id = client.get(
            f"/api/users/{ObjectId()}",
            headers=admin_headers,
        )
        check("GET /api/users/{id} existant -> 200", get_user.status_code == 200)
        check(
            "GET /api/users/{id} invalide/inexistant -> 404",
            invalid_id.status_code == missing_id.status_code == 404,
        )

        created_user = client.post(
            "/api/users",
            headers=admin_headers,
            json={
                "email": "Managed@Smoke.Test",
                "password": "Managed-user-password-42",
                "full_name": "Managed User",
                "role": "patient",
            },
        )
        check(
            "POST /api/users -> 201 active, email normalisé",
            created_user.status_code == 201
            and created_user.json()["status"] == "active"
            and created_user.json()["email"] == "managed@smoke.test",
        )
        managed_id = created_user.json()["id"]
        role_change = client.patch(
            f"/api/users/{managed_id}/role",
            headers=admin_headers,
            json={"role": "secretary"},
        )
        disabled = client.patch(
            f"/api/users/{managed_id}/disable",
            headers=admin_headers,
        )
        enable = client.patch(
            f"/api/users/{managed_id}/enable",
            headers=admin_headers,
        )
        managed_login = client.post(
            "/api/auth/login",
            data={
                "username": "managed@smoke.test",
                "password": "Managed-user-password-42",
            },
        )
        logical_delete = client.delete(
            f"/api/users/{managed_id}",
            headers=admin_headers,
        )
        check("PATCH /api/users/{id}/role -> 200", role_change.status_code == 200)
        check("PATCH /api/users/{id}/disable -> disabled", disabled.status_code == 200 and disabled.json()["status"] == "disabled")
        check("PATCH /api/users/{id}/enable -> active", enable.status_code == 200 and enable.json()["status"] == "active")
        check("DELETE /api/users/{id} logique -> disabled", logical_delete.status_code == 200 and logical_delete.json()["status"] == "disabled")

        self_disable = client.patch(
            f"/api/users/{admin_id}/disable",
            headers=admin_headers,
        )
        self_delete = client.delete(f"/api/users/{admin_id}", headers=admin_headers)
        self_demote = client.patch(
            f"/api/users/{admin_id}/role",
            headers=admin_headers,
            json={"role": "doctor"},
        )
        check(
            "garde-fous admin: auto-désactivation, suppression logique, auto-rétrogradation -> 400",
            self_disable.status_code == self_delete.status_code == self_demote.status_code == 400,
        )

        async def check_last_admin_guard() -> bool:
            motor_client = AsyncIOMotorClient(MONGO_URI)
            try:
                service = UsersService(
                    UsersRepository(motor_client[DATABASE_NAME]),
                )
                try:
                    await service.disable(admin_id, {"_id": ObjectId()})
                except Exception as exc:
                    return (
                        getattr(exc, "status_code", None) == 400
                        and getattr(exc, "code", None) == "last_admin"
                    )
                return False
            finally:
                motor_client.close()

        import asyncio

        last_admin_guard = asyncio.run(check_last_admin_guard())
        check(
            "garde-fou dernier admin actif (service, cible distincte du demandeur)",
            last_admin_guard,
        )

        unauthenticated_users = client.get("/api/users")
        denied_users = [
            client.get("/api/users", headers=headers)
            for headers in (doctor_headers, secretary_headers, patient_headers)
        ]
        check(
            "GET /api/users: sans token -> 401 ; doctor/secretary/patient -> 403",
            unauthenticated_users.status_code == 401
            and all(response.status_code == 403 for response in denied_users),
        )

        linked_record_id = "smoke-patient-record-42"
        admin_link = client.patch(
            f"/api/users/{patient_id}/link-patient",
            headers=admin_headers,
            json={"patient_id": linked_record_id},
        )
        admin_unlink = client.patch(
            f"/api/users/{patient_id}/unlink-patient",
            headers=admin_headers,
        )
        linked_patient = client.patch(
            f"/api/users/{patient_id}/link-patient",
            headers=secretary_headers,
            json={"patient_id": linked_record_id},
        )
        secretary_unlink = client.patch(
            f"/api/users/{patient_id}/unlink-patient",
            headers=secretary_headers,
        )
        secretary_relink = client.patch(
            f"/api/users/{patient_id}/link-patient",
            headers=secretary_headers,
            json={"patient_id": linked_record_id},
        )
        check(
            "admin autorisé à link-patient/unlink-patient",
            admin_link.status_code == admin_unlink.status_code == 200,
        )
        check(
            "secrétaire autorisée à link-patient/unlink-patient",
            linked_patient.status_code == secretary_unlink.status_code == secretary_relink.status_code == 200,
        )
        denied_link_calls = []
        for headers in (doctor_headers, patient_headers):
            denied_link_calls.append(
                client.patch(
                    f"/api/users/{patient_id}/link-patient",
                    headers=headers,
                    json={"patient_id": "forbidden-record"},
                ),
            )
            denied_link_calls.append(
                client.patch(
                    f"/api/users/{patient_id}/unlink-patient",
                    headers=headers,
                ),
            )
        check(
            "doctor et patient refusés sur link-patient/unlink-patient -> 403",
            all(response.status_code == 403 for response in denied_link_calls),
        )

        dashboard_admin = client.get("/api/dashboard/summary", headers=admin_headers)
        dashboard_doctor = client.get("/api/dashboard/summary", headers=doctor_headers)
        dashboard_secretary = client.get("/api/dashboard/summary", headers=secretary_headers)
        patient_unlink = client.patch(
            f"/api/users/{patient_id}/unlink-patient",
            headers=secretary_headers,
        )
        dashboard_unlinked = client.get("/api/dashboard/summary", headers=patient_headers)
        patient_link_again = client.patch(
            f"/api/users/{patient_id}/link-patient",
            headers=secretary_headers,
            json={"patient_id": linked_record_id},
        )
        dashboard_linked = client.get("/api/dashboard/summary", headers=patient_headers)
        expected_unlinked_alert = "Dossier patient non lié, contactez l'accueil"
        check(
            "GET /api/dashboard/summary admin/doctor/secretary -> 200",
            all(
                response.status_code == 200
                for response in (dashboard_admin, dashboard_doctor, dashboard_secretary)
            )
            and dashboard_admin.json()["role"] == "admin"
            and dashboard_doctor.json()["role"] == "doctor"
            and dashboard_secretary.json()["role"] == "secretary",
        )
        dashboard_doctor_kpis = {
            item["key"]: item["value"]
            for item in dashboard_doctor.json()["kpis"]
        }
        dashboard_secretary_kpis = {
            item["key"]: item["value"]
            for item in dashboard_secretary.json()["kpis"]
        }
        check(
            "dashboard médecin/secrétaire: collections absentes -> compteurs zéro",
            dashboard_doctor_kpis == dashboard_secretary_kpis
            == {"patients": 0, "appointments_today": 0},
        )
        check(
            "dashboard patient non lié: message exact et rendez-vous vide",
            patient_unlink.status_code == 200
            and dashboard_unlinked.status_code == 200
            and dashboard_unlinked.json()["alerts"][0]["message"] == expected_unlinked_alert
            and dashboard_unlinked.json()["kpis"][0]["value"] == 0,
        )
        check(
            "dashboard patient lié après link-patient -> 200 et liste vide sans rendez-vous",
            patient_link_again.status_code == 200
            and dashboard_linked.status_code == 200
            and dashboard_linked.json()["alerts"] == [],
        )

        disabled_token = managed_login.json().get("access_token", "")
        # Le compte géré est désactivé après émission de son token.
        disabled_me = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {disabled_token}"},
        )
        disabled_dashboard = client.get(
            "/api/dashboard/summary",
            headers={"Authorization": f"Bearer {disabled_token}"},
        )
        check(
            "compte désactivé: token valide refusé sur /me et dashboard -> 403",
            managed_login.status_code == 200
            and disabled_me.status_code == disabled_dashboard.status_code == 403,
        )

        wrong_current_password = client.post(
            "/api/auth/change-password",
            headers=patient_headers,
            json={
                "current_password": "incorrect-password",
                "new_password": "Replacement-password-42",
            },
        )
        changed_password = client.post(
            "/api/auth/change-password",
            headers=patient_headers,
            json={
                "current_password": patient_password,
                "new_password": "Replacement-password-42",
            },
        )
        login_new_password = client.post(
            "/api/auth/login",
            data={
                "username": "patient@smoke.test",
                "password": "Replacement-password-42",
            },
        )
        check("change-password mauvais mot de passe actuel -> 400", wrong_current_password.status_code == 400)
        check(
            "change-password correct puis login avec nouveau mot de passe -> 200",
            changed_password.status_code == 200 and login_new_password.status_code == 200,
        )

        note_create = client.post(
            "/api/notes/",
            json={"title": "Smoke note", "content": "Note body"},
        )
        check("POST /api/notes -> 201", note_create.status_code == 201)
        note_id = note_create.json()["id"]
        note_list = client.get("/api/notes/")
        note_get = client.get(f"/api/notes/{note_id}")
        note_update = client.put(
            f"/api/notes/{note_id}",
            json={"title": "Updated smoke note", "content": "Updated note body"},
        )
        note_summary = client.post(
            "/api/notes/summarize",
            json={"content": "Patient stable. Follow-up next week."},
        )
        note_delete = client.delete(f"/api/notes/{note_id}")
        check(
            "GET /api/notes liste et GET /{id} -> 200",
            note_list.status_code == note_get.status_code == 200
            and any(item["id"] == note_id for item in note_list.json()),
        )
        check(
            "PUT /api/notes/{id} -> 200 et document modifié",
            note_update.status_code == 200
            and note_update.json()["title"] == "Updated smoke note",
        )
        check(
            "POST /api/notes/summarize en mode mock -> 200 valide",
            note_summary.status_code == 200 and bool(note_summary.json().get("summary")),
        )
        check("DELETE /api/notes/{id} -> 204", note_delete.status_code == 204)
        documents = client.get("/api/documents/")
        check("GET /api/documents/ -> 501", documents.status_code == 501)

    print("\nVérifications persistantes dans la base temporaire")
    users = list(database["users"].find({}))
    emails_lowercase = all(user["email"] == user["email"].lower() for user in users)
    check("tous les emails persistés sont en minuscules", emails_lowercase)
    user_indexes = list(database["users"].list_indexes())
    unique_email_index = any(
        index.get("key") == {"email": ASCENDING} and index.get("unique") is True
        for index in user_indexes
    )
    check("index unique users.email présent", unique_email_index)
    bcrypt_hashes = all(
        isinstance(user.get("password_hash"), str)
        and user["password_hash"].startswith("$2b$")
        for user in users
    )
    plaintext_password_fields = any("password" in user for user in users)
    plaintext_passwords = (
        admin_password,
        patient_password,
        doctor_password,
        secretary_password,
        "Managed-user-password-42",
        "Replacement-password-42",
    )
    leaked_values = any(
        user.get("password_hash") in plaintext_passwords
        for user in users
    )
    check(
        "password_hash au format bcrypt $2b$ ; aucun mot de passe en clair",
        bcrypt_hashes and not plaintext_password_fields and not leaked_values,
    )
    check(
        "aucune collection patients créée",
        "patients" not in database.list_collection_names(),
    )


def main() -> int:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError

    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    try:
        mongo_client.admin.command("ping")
    except PyMongoError:
        print("KO  MongoDB injoignable sur mongodb://localhost:27017.")
        mongo_client.close()
        return 2

    print("OK  MongoDB répond sur localhost:27017.")
    exit_code = 0
    try:
        from app.main import app

        run_checks(app, mongo_client)
    except Exception:
        print("KO  Échec du smoke test (voir la dernière assertion KO ci-dessus).")
        exit_code = 1
    finally:
        try:
            mongo_client.drop_database(DATABASE_NAME)
            mongo_client.close()
            verify_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            try:
                remaining = DATABASE_NAME in verify_client.list_database_names()
                check("base mediflow_smoke_test supprimée", not remaining)
            finally:
                verify_client.close()
        except Exception:
            print("KO  Échec de la suppression/vérification de la base temporaire.")
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
