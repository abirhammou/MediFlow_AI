from beanie import PydanticObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.models import normalize_email
from app.errors import APIError
from app.modules.auth.models import Role, User
from app.modules.auth.repository import get_user_by_id
from app.modules.patients.repository import get_patient
from app.modules.users import repository
from app.modules.users.schemas import UserCreateRequest, UserListResponse, UserResponse
from app.security import hash_password


class UsersService:
    async def list_users(
        self,
        *,
        is_active: bool | None,
        role: Role | None,
        page: int,
        size: int,
    ) -> UserListResponse:
        users, total = await repository.list_users(
            is_active=is_active,
            role=role,
            skip=(page - 1) * size,
            limit=size,
        )
        return UserListResponse(
            items=[UserResponse.from_user(user) for user in users],
            total=total,
            page=page,
            size=size,
        )

    async def get_user(self, user_id: str) -> UserResponse:
        return UserResponse.from_user(await self._get_user(user_id))

    async def create_user(self, request: UserCreateRequest) -> UserResponse:
        first_name, last_name = request.first_name.strip(), request.last_name.strip()
        if not first_name or not last_name:
            raise APIError(422, "invalid_name", "Le prénom et le nom sont obligatoires.")
        user = User(
            email=normalize_email(request.email),
            password_hash=hash_password(request.password),
            first_name=first_name,
            last_name=last_name,
            role=request.role,
        )
        try:
            await user.insert()
        except DuplicateKeyError:
            raise APIError(409, "email_exists", "Cette adresse email est déjà utilisée.") from None
        return UserResponse.from_user(user)

    async def activate(self, user_id: str) -> UserResponse:
        """Approve a pending account or re-enable a disabled one (both are `is_active = False`)."""
        target = await self._get_user(user_id)
        if target.is_active:
            raise APIError(400, "already_active", "Le compte est déjà actif.")
        target.is_active = True
        target.failed_login_attempts = 0
        target.locked_until = None
        await target.save()
        return UserResponse.from_user(target)

    async def disable(self, user_id: str, acting_user: User) -> UserResponse:
        target = await self._get_user(user_id)
        if target.id == acting_user.id:
            raise APIError(400, "self_deactivation", "Un administrateur ne peut pas se désactiver.")
        await self._prevent_last_active_admin(target, new_role=target.role, new_active=False)
        target.is_active = False
        await target.save()
        return UserResponse.from_user(target)

    async def change_role(self, user_id: str, role: Role, acting_user: User) -> UserResponse:
        target = await self._get_user(user_id)
        if target.id == acting_user.id and target.role == Role.ADMIN and role != Role.ADMIN:
            raise APIError(400, "self_admin_role", "Un administrateur ne peut pas retirer son propre rôle.")
        await self._prevent_last_active_admin(target, new_role=role, new_active=target.is_active)
        target.role = role
        if role != Role.PATIENT:
            target.patient_id = None
        await target.save()
        return UserResponse.from_user(target)

    async def link_patient(self, user_id: str, patient_id: str) -> UserResponse:
        target = await self._get_user(user_id)
        if target.role != Role.PATIENT:
            raise APIError(400, "not_a_patient", "Seul un compte patient peut être lié à un dossier.")
        try:
            patient = await get_patient(PydanticObjectId(patient_id))
        except (InvalidId, TypeError):
            patient = None
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier patient introuvable.")
        target.patient_id = patient.id
        await target.save()
        return UserResponse.from_user(target)

    async def unlink_patient(self, user_id: str) -> UserResponse:
        target = await self._get_user(user_id)
        target.patient_id = None
        await target.save()
        return UserResponse.from_user(target)

    @staticmethod
    async def _get_user(user_id: str) -> User:
        try:
            user = await get_user_by_id(PydanticObjectId(user_id))
        except (InvalidId, TypeError):
            user = None
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
        return user

    @staticmethod
    async def _prevent_last_active_admin(target: User, *, new_role: Role, new_active: bool) -> None:
        if (
            target.role == Role.ADMIN
            and target.is_active
            and (new_role != Role.ADMIN or not new_active)
            and await repository.count_active_admins() <= 1
        ):
            raise APIError(400, "last_admin", "Le dernier administrateur actif ne peut pas être désactivé.")
