from collections.abc import Callable, Mapping
from typing import Any

import jwt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.common.roles import Role, UserStatus
from app.database import get_db
from app.security import decode_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    database: AsyncIOMotorDatabase = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> dict[str, Any]:
    try:
        claims = decode_token(token)
        user_id = ObjectId(claims["sub"])
    except (jwt.PyJWTError, InvalidId, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton invalide ou expiré.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await database["users"].find_one({"_id": user_id})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton invalide ou expiré.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.get("status") != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Le compte n'est pas actif.",
        )
    return user


def require_roles(*roles: Role) -> Callable[..., Any]:
    async def check_role(
        user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        if user.get("status") != UserStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Le compte n'est pas actif.",
            )
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Rôle non autorisé.",
            )
        return user

    return check_role


def owns_patient_record(user: Mapping[str, Any], patient_id: str) -> None:
    if user.get("role") != Role.PATIENT:
        return
    if str(user.get("patient_id") or "") != patient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès limité à votre propre dossier patient.",
        )
