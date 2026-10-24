from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.core.config import settings
from app.core.db import create_client, get_db, init_db
from app.errors import APIError, register_error_handlers
from app.modules.discovery import include_discovered_routers
from app.modules.llm_router import router as llm_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    client = create_client(settings.mongodb_uri)
    app.state.mongo_client = client
    app.state.db = client[settings.mongodb_db]
    try:
        await init_db(app.state.db)
        yield
    finally:
        await client.close()


app = FastAPI(title="MediFlow API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)


@app.get("/api/health")
async def health(database: AsyncDatabase = Depends(get_db)) -> dict[str, str]:
    try:
        await database.command("ping")
    except PyMongoError:
        raise APIError(503, "database_unavailable", "La base de données est injoignable.") from None
    return {"status": "ok", "database": "ok"}


include_discovered_routers(app)
app.include_router(llm_router, prefix="/api/llm", tags=["llm"])
