import os
from pathlib import Path
from typing import Literal, cast

from dotenv import dotenv_values
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ProviderName = Literal["mock", "openai_compatible", "anthropic"]
INSECURE_JWT_SECRET = "CHANGE-ME-use-a-local-secret-of-at-least-32-characters"
MODULES_DIRECTORY = Path(__file__).resolve().parent / "modules"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    llm_mock: bool = True
    llm_timeout_seconds: float = Field(default=20, gt=0)
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "mediflow"
    cors_origins: str = "http://localhost:4200"
    app_env: Literal["development", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "ENVIRONMENT"),
    )
    expose_template: bool | None = None
    jwt_secret: str = INSECURE_JWT_SECRET
    jwt_expire_minutes: int = Field(default=60, gt=0)
    admin_email: str | None = None
    admin_password: str | None = None

    @property
    def environment(self) -> str:
        return self.app_env

    def validate_runtime_configuration(self) -> None:
        secret = self.jwt_secret.strip()
        if self.app_env == "production" and (
            not secret
            or len(secret) < 32
            or secret == INSECURE_JWT_SECRET
            or "CHANGE-ME" in secret.upper()
        ):
            raise ValueError(
                "APP_ENV=production exige un JWT_SECRET défini, non factice et "
                "d'au moins 32 caractères."
            )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def should_expose_template(self) -> bool:
        if self.expose_template is not None:
            return self.expose_template
        return self.environment == "development"

    def module_llm(self, module: str) -> tuple[ProviderName, str, str, str]:
        prefix = module.upper()
        configured_values = dotenv_values(self.model_config["env_file"])

        def setting(suffix: str) -> str:
            name = f"{prefix}_LLM_{suffix}"
            return os.environ.get(name, configured_values.get(name) or "")

        provider = setting("PROVIDER") or "mock"
        if provider not in {"mock", "openai_compatible", "anthropic"}:
            raise ValueError(f"Fournisseur LLM inconnu pour le module {module}.")
        return (
            cast(ProviderName, provider),
            setting("BASE_URL"),
            setting("MODEL"),
            setting("API_KEY"),
        )


settings = Settings()
settings.validate_runtime_configuration()


settings = Settings()
