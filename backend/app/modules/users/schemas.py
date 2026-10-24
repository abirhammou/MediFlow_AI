from datetime import datetime

from pydantic import BaseModel, Field

from app.common.roles import Role, UserStatus


class UserCreateRequest(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=200)
    role: Role


class UserRoleRequest(BaseModel):
    role: Role


class PatientLinkRequest(BaseModel):
    patient_id: str = Field(min_length=1, max_length=200)


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: Role
    status: UserStatus
    patient_id: str | None
    created_at: datetime


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    size: int
