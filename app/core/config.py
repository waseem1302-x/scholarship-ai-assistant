from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        case_sensitive=False,
        extra="ignore",
    )

    name: str = "Scholarship AI Assistant API"
    env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    database_url: str = "postgresql+psycopg://scholarship:scholarship@localhost:5432/scholarship"
    jwt_secret: str = Field(
        default="local-development-secret-change-me-now",
        min_length=32,
        repr=False,
    )
    jwt_issuer: str = "scholarship-ai-assistant"
    jwt_audience: str = "scholarship-ai-api"
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=90)
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
