from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.common.roles import Role, UserStatus
from app.errors import APIError
from app.security import hash_password
from app.modules.users.repository import UsersRepository
from app.modules.users.schemas import (
    UserCreateRequest,
    UserListResponse,
    UserResponse,
)


class UsersService:
    def __init__(self, repository: UsersRepository) -> None:
        self.repository = repository

    async def list_users(
        self,
        *,
        user_status: UserStatus | None,
        role: Role | None,
        page: int,
        size: int,
    ) -> UserListResponse:
        filters: dict[str, str] = {}
        if user_status is not None:
            filters["status"] = user_status.value
        if role is not None:
            filters["role"] = role.value
        users, total = await self.repository.list_users(
            filters,
            skip=(page - 1) * size,
            limit=size,
        )
        return UserListResponse(
            items=[self._response(user) for user in users],
            total=total,
            page=page,
            size=size,
        )

    async def get_user(self, user_id: str) -> UserResponse:
        user = await self.repository.get_by_id(self._parse_id(user_id))
        if user is None:
            raise self._not_found()
        return self._response(user)

    async def create_user(self, request: UserCreateRequest) -> UserResponse:
        email = request.email.strip().lower()
        full_name = request.full_name.strip()
        if not full_name:
            raise APIError(422, "invalid_full_name", "Le nom complet est obligatoire.")
        try:
            user = await self.repository.create(
                email=email,
                full_name=full_name,
                password_hash=hash_password(request.password),
                role=request.role.value,
            )
        except DuplicateKeyError:
            raise APIError(409, "email_exists", "Cette adresse email est déjà utilisée.") from None
        return self._response(user)

    async def approve(self, user_id: str) -> UserResponse:
        return await self._update_status(
            user_id,
            UserStatus.PENDING,
            {"status": UserStatus.ACTIVE.value},
            "Seul un compte en attente peut être approuvé.",
        )

    async def disable(
        self,
        user_id: str,
        acting_user: dict[str, Any],
    ) -> UserResponse:
        target = await self._get_raw_user(user_id)
        self._prevent_self_deactivation(target, acting_user)
        await self._prevent_last_active_admin(target, {"status": UserStatus.DISABLED.value})
        updated = await self.repository.update_fields(
            target["_id"],
            {"status": UserStatus.DISABLED.value},
        )
        if updated is None:
            raise self._not_found()
        return self._response(updated)

    async def enable(self, user_id: str) -> UserResponse:
        return await self._update_status(
            user_id,
            UserStatus.DISABLED,
            {"status": UserStatus.ACTIVE.value},
            "Seul un compte désactivé peut être réactivé.",
        )

    async def change_role(
        self,
        user_id: str,
        role: Role,
        acting_user: dict[str, Any],
    ) -> UserResponse:
        target = await self._get_raw_user(user_id)
        if (
            target["_id"] == acting_user["_id"]
            and target["role"] == Role.ADMIN
            and role != Role.ADMIN
        ):
            raise APIError(400, "self_admin_role", "Un administrateur ne peut pas retirer son propre rôle.")
        fields = {"role": role.value}
        await self._prevent_last_active_admin(target, fields)
        updated = await self.repository.update_fields(target["_id"], fields)
        if updated is None:
            raise self._not_found()
        return self._response(updated)

    async def delete(
        self,
        user_id: str,
        acting_user: dict[str, Any],
    ) -> UserResponse:
        return await self.disable(user_id, acting_user)

    async def link_patient(self, user_id: str, patient_id: str) -> UserResponse:
        target = await self._get_raw_user(user_id)
        updated = await self.repository.update_fields(
            target["_id"],
            {"patient_id": patient_id},
        )
        if updated is None:
            raise self._not_found()
        return self._response(updated)

    async def unlink_patient(self, user_id: str) -> UserResponse:
        target = await self._get_raw_user(user_id)
        updated = await self.repository.update_fields(
            target["_id"],
            {"patient_id": None},
        )
        if updated is None:
            raise self._not_found()
        return self._response(updated)

    async def _update_status(
        self,
        user_id: str,
        expected_status: UserStatus,
        fields: dict[str, str],
        error_detail: str,
    ) -> UserResponse:
        parsed_id = self._parse_id(user_id)
        updated = await self.repository.update_if_status(
            parsed_id,
            expected_status.value,
            fields,
        )
        if updated is None:
            if await self.repository.get_by_id(parsed_id) is None:
                raise self._not_found()
            raise APIError(400, "invalid_user_status", error_detail)
        return self._response(updated)

    async def _get_raw_user(self, user_id: str) -> dict[str, Any]:
        user = await self.repository.get_by_id(self._parse_id(user_id))
        if user is None:
            raise self._not_found()
        return user

    async def _prevent_last_active_admin(
        self,
        target: dict[str, Any],
        changes: dict[str, Any],
    ) -> None:
        if (
            target.get("role") == Role.ADMIN
            and target.get("status") == UserStatus.ACTIVE
            and (
                changes.get("role", Role.ADMIN.value) != Role.ADMIN.value
                or changes.get("status", UserStatus.ACTIVE.value) != UserStatus.ACTIVE.value
            )
            and await self.repository.count_active_admins() <= 1
        ):
            raise APIError(400, "last_admin", "Le dernier administrateur actif ne peut pas être désactivé.")

    @staticmethod
    def _prevent_self_deactivation(
        target: dict[str, Any],
        acting_user: dict[str, Any],
    ) -> None:
        if target["_id"] == acting_user["_id"]:
            raise APIError(400, "self_deactivation", "Un administrateur ne peut pas se désactiver.")

    @staticmethod
    def _parse_id(user_id: str) -> ObjectId:
        try:
            return ObjectId(user_id)
        except (InvalidId, TypeError):
            raise UsersService._not_found() from None

    @staticmethod
    def _not_found() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur introuvable.",
        )

    @staticmethod
    def _response(user: dict[str, Any]) -> UserResponse:
        patient_id = user.get("patient_id")
        return UserResponse(
            id=str(user["_id"]),
            email=user["email"],
            full_name=user["full_name"],
            role=user["role"],
            status=user["status"],
            patient_id=str(patient_id) if patient_id is not None else None,
            created_at=user["created_at"],
        )
