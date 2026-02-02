from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


class SchemaValidator:
    """
    Loads MCP/ACP schemas from ./schemas and validates messages.
    Also validates AgentB API v0.1 messages (QueryRequest/QueryResponse).
    Requires schemas to include stable $id fields so references can be resolved.
    """

    def __init__(self, schema_root: str | Path = "schemas"):
        self.schema_root = Path(schema_root)
        if not self.schema_root.exists():
            raise FileNotFoundError(f"Schema root not found: {self.schema_root.resolve()}")

        # Build registry for resolving $ref by $id
        self.registry = self._load_registry(self.schema_root)

        # --- Load top-level schemas ---
        self.mcp_message_schema = self._load_json(self.schema_root / "mcp.v0.1" / "message.json")
        self.acp_message_schema = self._load_json(self.schema_root / "acp.v0.1" / "message.json")

        self.agentb_query_req_schema = self._load_json(
            self.schema_root / "agentb.api.v0.1" / "query_request.json"
        )
        self.agentb_query_res_schema = self._load_json(
            self.schema_root / "agentb.api.v0.1" / "query_response.json"
        )

        # --- Compile validators ---
        self._mcp_validator = Draft202012Validator(self.mcp_message_schema, registry=self.registry)
        self._acp_validator = Draft202012Validator(self.acp_message_schema, registry=self.registry)
        self._agentb_query_req_validator = Draft202012Validator(self.agentb_query_req_schema, registry=self.registry)
        self._agentb_query_res_validator = Draft202012Validator(self.agentb_query_res_schema, registry=self.registry)

    @staticmethod
    def _load_json(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _load_registry(schema_root: Path) -> Registry:
        """
        Walk schema_root, load every *.json file, and register by $id.
        """
        reg = Registry()
        for p in schema_root.rglob("*.json"):
            with p.open("r", encoding="utf-8") as f:
                contents = json.load(f)

            schema_id = contents.get("$id")
            if not schema_id:
                # You can enforce $id everywhere if you want strict mode.
                continue

            reg = reg.with_resource(schema_id, Resource.from_contents(contents))
        return reg

    def validate(self, msg: Dict[str, Any]) -> None:
        """
        Validates a single message. Raises jsonschema.ValidationError or ValueError.
        """
        schema = msg.get("schema")

        if schema == "mcp.v0.1":
            self._mcp_validator.validate(msg)
            return

        if schema == "acp.v0.1":
            self._acp_validator.validate(msg)
            return

        if schema == "agentb.api.v0.1":
            msg_type = msg.get("type")
            if msg_type == "AgentB.QueryRequest":
                self._agentb_query_req_validator.validate(msg)
                return
            if msg_type == "AgentB.QueryResponse":
                self._agentb_query_res_validator.validate(msg)
                return
            raise ValueError(f"Unknown agentb.api.v0.1 message type: {msg_type!r}")

        raise ValueError(f"Unsupported or missing 'schema' field: {schema!r}")

    def iter_errors(self, msg: Dict[str, Any]) -> Iterator[Any]:
        """
        Returns an iterator of validation errors (doesn't raise).
        """
        schema = msg.get("schema")

        if schema == "mcp.v0.1":
            return self._mcp_validator.iter_errors(msg)

        if schema == "acp.v0.1":
            return self._acp_validator.iter_errors(msg)

        if schema == "agentb.api.v0.1":
            msg_type = msg.get("type")
            if msg_type == "AgentB.QueryRequest":
                return self._agentb_query_req_validator.iter_errors(msg)
            if msg_type == "AgentB.QueryResponse":
                return self._agentb_query_res_validator.iter_errors(msg)
            # Return one error-like item
            return iter([ValueError(f"Unknown agentb.api.v0.1 message type: {msg_type!r}")])

        return iter([ValueError(f"Unsupported or missing 'schema' field: {schema!r}")])
