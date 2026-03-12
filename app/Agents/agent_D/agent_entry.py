"""Agent D message ingress scaffold.

This module is a lightweight ACP ingress entrypoint for local testing while
Agent D planning integration is being wired.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ACP_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas" / "acpV0.1"
if str(ACP_SCHEMA_DIR) not in sys.path:
    sys.path.insert(0, str(ACP_SCHEMA_DIR))

from dispatcher import parse_agent_d_message


def ingest_acp_message(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and route one ACP message into Agent D."""
    parsed = parse_agent_d_message(raw)
    return {
        "ok": True,
        "parsed_type": type(parsed).__name__,
        "message_id": raw.get("envelope", {}).get("message_id"),
    }
