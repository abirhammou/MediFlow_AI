from collections.abc import Callable
from typing import Any

import jwt
from beanie import PydanticObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.errors import APIError
from app.modules.auth.models import Role, User
from app.modules.auth.repository import get_user_by_id
from app.modules.patient_portal.accounts import needs_password_change
from app.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _invalid_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Jeton invalide ou expiré.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    try:
        claims = decode_token(token)
        user_id = PydanticObjectId(claims["sub"])
    except (jwt.PyJWTError, InvalidId, TypeError) as exc:
        raise _invalid_token() from exc

    user = await get_user_by_id(user_id)
    if user is None:
        raise _invalid_token()
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Le compte n'est pas actif.",
        )
    return user


def require_roles(*roles: Role) -> Callable[..., Any]:
    async def check_role(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Rôle non autorisé.",
            )
        # Temporary password of a clinic-created PATIENT account: /api/auth/me and
        # /api/auth/change-password (plain get_current_user) still answer, nothing else.
        if await needs_password_change(user):
            raise APIError(
                403,
                "password_change_required",
                "Changez votre mot de passe temporaire avant de continuer.",
            )
        return user

    return check_role


def owns_patient_record(user: User, patient_id: str) -> None:
    if user.role != Role.PATIENT:
        return
    if str(user.patient_id or "") != patient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès limité à votre propre dossier patient.",
        )
