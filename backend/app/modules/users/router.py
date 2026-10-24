from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.common.roles import Role, UserStatus
from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.modules.users.repository import UsersRepository
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


def get_users_service(
    database: AsyncIOMotorDatabase = Depends(get_db),
) -> UsersService:
    return UsersService(UsersRepository(database))


@router.get("", response_model=UserListResponse)
async def list_users(
    user_status: UserStatus | None = Query(default=None, alias="status"),
    role: Role | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    _: dict = Depends(require_roles(Role.ADMIN)),
    service: UsersService = Depends(get_users_service),
) -> UserListResponse:
    return await service.list_users(
        user_status=user_status,
        role=role,
        page=page,
        size=size,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    _: dict = Depends(require_roles(Role.ADMIN)),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.get_user(user_id)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    request: UserCreateRequest,
    _: dict = Depends(require_roles(Role.ADMIN)),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.create_user(request)


@router.patch("/{user_id}/approve", response_model=UserResponse)
async def approve_user(
    user_id: str,
    _: dict = Depends(require_roles(Role.ADMIN)),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.approve(user_id)


@router.patch("/{user_id}/disable", response_model=UserResponse)
async def disable_user(
    user_id: str,
    user: dict = Depends(require_roles(Role.ADMIN)),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.disable(user_id, user)


@router.patch("/{user_id}/enable", response_model=UserResponse)
async def enable_user(
    user_id: str,
    _: dict = Depends(require_roles(Role.ADMIN)),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.enable(user_id)


@router.patch("/{user_id}/role", response_model=UserResponse)
async def change_user_role(
    user_id: str,
    request: UserRoleRequest,
    user: dict = Depends(require_roles(Role.ADMIN)),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.change_role(user_id, request.role, user)


@router.delete("/{user_id}", response_model=UserResponse)
async def delete_user(
    user_id: str,
    user: dict = Depends(require_roles(Role.ADMIN)),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.delete(user_id, user)


@router.patch("/{user_id}/link-patient", response_model=UserResponse)
async def link_patient(
    user_id: str,
    request: PatientLinkRequest,
    _: dict = Depends(require_roles(Role.ADMIN, Role.SECRETARY)),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.link_patient(user_id, request.patient_id)


@router.patch("/{user_id}/unlink-patient", response_model=UserResponse)
async def unlink_patient(
    user_id: str,
    _: dict = Depends(require_roles(Role.ADMIN, Role.SECRETARY)),
    service: UsersService = Depends(get_users_service),
) -> UserResponse:
    return await service.unlink_patient(user_id)
