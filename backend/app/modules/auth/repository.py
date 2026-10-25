from beanie import PydanticObjectId
from beanie.operators import In

from app.core.models import normalize_email
from app.modules.auth.models import User


async def get_user_by_email(email: str) -> User | None:
    return await User.find_one(User.email == normalize_email(email))


async def get_user_by_id(user_id: PydanticObjectId) -> User | None:
    return await User.get(user_id)


async def get_user_names(user_ids: set[PydanticObjectId]) -> dict[PydanticObjectId, str]:
    """Name ("First Last") of each user found, in one query (author / reviewer names)."""
    if not user_ids:
        return {}
    users = await User.find(In(User.id, list(user_ids))).to_list()
    return {user.id: f"{user.first_name} {user.last_name}" for user in users if user.id}
