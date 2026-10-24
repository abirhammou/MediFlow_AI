from beanie.operators import Eq

from app.modules.auth.models import Role, User


async def list_users(
    *,
    is_active: bool | None,
    role: Role | None,
    skip: int,
    limit: int,
) -> tuple[list[User], int]:
    filters = []
    if is_active is not None:
        filters.append(Eq(User.is_active, is_active))
    if role is not None:
        filters.append(Eq(User.role, role))
    query = User.find(*filters)
    total = await query.count()
    items = await query.sort(-User.created_at, -User.id).skip(skip).limit(limit).to_list()
    return items, total


async def count_active_admins() -> int:
    return await User.find(Eq(User.role, Role.ADMIN), Eq(User.is_active, True)).count()
