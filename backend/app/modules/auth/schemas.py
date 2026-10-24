from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.auth.models import EMAIL_PATTERN, Role, User


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    role_requested: Literal["PATIENT", "DOCTOR", "SECRETARY", "ADMIN", "ADMIN_STAFF"] | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class UserProfile(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    role: Role
    is_active: bool
    patient_id: str | None
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def from_user(cls, user: User) -> "UserProfile":
        return cls(
            id=str(user.id),
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role,
            is_active=user.is_active,
            patient_id=str(user.patient_id) if user.patient_id is not None else None,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    first_name: str
    last_name: str


class RegistrationResponse(UserProfile):
    detail: str
