from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_", extra="ignore")

    # Shared schemas
    SCHEMA_ROOT: str = "./schemas"

    # Agent C
    C_API_KEY: str = ""
    C_DB_PATH: str = "./agent_c.db"

    # Downstream Agent B
    B_BASE_URL: str = "http://localhost:8000"
    B_TIMEOUT_S: float = 5.0

    # TRT-LLM sidecar (OpenAI-like server)
    TRTLLM_BASE_URL: str = "http://127.0.0.1:8002"
    TRTLLM_MODEL: str = "tensorrt_llm"
    TRTLLM_TIMEOUT_S: float = 120.0

    # LLM planning
    LLM_ENABLED: bool = False
    LLM_MAX_TOKENS: int = 512
    LLM_TEMPERATURE: float = 0.0
    MAX_LLM_CONCURRENCY: int = 1

    # Worker
    WORKER_QUEUE_MAX: int = 256

    # Outbound publisher (optional)
    PUBLISH_URL: str = ""  # e.g. http://localhost:9000/messages
