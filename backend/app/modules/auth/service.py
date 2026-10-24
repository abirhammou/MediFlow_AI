from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.common.roles import Role, UserStatus
from app.errors import APIError
from app.security import create_access_token, hash_password, verify_password
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginResponse,
    RegistrationResponse,
    RegisterRequest,
    UserProfile,
)


class AuthService:
    def __init__(self, repository: AuthRepository) -> None:
        self.repository = repository

    async def register(self, request: RegisterRequest) -> RegistrationResponse:
        requested_role = request.role_requested or Role.PATIENT.value
        if requested_role == Role.ADMIN:
            raise APIError(403, "role_forbidden", "La création d'un compte administrateur est interdite.")
        if requested_role not in {Role.PATIENT, Role.DOCTOR, Role.SECRETARY}:
            raise APIError(400, "invalid_role", "Le rôle demandé n'est pas valide.")

        email = request.email.strip().lower()
        full_name = request.full_name.strip()
        if not full_name:
            raise APIError(422, "invalid_full_name", "Le nom complet est obligatoire.")
        # Le dossier patient (collection patients) est géré par le module patients. Le lien se fait via users.patient_id.
        active = requested_role == Role.PATIENT
        try:
            user = await self.repository.register(
                email=email,
                full_name=full_name,
                password_hash=hash_password(request.password),
                role=requested_role,
                status=UserStatus.ACTIVE if active else UserStatus.PENDING,
                created_at=datetime.now(UTC),
            )
        except DuplicateKeyError:
            raise APIError(409, "email_exists", "Cette adresse email est déjà utilisée.") from None

        profile = self._profile(user)
        detail = (
            "Compte créé."
            if active
            else "Compte créé ; une approbation est nécessaire avant la connexion."
        )
        return RegistrationResponse(**profile.model_dump(), detail=detail)

    async def login(self, email: str, password: str) -> LoginResponse:
        user = await self.repository.get_by_email(email.strip().lower())
        if user is None or not verify_password(password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou mot de passe incorrect.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if user["status"] == UserStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Compte en attente d'approbation.",
            )
        if user["status"] == UserStatus.DISABLED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Compte désactivé.",
            )

        return LoginResponse(
            access_token=create_access_token(str(user["_id"]), user["role"]),
            role=user["role"],
            status=user["status"],
            full_name=user["full_name"],
        )

    def profile(self, user: dict[str, Any]) -> UserProfile:
        return self._profile(user)

    async def change_password(
        self,
        user: dict[str, Any],
        request: ChangePasswordRequest,
    ) -> dict[str, str]:
        if not verify_password(request.current_password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le mot de passe actuel est incorrect.",
            )
        await self.repository.update_password(
            user["_id"],
            hash_password(request.new_password),
        )
        return {"detail": "Mot de passe modifié."}

    @staticmethod
    def _profile(user: dict[str, Any]) -> UserProfile:
        patient_id = user.get("patient_id")
        return UserProfile(
            id=str(user["_id"]),
            email=user["email"],
            full_name=user["full_name"],
            role=user["role"],
            status=user["status"],
            patient_id=str(patient_id) if patient_id is not None else None,
            created_at=user["created_at"],
        )
