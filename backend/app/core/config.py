import os
from pathlib import Path
from typing import Literal, cast

from dotenv import dotenv_values
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["mock", "openai_compatible", "anthropic", "gemini"]
Environment = Literal["dev", "test", "prod"]
BACKEND_ROOT = Path(__file__).resolve().parents[2]
MODULES_DIRECTORY = BACKEND_ROOT / "app" / "modules"
INSECURE_JWT_SECRET = "CHANGE-ME-use-a-local-secret-of-at-least-32-characters"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    env: Environment = "dev"
    llm_mock: bool = True
    llm_timeout_seconds: float = Field(default=30, gt=0)
    # Shared LiteLLM client (app/llm/client.py): provider-prefixed model IDs.
    llm_model: str = "gemini/gemini-3.8-flash"
    llm_fallback_models: str = "groq/openai/gpt-oss-120b"
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    llm_max_retries: int = Field(default=1, ge=0, le=5)
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_max_tokens: int = Field(default=800, gt=0)
    # Thinking models (Gemini 3+): their reasoning counts against max_tokens.
    # Empty: provider default; dropped for models without reasoning.
    llm_reasoning_effort: Literal["minimal", "low", "medium", "high", ""] = "low"
    # Must authenticate as mediflow_app (readWrite on mediflow), never as root.
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "mediflow"
    cors_origins: str = "http://localhost:4200"
    expose_template: bool | None = None
    jwt_secret: str = INSECURE_JWT_SECRET
    jwt_expire_minutes: int = Field(default=60, gt=0)
    # Password of the accounts created by scripts/seed.py (empty: dev default)
    seed_password: str | None = None

    def validate_runtime_configuration(self) -> None:
        secret = self.jwt_secret.strip()
        if self.env == "prod" and (
            not secret
            or len(secret) < 32
            or secret == INSECURE_JWT_SECRET
            or "CHANGE-ME" in secret.upper()
        ):
            raise ValueError(
                "ENV=prod exige un JWT_SECRET défini, non factice et d'au moins 32 caractères."
            )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def llm_models(self) -> list[str]:
        """Primary model first, then the fallbacks in order (no duplicates)."""
        names = [self.llm_model, *self.llm_fallback_models.split(",")]
        return list(dict.fromkeys(name.strip() for name in names if name.strip()))

    def llm_api_key(self, model: str) -> str | None:
        """Key for a `provider/model` ID; None lets LiteLLM read its own env variable."""
        provider = model.split("/", 1)[0]
        secret = {"gemini": self.gemini_api_key, "groq": self.groq_api_key}.get(provider)
        if secret is None:
            return None
        return secret.get_secret_value() or None

    @property
    def should_expose_template(self) -> bool:
        if self.expose_template is not None:
            return self.expose_template
        return self.env == "dev"

    def module_llm(self, module: str) -> tuple[ProviderName, str, str, str]:
        prefix = module.upper()
        configured_values = dotenv_values(self.model_config["env_file"])

        def setting(suffix: str) -> str:
            name = f"{prefix}_LLM_{suffix}"
            return os.environ.get(name, configured_values.get(name) or "")

        provider = setting("PROVIDER") or "mock"
        if provider not in {"mock", "openai_compatible", "anthropic", "gemini"}:
            raise ValueError(f"Fournisseur LLM inconnu pour le module {module}.")
        return (
            cast(ProviderName, provider),
            setting("BASE_URL"),
            setting("MODEL"),
            setting("API_KEY"),
        )


settings = Settings()
settings.validate_runtime_configuration()
