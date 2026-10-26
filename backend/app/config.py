"""Runtime settings, read from environment variables (prefix CC_)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CC_", env_file=".env", extra="ignore")

    env: str = "development"
    database_url: str = "sqlite:///./consent_court.db"

    session_ttl_minutes: int = 60
    step_up_ttl_minutes: int = 5
    cookie_secure: bool = False
    session_cookie_name: str = "cc_session"

    token_default_ttl_seconds: int = 300
    token_max_ttl_seconds: int = 3600
    token_max_uses_limit: int = 100
    approval_ttl_minutes: int = 15

    rate_limit_auth_per_minute: int = 10
    password_min_length: int = 12

    cors_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
