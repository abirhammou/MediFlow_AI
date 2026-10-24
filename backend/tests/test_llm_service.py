import pytest
from pydantic import BaseModel, Field

from app.config import Settings
from app.errors import LLMResponseError
from app.errors import LLMConfigurationError
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


def test_missing_key_in_production_is_a_typed_503(monkeypatch):
    monkeypatch.setenv("TEMPLATE_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("TEMPLATE_LLM_BASE_URL", "https://example.test")
    monkeypatch.setenv("TEMPLATE_LLM_MODEL", "example-model")
    monkeypatch.setenv("TEMPLATE_LLM_API_KEY", "")
    config = Settings(llm_mock=False, environment="production")

    with pytest.raises(LLMConfigurationError):
        provider_for("template", config)
