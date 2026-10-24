from fastapi import APIRouter, Depends, Query, status

from app.dependencies import require_roles
from app.modules.auth.models import Role, User
from app.modules.users.schemas import (
    PatientLinkRequest,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserRoleRequest,
)
from app.modules.users.service import UsersService

router = APIRouter()
TAGS = ["users"]
LLM_ENABLED = False

admin_only = require_roles(Role.ADMIN)


def get_users_service() -> UsersService:
    return UsersService()


@router.get("", response_model=UserListResponse)
async def list_users(
    is_active: bool | None = None,
    role: Role | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(admin_only),
    service: UsersService = Depends(get_users_service),
) -> UserListResponse:
    return await service.list_users(is_active=is_active, role=role, page=page, size=size)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    _: User = Depends(admin_only),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.get_user(user_id)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: UserCreateRequest,
    _: User = Depends(admin_only),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.create_user(request)


@router.patch("/{user_id}/approve", response_model=UserResponse)
async def approve_user(
    user_id: str,
    _: User = Depends(admin_only),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.activate(user_id)


@router.patch("/{user_id}/enable", response_model=UserResponse)
async def enable_user(
    user_id: str,
    _: User = Depends(admin_only),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.activate(user_id)


@router.patch("/{user_id}/disable", response_model=UserResponse)
async def disable_user(
    user_id: str,
    user: User = Depends(admin_only),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.disable(user_id, user)


@router.patch("/{user_id}/role", response_model=UserResponse)
async def change_user_role(
    user_id: str,
    request: UserRoleRequest,
    user: User = Depends(admin_only),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.change_role(user_id, request.role, user)


@router.delete("/{user_id}", response_model=UserResponse)
async def delete_user(
    user_id: str,
    user: User = Depends(admin_only),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    """Soft delete: the account is disabled, never removed."""
    return await service.disable(user_id, user)


@router.patch("/{user_id}/link-patient", response_model=UserResponse)
async def link_patient(
    user_id: str,
    request: PatientLinkRequest,
    _: User = Depends(require_roles(Role.ADMIN, Role.SECRETARY)),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.link_patient(user_id, request.patient_id)


@router.patch("/{user_id}/unlink-patient", response_model=UserResponse)
async def unlink_patient(
    user_id: str,
    _: User = Depends(require_roles(Role.ADMIN, Role.SECRETARY)),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.unlink_patient(user_id)
