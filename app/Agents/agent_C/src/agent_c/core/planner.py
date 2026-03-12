from __future__ import annotations

import json
from uuid import uuid4
from typing import Any, Dict

from pydantic import ValidationError

from agent_c.clients.trtllm import TRTLLMClient
from agent_c.core.models import ACPIntent, Plan
from agent_c.core.state import intent_to_text


PLAN_JSON_SCHEMA_HINT = {
  "plan_id": "string",
  "actions": [
    {"tool": "emit.status", "args": {"state": "planning", "detail": "..."}},
    {"tool": "agentb.query", "args": {"query": "...", "rerank": False, "where": {}}},
    {"tool": "emit.status", "args": {"state": "proposed", "detail": "..."}},
    {"tool": "emit.result", "args": {"outcome": "success", "summary": "..."}},
  ],
  "rationale": "string (optional)"
}


class DeterministicPlanner:
    def plan(self, intent: ACPIntent, run_context: Dict[str, Any]) -> Plan:
        q = intent_to_text(intent)
        return Plan(
            plan_id=f"plan-{uuid4().hex[:8]}",
            actions=[
                {"tool": "emit.status", "args": {"state": "planning", "detail": "planning started"}},
                {"tool": "agentb.query", "args": {"query": q, "rerank": False, "where": {}}},
                {"tool": "emit.status", "args": {"state": "proposed", "detail": "proposal ready"}},
                {"tool": "emit.result", "args": {"outcome": "success", "summary": "retrieval complete"}},
            ],
            rationale="deterministic bootstrap plan",
        )


class LLMPlanner:
    def __init__(self, llm: TRTLLMClient, max_tokens: int = 512, temperature: float = 0.0):
        self.llm = llm
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def plan(self, intent: ACPIntent, run_context: Dict[str, Any]) -> Plan:
        intent_text = intent_to_text(intent)

        system = (
            "You are AgentC Planner. Output ONLY valid JSON. No prose, no markdown.\n"
            "Return a plan that uses ONLY these tools: agentb.query, emit.status, emit.result.\n"
            "Ensure JSON parses.\n"
        )
        user = (
            "Intent:\n"
            f"{intent_text}\n\n"
            "Run context (may be empty):\n"
            f"{json.dumps(run_context, ensure_ascii=False)[:2000]}\n\n"
            "Return JSON matching this shape:\n"
            f"{json.dumps(PLAN_JSON_SCHEMA_HINT, ensure_ascii=False)}\n"
        )

        res = await self.llm.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        if not res.ok:
            raise RuntimeError(f"LLM error: {res.error}")

        text = res.content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            lines = text.splitlines()
            if lines and lines[0].strip().lower() == "json":
                text = "\n".join(lines[1:])

        try:
            obj = json.loads(text)
        except Exception as e:
            repair_user = (
                "Your previous output was not valid JSON. Return ONLY corrected JSON.\n"
                f"Error: {e}\n"
                "Original output:\n"
                f"{res.content[:1500]}\n"
            )
            res2 = await self.llm.chat(
                [{"role": "system", "content": system}, {"role": "user", "content": repair_user}],
                max_tokens=self.max_tokens,
                temperature=0.0,
            )
            if not res2.ok:
                raise RuntimeError(f"LLM repair error: {res2.error}")
            text2 = res2.content.strip()
            if text2.startswith("```"):
                text2 = text2.strip("`")
                lines = text2.splitlines()
                if lines and lines[0].strip().lower() == "json":
                    text2 = "\n".join(lines[1:])
            obj = json.loads(text2)

        try:
            return Plan.model_validate(obj)
        except ValidationError as e:
            raise RuntimeError(f"Plan validation failed: {e}")
