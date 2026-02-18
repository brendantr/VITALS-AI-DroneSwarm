from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SCHEMA_ROOT: str = "./schemas"
    model_config = SettingsConfigDict(env_prefix="AGENT_", extra="ignore")

    # Agent B
    B_BASE_URL: str = "http://localhost:8000"
    B_TIMEOUT_S: float = 5.0

    # Agent C
    C_API_KEY: str = ""
    C_DB_PATH: str = "./agent_c.db"
