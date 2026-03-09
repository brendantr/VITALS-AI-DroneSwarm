"""Agent D ACP dispatcher for inbound messages from Agents A/B/C."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from acp_A import MESSAGE_TYPE as A_MESSAGE_TYPE
from acp_A import parse_obstacle_feed
from acp_B import MESSAGE_TYPE as B_MESSAGE_TYPE
from acp_B import parse_retrieval_context
from acp_C import MESSAGE_TYPE as C_MESSAGE_TYPE
from acp_C import parse_coordinator_intents


def parse_agent_d_message(raw: dict[str, Any]) -> Any:
    """Parse inbound ACP payload for Agent D using source/message_type routing."""
    envelope = raw.get("envelope") or {}
    source_agent = envelope.get("source_agent")
    message_type = envelope.get("message_type")

    if source_agent == "A" and message_type == A_MESSAGE_TYPE:
        return parse_obstacle_feed(raw)
    if source_agent == "B" and message_type == B_MESSAGE_TYPE:
        return parse_retrieval_context(raw)
    if source_agent == "C" and message_type == C_MESSAGE_TYPE:
        return parse_coordinator_intents(raw)

    raise ValueError(
        f"Unsupported Agent D ACP route: source_agent={source_agent!r}, message_type={message_type!r}"
    )
