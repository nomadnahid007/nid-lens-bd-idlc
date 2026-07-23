from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_mode: Literal["demo", "live"] = "demo"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    max_image_size_mb: int = 8
    min_image_dimension: int = 64


@lru_cache
def get_settings() -> Settings:
    return Settings()
