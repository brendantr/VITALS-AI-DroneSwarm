from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from agent_c.clients.agent_b import AgentBClient
from agent_c.clients.publisher import Publisher
from agent_c.clients.trtllm import TRTLLMClient
from agent_c.core.executor import Executor
from agent_c.core.models import ACPIntent, Plan
from agent_c.core.planner import DeterministicPlanner, LLMPlanner
from agent_c.storage.store import RunStore


class Coordinator:
    def __init__(
        self,
        store: RunStore,
        agent_b: AgentBClient,
        publisher: Publisher,
        llm: TRTLLMClient,
        *,
        llm_enabled: bool,
        llm_max_tokens: int,
        llm_temperature: float,
    ):
        self.store = store
        self.agent_b = agent_b
        self.publisher = publisher
        self.llm_enabled = llm_enabled

        self.det_planner = DeterministicPlanner()
        self.llm_planner = LLMPlanner(llm, max_tokens=llm_max_tokens, temperature=llm_temperature)
        self.exec = Executor()

    async def plan_and_act_intent(self, intent: ACPIntent) -> Dict[str, Any]:
        corr_id = intent.corr_id or "missing"
        run = self.store.get_run(corr_id)
        ctx = run.get("context") or {}

        if self.llm_enabled:
            plan: Plan = await self.llm_planner.plan(intent, ctx)
        else:
            plan = self.det_planner.plan(intent, ctx)

        self.store.update_context(corr_id, {"last_plan": plan.model_dump(mode="json"), "last_plan_error": None})

        from agent_c.core.tools import ToolContext
        tool_ctx = ToolContext(
            corr_id=corr_id,
            intent=intent,
            store=self.store,
            agent_b=self.agent_b,
            publisher=self.publisher,
        )
        return await self.exec.run(tool_ctx, plan)


class Worker:
    def __init__(self, coordinator: Coordinator, queue_max: int = 256):
        self.coordinator = coordinator
        self.queue: asyncio.Queue[ACPIntent] = asyncio.Queue(maxsize=queue_max)
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None

    async def enqueue_intent(self, intent: ACPIntent) -> bool:
        await self.queue.put(intent)
        return True

    async def _run_loop(self) -> None:
        while True:
            intent = await self.queue.get()
            corr_id = intent.corr_id or "missing"
            try:
                out = await self.coordinator.plan_and_act_intent(intent)
                run = self.coordinator.store.get_run(corr_id)
                dc = run["context"].get("dispatch_counts") or {}
                dc["planned"] = int(dc.get("planned", 0)) + 1
                self.coordinator.store.update_context(corr_id, {"dispatch_counts": dc, "last_exec": out})
            except Exception as e:
                self.coordinator.store.update_context(corr_id, {"last_plan_error": str(e)})
            finally:
                self.queue.task_done()
