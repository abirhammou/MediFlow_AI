"""Provider-agnostic chat completions through LiteLLM, shared by every module.

The models come from the settings: LLM_MODEL first, then LLM_FALLBACK_MODELS in
order (IDs prefixed by the provider, e.g. `gemini/...`, `groq/...`). Switching
provider only changes .env. Every `complete()` call writes one
`llm_interactions` document, whatever the outcome.
"""

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from beanie import PydanticObjectId

from app.core.config import settings
from app.errors import LlmUnavailableError
from app.llm.interactions import record_interaction
from app.modules.llm.models import LlmModule

Message = dict[str, str]

MOCK_MODEL = "mock"
MOCK_RESPONSE = "Réponse simulée (LLM_MOCK=true) : aucun modèle n'a été appelé."
# Provider prefix -> environment variable LiteLLM would read the key from.
KEY_VARIABLES = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY"}


@dataclass(frozen=True)
class LlmResult:
    text: str
    model: str
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: int


class EmptyCompletionError(Exception):
    """The model answered without any text."""


class MissingApiKeyError(Exception):
    """No key configured for the model's provider."""


_litellm: ModuleType | None = None


def litellm_module() -> ModuleType:
    """LiteLLM, imported on first use (slow import) and configured once."""
    global _litellm
    if _litellm is None:
        # Bundled model cost map: no download from GitHub when LiteLLM is imported.
        os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
        import litellm

        litellm.drop_params = True  # providers accept different parameters
        litellm.telemetry = False
        litellm.suppress_debug_info = True
        litellm.turn_off_message_logging = True
        for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
            logging.getLogger(name).setLevel(logging.ERROR)
        _litellm = litellm
    return _litellm


def _is_request_error(exc: Exception) -> bool:
    """A 400/422 caused by our own request: another model would fail the same way."""
    litellm = litellm_module()
    return isinstance(exc, litellm.BadRequestError | litellm.UnprocessableEntityError)


def _is_transient(exc: Exception) -> bool:
    """Worth retrying on the same model (rate limits and auth errors go to the next one)."""
    litellm = litellm_module()
    return isinstance(
        exc,
        litellm.Timeout
        | litellm.APIConnectionError
        | litellm.InternalServerError
        | litellm.ServiceUnavailableError
        | litellm.BadGatewayError
        | EmptyCompletionError,
    )


def describe_error(model: str, exc: Exception) -> str:
    message = f"{model}: {type(exc).__name__}: {exc}"
    for key in (settings.gemini_api_key, settings.groq_api_key):
        if key is not None and key.get_secret_value():
            message = message.replace(key.get_secret_value(), "***")
    return message


async def call_model(
    model: str,
    messages: list[Message],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
) -> LlmResult:
    """One request to one model, without retry, fallback or logging."""
    provider = model.split("/", 1)[0]
    api_key = settings.llm_api_key(model)
    if api_key is None and provider in KEY_VARIABLES:
        raise MissingApiKeyError(f"{KEY_VARIABLES[provider]} n'est pas configurée.")

    options: dict[str, Any] = {}
    if response_format is not None:
        options["response_format"] = response_format
    if settings.llm_reasoning_effort:
        options["reasoning_effort"] = settings.llm_reasoning_effort
    started = time.perf_counter()
    response = await litellm_module().acompletion(
        model=model,
        messages=messages,
        api_key=api_key,
        timeout=settings.llm_timeout_seconds,
        temperature=settings.llm_temperature if temperature is None else temperature,
        max_tokens=max_tokens or settings.llm_max_tokens,
        num_retries=0,  # retries and fallbacks are handled by complete()
        max_retries=0,
        **options,
    )
    latency_ms = round((time.perf_counter() - started) * 1000)
    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise EmptyCompletionError("Réponse vide.")
    usage = getattr(response, "usage", None)
    return LlmResult(
        text=text,
        model=model,
        tokens_in=getattr(usage, "prompt_tokens", None),
        tokens_out=getattr(usage, "completion_tokens", None),
        latency_ms=latency_ms,
    )


async def complete(
    *,
    module: LlmModule,
    messages: list[Message],
    entity_id: PydanticObjectId | None = None,
    user_id: PydanticObjectId | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    postprocess: Callable[[str], str] | None = None,
) -> LlmResult:
    """Primary model, then each fallback; raises LlmUnavailableError (503) if all fail.

    Timeouts, connection and 5xx errors are retried on the same model
    (LLM_MAX_RETRIES times); rate limits (429), auth errors and missing keys go
    straight to the next model. A 400 caused by the request stops at once.
    `postprocess` checks or cleans the text; whatever it raises is logged as a
    failure and re-raised (no fallback: the request itself was answered).
    """

    async def log(success: bool, **fields: Any) -> None:
        await record_interaction(
            module=module,
            messages=messages,
            user_id=user_id,
            entity_id=entity_id,
            success=success,
            **fields,
        )

    started = time.perf_counter()
    errors: list[str] = []
    models = [MOCK_MODEL] if settings.llm_mock else settings.llm_models
    if not models:
        errors.append("LLM_MODEL n'est pas configuré.")

    for model in models:
        for attempt in range(settings.llm_max_retries + 1):
            try:
                if model == MOCK_MODEL:
                    result = LlmResult(MOCK_RESPONSE, MOCK_MODEL, None, None, 0)
                else:
                    result = await call_model(
                        model,
                        messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format=response_format,
                    )
            except Exception as exc:
                errors.append(describe_error(model, exc))
                if _is_request_error(exc):
                    await log(False, model=model, error_message="\n".join(errors))
                    raise LlmUnavailableError() from exc
                if _is_transient(exc) and attempt < settings.llm_max_retries:
                    continue
                break  # next model

            usage = {
                "model": result.model,
                "response": result.text,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "latency_ms": result.latency_ms,
            }
            if postprocess is not None:
                try:
                    result = LlmResult(
                        postprocess(result.text),
                        result.model,
                        result.tokens_in,
                        result.tokens_out,
                        result.latency_ms,
                    )
                except Exception as exc:
                    await log(False, **usage, error_message=describe_error(model, exc))
                    raise
            await log(True, **usage, error_message="\n".join(errors) or None)
            return result

    latency_ms = round((time.perf_counter() - started) * 1000)
    await log(False, latency_ms=latency_ms, error_message="\n".join(errors))
    raise LlmUnavailableError()
