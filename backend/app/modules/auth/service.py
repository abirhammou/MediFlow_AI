from datetime import timedelta

from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.models import normalize_email
from app.core.time import utcnow
from app.errors import APIError
from app.modules.auth.models import Role, User
from app.modules.auth.repository import get_user_by_email
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginResponse,
    RegisterRequest,
    RegistrationResponse,
    UserProfile,
)
from app.modules.patient_portal.accounts import mark_password_changed, needs_password_change
from app.security import create_access_token, hash_password, verify_password

MAX_FAILED_LOGINS = 5
LOCK_DURATION = timedelta(minutes=15)
# Self-registration: patients are active at once, staff accounts wait for an admin.
SELF_REGISTER_ROLES = {Role.PATIENT, Role.DOCTOR, Role.SECRETARY}


class AuthService:
    async def register(self, request: RegisterRequest) -> RegistrationResponse:
        role = Role(request.role_requested or Role.PATIENT)
        if role not in SELF_REGISTER_ROLES:
            raise APIError(403, "role_forbidden", "Ce rôle ne peut pas être demandé à l'inscription.")

        first_name, last_name = request.first_name.strip(), request.last_name.strip()
        if not first_name or not last_name:
            raise APIError(422, "invalid_name", "Le prénom et le nom sont obligatoires.")
        # The patient record (patients collection) is created by the staff and linked via users.patientId.
        active = role == Role.PATIENT
        user = User(
            email=normalize_email(request.email),
            password_hash=hash_password(request.password),
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=active,
        )
        try:
            await user.insert()
        except DuplicateKeyError:
            raise APIError(409, "email_exists", "Cette adresse email est déjà utilisée.") from None

        detail = (
            "Compte créé."
            if active
            else "Compte créé ; une approbation est nécessaire avant la connexion."
        )
        return RegistrationResponse(**UserProfile.from_user(user).model_dump(), detail=detail)

    async def login(self, email: str, password: str) -> LoginResponse:
        user = await get_user_by_email(email)
        now = utcnow()
        if user is not None and user.locked_until is not None and user.locked_until > now:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Trop de tentatives échouées. Réessayez dans quelques minutes.",
            )
        if user is None or not verify_password(password, user.password_hash):
            if user is not None:
                await self._record_failure(user)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou mot de passe incorrect.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Compte inactif ou en attente d'approbation.",
            )

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        await user.save()
        return LoginResponse(
            access_token=create_access_token(str(user.id), user.role.value),
            role=user.role,
            first_name=user.first_name,
            last_name=user.last_name,
            must_change_password=await needs_password_change(user),
        )

    async def change_password(self, user: User, request: ChangePasswordRequest) -> dict[str, str]:
        if not verify_password(request.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le mot de passe actuel est incorrect.",
            )
        if request.new_password == request.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le nouveau mot de passe doit être différent de l'actuel.",
            )
        user.password_hash = hash_password(request.new_password)
        await user.save()
        await mark_password_changed(user)
        return {"detail": "Mot de passe modifié."}

    @staticmethod
    async def _record_failure(user: User) -> None:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_LOGINS:
            user.failed_login_attempts = 0
            user.locked_until = utcnow() + LOCK_DURATION
        await user.save()
