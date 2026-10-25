import json

import pytest
from beanie import PydanticObjectId

from app.core.config import Settings, settings
from app.errors import LLMResponseError, LlmUnavailableError
from app.llm.client import MOCK_MODEL, complete, litellm_module
from app.modules.llm.models import LlmInteraction, LlmModule
from tests.conftest import FAKE_SUMMARY, FALLBACK_MODEL, PRIMARY_MODEL, TEST_GEMINI_KEY

MESSAGES = [
    {"role": "system", "content": "Consigne de test."},
    {"role": "user", "content": "Bonjour"},
]


def litellm_error(name: str, model: str = PRIMARY_MODEL, message: str = "erreur fournisseur"):
    provider = model.split("/", 1)[0]
    return getattr(litellm_module(), name)(message=message, model=model, llm_provider=provider)


async def logged() -> list[LlmInteraction]:
    return await LlmInteraction.find_all().to_list()


# --- configuration -------------------------------------------------------


def test_model_list_and_keys():
    config = Settings(
        llm_model=" groq/a ",
        llm_fallback_models="gemini/b, ,groq/a,gemini/c",
        gemini_api_key="g-key",
        groq_api_key="",
    )

    assert config.llm_models == ["groq/a", "gemini/b", "gemini/c"]
    assert config.llm_api_key("gemini/b") == "g-key"
    assert config.llm_api_key("groq/a") is None
    assert config.llm_api_key("openai/x") is None


def test_litellm_is_configured_quietly():
    litellm = litellm_module()

    assert litellm.drop_params is True
    assert litellm.telemetry is False
    assert litellm.suppress_debug_info is True


# --- calls ---------------------------------------------------------------


async def test_success_is_logged(db, fake_llm):
    user_id, entity_id = PydanticObjectId(), PydanticObjectId()

    result = await complete(
        module=LlmModule.PATIENT_RECORD, messages=MESSAGES, user_id=user_id, entity_id=entity_id
    )

    assert result.text == FAKE_SUMMARY
    assert result.model == PRIMARY_MODEL
    assert (result.tokens_in, result.tokens_out) == (120, 80)
    call = fake_llm.calls[0]
    assert call["api_key"] == TEST_GEMINI_KEY
    assert call["temperature"] == settings.llm_temperature
    assert call["max_tokens"] == settings.llm_max_tokens
    assert call["timeout"] == settings.llm_timeout_seconds
    [row] = await logged()
    assert row.success is True
    assert row.module == LlmModule.PATIENT_RECORD
    assert (row.user_id, row.entity_id) == (user_id, entity_id)
    assert json.loads(row.prompt) == MESSAGES
    assert row.response == FAKE_SUMMARY
    assert row.model == PRIMARY_MODEL
    assert (row.tokens_in, row.tokens_out) == (120, 80)
    assert isinstance(row.latency_ms, int)
    raw = await db.llm_interactions.find_one({})
    assert TEST_GEMINI_KEY not in str(raw)


async def test_rate_limit_goes_to_the_fallback_without_retry(db, fake_llm):
    fake_llm.set(PRIMARY_MODEL, litellm_error("RateLimitError"))

    result = await complete(module=LlmModule.FAQ, messages=MESSAGES)

    assert result.model == FALLBACK_MODEL
    assert fake_llm.models_called() == [PRIMARY_MODEL, FALLBACK_MODEL]
    [row] = await logged()
    assert row.success is True
    assert row.model == FALLBACK_MODEL
    assert "RateLimitError" in row.error_message


async def test_timeout_is_retried_then_falls_back(db, fake_llm):
    fake_llm.set(PRIMARY_MODEL, litellm_error("Timeout"))

    result = await complete(module=LlmModule.FAQ, messages=MESSAGES)

    assert result.model == FALLBACK_MODEL
    assert fake_llm.models_called() == [PRIMARY_MODEL, PRIMARY_MODEL, FALLBACK_MODEL]


async def test_transient_error_recovers_on_retry(db, fake_llm):
    fake_llm.set(PRIMARY_MODEL, litellm_error("InternalServerError"), "Réponse")

    result = await complete(module=LlmModule.FAQ, messages=MESSAGES)

    assert (result.model, result.text) == (PRIMARY_MODEL, "Réponse")
    assert fake_llm.models_called() == [PRIMARY_MODEL, PRIMARY_MODEL]


