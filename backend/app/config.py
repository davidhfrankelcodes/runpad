from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Deployment configuration. Everything else lives in Postgres."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = Field(validation_alias="DATABASE_URL")
    secret_key: SecretStr = Field(validation_alias="RUNPAD_SECRET_KEY", min_length=32)
    # Where browsers load theme.park themes from. Point it at a self-hosted theme.park
    # (https://docs.theme-park.dev/setup/#docker) to avoid the public site.
    themepark_url: str = Field(
        default="https://theme-park.dev", validation_alias="RUNPAD_THEMEPARK_URL"
    )

    @field_validator("themepark_url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        AnyHttpUrl(value)  # Raises unless it is an http(s) URL.
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # populated from the environment
