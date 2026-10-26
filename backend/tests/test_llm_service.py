import httpx
import pytest
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.errors import LLMConfigurationError, LLMResponseError
from app.llm.anonymizer import anonymize
from app.llm.providers.openai_compatible import OpenAICompatibleProvider
from app.llm.registry import provider_for
from app.llm.service import generate_json


class ExampleOutput(BaseModel):
    answer: str = Field(min_length=1)


@pytest.mark.asyncio
async def test_mock_provider_returns_validated_schema():
    response = await generate_json(
        module="template",
        system="Réponds au format requis.",
        user="Texte de test",
        output_schema=ExampleOutput,
    )

    assert isinstance(response, ExampleOutput)
    assert response.answer


@pytest.mark.asyncio
async def test_service_anonymizes_and_retries_invalid_json(monkeypatch):
    calls = []

    class Provider:
        async def complete_json(self, system, user, model, timeout):
            calls.append((system, user))
            return "not JSON" if len(calls) == 1 else '{"answer":"ok"}'

    monkeypatch.setattr(
        "app.llm.service.provider_for",
        lambda module: (Provider(), "model-from-env"),
    )
    result = await generate_json(
        module="template",
        system="Résume sans révéler l'identité.",
        user="Contacte alice@example.test au +33 6 12 34 56 78.",
        output_schema=ExampleOutput,
    )

    assert result.answer == "ok"
    assert len(calls) == 2
    assert "alice@example.test" not in calls[0][1]
    assert "+33 6 12 34 56 78" not in calls[0][1]
    assert "[EMAIL]" in calls[0][1]
    assert "[TÉLÉPHONE]" in calls[0][1]


@pytest.mark.parametrize(
    "text",
    ["Appeler le 98 765 432", "Appeler le 98765432", "Appeler le 98 76 54 32", "+216 51 964 422"],
)
def test_local_phone_numbers_are_masked(text):
    assert anonymize(text).endswith("[TÉLÉPHONE]")


@pytest.mark.parametrize(
    "text", ["RDV le 2026-10-30 à 09:30", "Dossier PAT-2026-00001", "Montant 1 250 000 millimes"]
)
def test_dates_and_record_numbers_are_kept(text):
    assert anonymize(text) == text


@pytest.mark.asyncio
async def test_service_returns_502_after_second_invalid_response(monkeypatch):
    class Provider:
        async def complete_json(self, system, user, model, timeout):
            return "not JSON"

    monkeypatch.setattr(
        "app.llm.service.provider_for",
        lambda module: (Provider(), "model-from-env"),
    )

    with pytest.raises(LLMResponseError):
        await generate_json(
            module="template",
            system="Instructions",
            user="Contenu",
            output_schema=ExampleOutput,
        )


@pytest.mark.asyncio
async def test_openai_compatible_provider_includes_sanitized_upstream_error(monkeypatch):
    api_key = "gsk_private_test_key"

    class ErrorResponseClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, *args, **kwargs):
            return httpx.Response(
                401,
                json={"error": {"message": f"Invalid API Key: {api_key}"}},
                request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
            )

    monkeypatch.setattr(
        "app.llm.providers.openai_compatible.httpx.AsyncClient",
        ErrorResponseClient,
    )
    provider = OpenAICompatibleProvider("https://api.groq.com/openai/v1", api_key)

    with pytest.raises(LLMResponseError) as error:
        await provider.complete_json(
            system="JSON",
            user="Synthetic test",
            model="test-model",
            timeout=1,
        )

    assert error.value.status_code == 502
    assert "HTTP 401" in error.value.detail
    assert "Invalid API Key" in error.value.detail
    assert api_key not in error.value.detail


def test_missing_key_in_production_is_a_typed_503(monkeypatch):
    monkeypatch.setenv("TEMPLATE_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("TEMPLATE_LLM_BASE_URL", "https://example.test")
    monkeypatch.setenv("TEMPLATE_LLM_MODEL", "example-model")
    monkeypatch.setenv("TEMPLATE_LLM_API_KEY", "")
    config = Settings(llm_mock=False, env="prod")

    with pytest.raises(LLMConfigurationError):
        provider_for("template", config)