async def test_auth_error_and_missing_key_go_to_the_fallback(db, fake_llm, monkeypatch):
    fake_llm.set(PRIMARY_MODEL, litellm_error("AuthenticationError"))
    assert (await complete(module=LlmModule.FAQ, messages=MESSAGES)).model == FALLBACK_MODEL

    fake_llm.calls.clear()
    monkeypatch.setattr(settings, "gemini_api_key", None)
    assert (await complete(module=LlmModule.FAQ, messages=MESSAGES)).model == FALLBACK_MODEL
    assert fake_llm.models_called() == [FALLBACK_MODEL]  # no call without a key


async def test_empty_answer_is_a_failure(db, fake_llm):
    fake_llm.set(PRIMARY_MODEL, "   ")

    result = await complete(module=LlmModule.FAQ, messages=MESSAGES)

    assert result.model == FALLBACK_MODEL


async def test_bad_request_does_not_fall_back(db, fake_llm):
    fake_llm.set(PRIMARY_MODEL, litellm_error("BadRequestError"))

    with pytest.raises(LlmUnavailableError):
        await complete(module=LlmModule.FAQ, messages=MESSAGES)

    assert fake_llm.models_called() == [PRIMARY_MODEL]
    [row] = await logged()
    assert row.success is False
    assert "BadRequestError" in row.error_message


async def test_all_models_failing_is_a_logged_503(db, fake_llm):
    fake_llm.set(PRIMARY_MODEL, litellm_error("RateLimitError"))
    fake_llm.set(FALLBACK_MODEL, litellm_error("ServiceUnavailableError", FALLBACK_MODEL))

    with pytest.raises(LlmUnavailableError) as raised:
        await complete(module=LlmModule.FAQ, messages=MESSAGES)

    assert raised.value.status_code == 503
    [row] = await logged()
    assert row.success is False
    assert row.response is None
    assert PRIMARY_MODEL in row.error_message and FALLBACK_MODEL in row.error_message


async def test_error_messages_never_contain_a_key(db, fake_llm):
    fake_llm.set(
        PRIMARY_MODEL, litellm_error("AuthenticationError", message=f"bad {TEST_GEMINI_KEY}")
    )

    await complete(module=LlmModule.FAQ, messages=MESSAGES)

    [row] = await logged()
    assert TEST_GEMINI_KEY not in row.error_message
    assert "***" in row.error_message


async def test_postprocess_failure_is_logged_and_raised(db, fake_llm):
    def reject(_: str) -> str:
        raise LLMResponseError()

    with pytest.raises(LLMResponseError):
        await complete(module=LlmModule.FAQ, messages=MESSAGES, postprocess=reject)

    assert fake_llm.models_called() == [PRIMARY_MODEL]  # the request was answered: no fallback
    [row] = await logged()
    assert row.success is False
    assert row.response == FAKE_SUMMARY


async def test_logging_failure_never_breaks_the_call(db, fake_llm, monkeypatch):
    async def broken_insert(*_, **__):
        raise RuntimeError("MongoDB down")

    monkeypatch.setattr(LlmInteraction, "insert", broken_insert)

    result = await complete(module=LlmModule.FAQ, messages=MESSAGES)

    assert result.text == FAKE_SUMMARY


async def test_groq_only_needs_no_code_change(db, fake_llm, monkeypatch):
    monkeypatch.setattr(settings, "llm_model", FALLBACK_MODEL)
    monkeypatch.setattr(settings, "llm_fallback_models", "")
    fake_llm.set(FALLBACK_MODEL, litellm_error("RateLimitError", FALLBACK_MODEL))

    with pytest.raises(LlmUnavailableError):
        await complete(module=LlmModule.FAQ, messages=MESSAGES)

    assert fake_llm.models_called() == [FALLBACK_MODEL]


async def test_mock_mode_calls_no_provider(db, fake_llm, monkeypatch):
    monkeypatch.setattr(settings, "llm_mock", True)

    result = await complete(module=LlmModule.FAQ, messages=MESSAGES)

    assert result.model == MOCK_MODEL
    assert fake_llm.calls == []
