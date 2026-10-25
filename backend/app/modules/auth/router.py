from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginResponse,
    RegisterRequest,
    RegistrationResponse,
    UserProfile,
)
from app.modules.auth.service import AuthService
from app.modules.patient_portal.accounts import needs_password_change

router = APIRouter()
TAGS = ["auth"]
LLM_ENABLED = False


def get_auth_service() -> AuthService:
    return AuthService()


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
    """Form fields `username` (the email) and `password`, as expected by OAuth2 / Swagger."""
    return await service.login(form.username, form.password)


@router.get("/me", response_model=UserProfile)
async def me(user: User = Depends(get_current_user)) -> UserProfile:
    profile = UserProfile.from_user(user)
    profile.must_change_password = await needs_password_change(user)
    return profile


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    return await service.change_password(user, request)
