from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Deployment configuration. Everything else lives in Postgres."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = Field(validation_alias="DATABASE_URL")
    secret_key: SecretStr = Field(validation_alias="RUNPAD_SECRET_KEY", min_length=32)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # populated from the environment
