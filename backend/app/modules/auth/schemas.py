from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.common.roles import Role, UserStatus


class RegisterRequest(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=200)
    role_requested: Literal["patient", "doctor", "secretary", "admin"] | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class UserProfile(BaseModel):
    id: str
    email: str
    full_name: str
    role: Role
    status: UserStatus
    patient_id: str | None
    created_at: datetime


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    status: UserStatus
    full_name: str


class RegistrationResponse(UserProfile):
    detail: str
