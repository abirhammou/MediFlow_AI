"""`llm_interactions`: one document per LLM call, success or failure."""

import json
import logging
from datetime import datetime

from beanie import PydanticObjectId
from beanie.operators import GTE, Eq

from app.modules.llm.models import LlmInteraction, LlmModule

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 1000


async def record_interaction(
    *,
    module: LlmModule,
    messages: list[dict[str, str]],
    success: bool,
    user_id: PydanticObjectId | None = None,
    entity_id: PydanticObjectId | None = None,
    response: str | None = None,
    model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    latency_ms: int | None = None,
    error_message: str | None = None,
) -> None:
    """Never raises: a logging failure must not break the user's request."""
    try:
        await LlmInteraction(
            module=module,
            user_id=user_id,
            entity_id=entity_id,
            prompt=json.dumps(messages, ensure_ascii=False),
            response=response,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            success=success,
            error_message=error_message[:MAX_ERROR_LENGTH] if error_message else None,
        ).insert()
    except Exception as exc:
        # The exception type only: its message could contain the prompt.
        logger.warning(
            "Journalisation de l'appel LLM impossible (module %s) : %s",
            module.value,
            type(exc).__name__,
        )


async def count_interactions(module: LlmModule, user_id: PydanticObjectId, since: datetime) -> int:
    """Calls made by a user for a module since a date (successful or not)."""
    return await LlmInteraction.find(
        Eq(LlmInteraction.module, module),
        Eq(LlmInteraction.user_id, user_id),
        GTE(LlmInteraction.created_at, since),
    ).count()
