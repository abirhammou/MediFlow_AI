from beanie import PydanticObjectId

from app.core.models import normalize_email
from app.modules.auth.models import User


async def get_user_by_email(email: str) -> User | None:
    return await User.find_one(User.email == normalize_email(email))


async def get_user_by_id(user_id: PydanticObjectId) -> User | None:
    return await User.get(user_id)
