import os
from pathlib import Path
from typing import Literal, cast

from dotenv import dotenv_values
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ProviderName = Literal["mock", "openai_compatible", "anthropic"]
MODULES_DIRECTORY = Path(__file__).resolve().parent / "modules"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_mock: bool = True
    llm_timeout_seconds: float = Field(default=20, gt=0)
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "mediflow"
    cors_origins: str = "http://localhost:4200"
    environment: str = "development"
    expose_template: bool | None = None

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
