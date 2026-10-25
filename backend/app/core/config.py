import os
from pathlib import Path
from typing import Literal, cast

from dotenv import dotenv_values
from pydantic import Field
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
    llm_timeout_seconds: float = Field(default=20, gt=0)
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
                "ENV=prod exige un JWT_SECRET défini, non factice et "
                "d'au moins 32 caractères."
            )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

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
