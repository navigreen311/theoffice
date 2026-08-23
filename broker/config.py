"""Broker settings.

Every value comes from the environment. There is deliberately no default that
could point at a real Forge or a real credential: a missing setting must fail
loudly at startup, not silently resolve to something plausible.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    office_app_dsn: str
    """Runtime DSN. This role cannot UPDATE or DELETE ledger rows."""

    forge_timeout_seconds: float = 30.0
    pool_min_size: int = 1
    pool_max_size: int = 10

    credential_backend: str = "env"
    """'env' for local development, 'vault' once an instance exists (0.3)."""


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
