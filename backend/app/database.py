from collections.abc import AsyncIterator

from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorDatabase


def get_db(request: Request) -> AsyncIterator[AsyncIOMotorDatabase]:
    yield request.app.state.db
