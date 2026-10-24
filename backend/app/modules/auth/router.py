from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.dependencies import get_current_user
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginResponse,
    RegistrationResponse,
    RegisterRequest,
    UserProfile,
)
from app.modules.auth.service import AuthService


router = APIRouter()
TAGS = ["auth"]
LLM_ENABLED = False


def get_auth_service(
    database: AsyncIOMotorDatabase = Depends(get_db),
) -> AuthService:
    return AuthService(AuthRepository(database))


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> RegistrationResponse:
    return await service.register(request)


@router.post("/login", response_model=LoginResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    return await service.login(form.username, form.password)


@router.get("/me", response_model=UserProfile)
async def me(
    user: dict = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> UserProfile:
    return service.profile(user)


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    user: dict = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    return await service.change_password(user, request)
