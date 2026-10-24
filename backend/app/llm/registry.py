from app.core.config import Settings, settings
from app.errors import LLMConfigurationError
from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.base import BaseProvider
from app.llm.providers.mock import MockProvider
from app.llm.providers.openai_compatible import OpenAICompatibleProvider


def active_provider_name(module: str, config: Settings = settings) -> str:
    provider, _, _, api_key = config.module_llm(module)
    if config.llm_mock or provider == "mock":
        return "mock"
    if not api_key and config.env == "dev":
        return "mock"
    return provider


def provider_for(module: str, config: Settings = settings) -> tuple[BaseProvider, str]:
    configured, base_url, model, api_key = config.module_llm(module)
    active = active_provider_name(module, config)
    if active == "mock":
        return MockProvider(), model
    if not api_key:
        raise LLMConfigurationError()
    if not model or not base_url:
        raise LLMConfigurationError("L'URL ou le modèle LLM n'est pas configuré.")
    if configured == "openai_compatible":
        return OpenAICompatibleProvider(base_url, api_key), model
    if configured == "anthropic":
        return AnthropicProvider(base_url, api_key), model
    raise LLMConfigurationError("Le fournisseur LLM configuré n'est pas pris en charge.")


def status(
    modules: list[str],
    config: Settings = settings,
) -> dict[str, dict[str, str | bool]]:
    result: dict[str, dict[str, str | bool]] = {}
    for module in modules:
        _, _, _, api_key = config.module_llm(module)
        result[module] = {
            "provider": active_provider_name(module, config),
            "key_configured": bool(api_key),
        }
    return result
