import json
import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.errors import APIError, LLMResponseError
from app.llm.anonymizer import anonymize
from app.llm.registry import provider_for

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


async def generate_json(
    module: str,
    system: str,
    user: str,
    output_schema: type[T],
) -> T:
    provider, model = provider_for(module)
    schema_json = json.dumps(output_schema.model_json_schema(), ensure_ascii=False)
    safe_system = anonymize(system)
    safe_user = anonymize(user)
    safe_system = (
        f"{safe_system}\nRéponds uniquement avec un objet JSON conforme au schéma.\n"
        f"<output_schema>{schema_json}</output_schema>"
    )

    for attempt in range(2):
        try:
            response = await provider.complete_json(
                system=safe_system,
                user=(
                    safe_user
                    if attempt == 0
                    else f"{safe_user}\nLa réponse précédente était invalide; renvoie uniquement le JSON conforme."
                ),
                model=model,
                timeout=settings.llm_timeout_seconds,
            )
        except APIError as exc:
            logger.warning("LLM request failed for module %s (%s)", module, exc.code)
            raise
        try:
            data = json.loads(response)
            return output_schema.model_validate(data)
        except (json.JSONDecodeError, TypeError, ValidationError):
            if attempt == 1:
                raise LLMResponseError() from None
    raise LLMResponseError()
