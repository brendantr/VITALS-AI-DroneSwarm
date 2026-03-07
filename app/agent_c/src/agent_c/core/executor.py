from __future__ import annotations

from typing import Any, Dict

from agent_c.core.models import Plan
from agent_c.core.tools import ToolContext, build_tool_registry


class Executor:
    def __init__(self):
        self.tools = build_tool_registry()

    async def run(self, ctx: ToolContext, plan: Plan) -> Dict[str, Any]:
        results: list[dict[str, Any]] = []
        for call in plan.actions:
            fn = self.tools.get(call.tool)
            if not fn:
                results.append({"tool": call.tool, "ok": False, "error": "unknown_tool"})
                continue
            try:
                out = await fn(ctx, **call.args)
                results.append({"tool": call.tool, **out})
            except Exception as e:
                results.append({"tool": call.tool, "ok": False, "error": str(e)})
        return {"ok": True, "results": results}
