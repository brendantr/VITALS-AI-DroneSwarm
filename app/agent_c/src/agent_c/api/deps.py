from __future__ import annotations

from agents_common.schema_validator import SchemaValidator

from agent_c.clients.agent_b import HttpAgentBClient, AgentBClient
from agent_c.clients.publisher import HttpPublisher, NullPublisher, Publisher
from agent_c.clients.trtllm import TRTLLMClient
from agent_c.core.coordinator import Coordinator, Worker
from agent_c.core.publisher_loop import OutboxPublisher
from agent_c.storage.store import RunStore
from agent_c.utils.config import Settings


settings = Settings()

schema_validator = SchemaValidator(settings.SCHEMA_ROOT)
store = RunStore(settings.C_DB_PATH)
agent_b = HttpAgentBClient(settings.B_BASE_URL, timeout_s=settings.B_TIMEOUT_S)
publisher: Publisher = HttpPublisher(settings.PUBLISH_URL) if settings.PUBLISH_URL else NullPublisher()

llm = TRTLLMClient(
    base_url=settings.TRTLLM_BASE_URL,
    model=settings.TRTLLM_MODEL,
    timeout_s=settings.TRTLLM_TIMEOUT_S,
    max_concurrency=settings.MAX_LLM_CONCURRENCY,
)

coordinator = Coordinator(
    store=store,
    agent_b=agent_b,
    publisher=publisher,
    llm=llm,
    llm_enabled=settings.LLM_ENABLED,
    llm_max_tokens=settings.LLM_MAX_TOKENS,
    llm_temperature=settings.LLM_TEMPERATURE,
)

worker = Worker(coordinator, queue_max=settings.WORKER_QUEUE_MAX)
outbox_publisher = OutboxPublisher(store, publisher)


def get_settings() -> Settings:
    return settings

def get_schema_validator() -> SchemaValidator:
    return schema_validator

def get_store() -> RunStore:
    return store

def get_agent_b() -> AgentBClient:
    return agent_b

def get_worker() -> Worker:
    return worker

def get_outbox_publisher() -> OutboxPublisher:
    return outbox_publisher

def get_llm() -> TRTLLMClient:
    return llm
