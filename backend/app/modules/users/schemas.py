from pydantic import BaseModel, Field

from app.modules.auth.models import EMAIL_PATTERN, Role
from app.modules.auth.schemas import UserProfile


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    role: Role


class UserRoleRequest(BaseModel):
    role: Role


class PatientLinkRequest(BaseModel):
    patient_id: str = Field(min_length=1, max_length=200)


UserResponse = UserProfile


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    size: int
