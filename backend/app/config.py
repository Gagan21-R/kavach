"""Runtime settings, read from environment variables (prefix CC_)."""
import os
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

    # Policy fetching. The contact goes in the User-Agent so site owners can reach whoever runs the bot.
    fetch_contact: str = "set CC_FETCH_CONTACT to a contact email"
    fetch_cache_minutes: int = 360
    fetch_render_enabled: bool = True  # headless Chromium for pages that need JavaScript (if installed)
    watch_scheduler_enabled: bool = True  # automatic Watchman checks while the server runs (app.serve)
    watch_interval_minutes: int = 360

    # Email signals. Forwarding addresses look like kavach+<token>@<inbound_domain>; the provider webhook
    # must send X-Inbound-Secret. An empty secret turns the webhook off.
    inbound_domain: str = "inbox.kavach.local"
    inbound_secret: str = ""
    imap_host: str = ""
    imap_user: str = ""
    imap_password: str = ""


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # On Render the site's own URL is a fine bot contact when no other one is set.
    if not os.environ.get("CC_FETCH_CONTACT") and os.environ.get("RENDER_EXTERNAL_URL"):
        s.fetch_contact = os.environ["RENDER_EXTERNAL_URL"]
    return s
