# agents_common/schema_validator.py
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple, Set, List

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


_SCHEMA_RE = re.compile(r"^(?P<name>.+)\.v(?P<ver>\d+\.\d+)$")


class SchemaValidator:
    """
    Validates messages against JSON Schemas stored under a schema_root directory.

    Supports the *new* directory layout:
      schemas/
        acp/v0.2/{base.json,message.json,types/...}
        mcp/v0.2/{...}
        agentb.api/v0.1/{query_request.json,query_response.json}

    Transport-agnostic reference resolution:
    - Walks schema_root and registers every *.json into a `referencing.Registry`,
      keyed by:
        1) the schema's $id (when present), and
        2) the file URI (always),
      so $ref can be resolved reliably even if a file is missing $id.

    Version policy (current):
    - ACP: supports acp.v0.2 ONLY
    - MCP: supports mcp.v0.1 ONLY
    - AgentB API: supports agentb.api.v0.1 ONLY (QueryRequest/QueryResponse)

    Optional improvements enabled:
    - Fail fast on unreadable / bad JSON schema files (instead of silently skipping).
    - Enforce that entrypoint schema files have a stable $id (message.json, query_request/response.json).
    - Uses typing.Dict / typing.Tuple for broader Python compatibility with type checkers (and older runtimes).
    """

    SUPPORTED: Dict[str, Set[str]] = {
        "acp": {"acp.v0.2"},
        "mcp": {"mcp.v0.2"},
        "agentb.api": {"agentb.api.v0.1"},
    }

    def __init__(self, schema_root: str | Path = "schemas"):
        self.schema_root = Path(schema_root)
        if not self.schema_root.exists():
            raise FileNotFoundError(f"Schema root not found: {self.schema_root.resolve()}")

        # Build registry for resolving $ref (fail-fast on bad schema JSON)
        self.registry = self._load_registry(self.schema_root)

        # Enforce stable $id on entrypoint schemas (fail-fast if missing)
        self._assert_entrypoint_ids()

        # Cache compiled validators by schema file path
        self._validator_cache: Dict[Path, Draft202012Validator] = {}

    # -------------------------
    # Public API
    # -------------------------
    def validate(self, msg: Dict[str, Any]) -> None:
        """
        Validates a single message. Raises jsonschema.ValidationError or ValueError.
        """
        schema_file = self._schema_file_for(msg)
        validator = self._get_validator(schema_file)
        validator.validate(msg)

    def iter_errors(self, msg: Dict[str, Any]) -> Iterator[Any]:
        """
        Returns an iterator of validation errors (doesn't raise).
        """
        try:
            schema_file = self._schema_file_for(msg)
            validator = self._get_validator(schema_file)
            return validator.iter_errors(msg)
        except Exception as e:
            return iter([e])

    # -------------------------
    # Internals: schema selection
    # -------------------------
    def _schema_file_for(self, msg: Dict[str, Any]) -> Path:
        schema = msg.get("schema")
        if not isinstance(schema, str) or not schema.strip():
            raise ValueError("Unsupported or missing 'schema' field")
        schema = schema.strip()  # normalize whitespace

        name, ver_dir = self._parse_schema(schema)

        # Enforce version policy
        allowed = self.SUPPORTED.get(name)
        if not allowed:
            raise ValueError(f"Unsupported schema name: {name!r} (from {schema!r})")
        if schema not in allowed:
            raise ValueError(f"Unsupported schema version: {schema!r}. Allowed: {sorted(allowed)}")

        base_dir = self.schema_root / name / ver_dir

        if name in ("acp", "mcp"):
            schema_file = base_dir / "message.json"
            if not schema_file.exists():
                raise FileNotFoundError(f"Schema file not found: {schema_file}")
            return schema_file

        if name == "agentb.api":
            msg_type = msg.get("type")
            if msg_type == "AgentB.QueryRequest":
                schema_file = base_dir / "query_request.json"
            elif msg_type == "AgentB.QueryResponse":
                schema_file = base_dir / "query_response.json"
            else:
                raise ValueError(f"Unknown agentb.api.v0.1 message type: {msg_type!r}")

            if not schema_file.exists():
                raise FileNotFoundError(f"Schema file not found: {schema_file}")
            return schema_file

        raise ValueError(f"Unsupported schema: {schema!r}")

    @staticmethod
    def _parse_schema(schema: str) -> Tuple[str, str]:
        """
        Parse 'acp.v0.2' -> ('acp', 'v0.2')
              'agentb.api.v0.1' -> ('agentb.api', 'v0.1')
        """
        m = _SCHEMA_RE.match(schema)
        if not m:
            raise ValueError(f"Unsupported schema format: {schema!r}")

        name = m.group("name")
        ver = m.group("ver")  # e.g. "0.2"
        return name, f"v{ver}"

    # -------------------------
    # Internals: validators
    # -------------------------
    def _get_validator(self, schema_file: Path) -> Draft202012Validator:
        schema_file = schema_file.resolve()
        v = self._validator_cache.get(schema_file)
        if v is not None:
            return v

        schema_obj = self._load_json(schema_file)
        v = Draft202012Validator(schema_obj, registry=self.registry)
        self._validator_cache[schema_file] = v
        return v

    @staticmethod
    def _load_json(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    # -------------------------
    # Internals: registry + entrypoint checks
    # -------------------------
    def _entrypoint_schema_files(self) -> List[Path]:
        """
        Return the schema entrypoints that should always have stable $id fields.
        """
        files: List[Path] = []

        # acp + mcp message entrypoints
        for name, allowed in self.SUPPORTED.items():
            for schema in allowed:
                n, ver_dir = self._parse_schema(schema)
                base_dir = self.schema_root / n / ver_dir

                if n in ("acp", "mcp"):
                    files.append(base_dir / "message.json")
                elif n == "agentb.api":
                    files.append(base_dir / "query_request.json")
                    files.append(base_dir / "query_response.json")

        # Deduplicate while preserving order
        seen: Set[Path] = set()
        out: List[Path] = []
        for p in files:
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                out.append(rp)
        return out

    def _assert_entrypoint_ids(self) -> None:
        """
        Fail fast if entrypoint schema files are missing or missing $id.
        Having stable $id on entrypoints makes $ref resolution and tooling more reliable.
        """
        for p in self._entrypoint_schema_files():
            if not p.exists():
                raise FileNotFoundError(f"Entrypoint schema file not found: {p}")

            obj = self._load_json(p)
            schema_id = obj.get("$id")
            if not isinstance(schema_id, str) or not schema_id.strip():
                raise ValueError(f"Entrypoint schema missing required $id: {p}")

    @staticmethod
    def _load_registry(schema_root: Path) -> Registry:
        """
        Walk schema_root, load every *.json file, and register resources for $ref resolution.

        Registers:
          - By $id (when present)
          - By file URI (always) as a fallback

        Optional improvement enabled:
          - Fail fast on unreadable/bad JSON schema files.
        """
        reg = Registry()
        for p in schema_root.rglob("*.json"):
            try:
                with p.open("r", encoding="utf-8") as f:
                    contents = json.load(f)
            except Exception as e:
                raise ValueError(f"Failed to read/parse schema JSON: {p} ({e})") from e

            resource = Resource.from_contents(contents)

            schema_id = contents.get("$id")
            if isinstance(schema_id, str) and schema_id.strip():
                reg = reg.with_resource(schema_id.strip(), resource)

            # Always register file URI as a fallback resolver key
            reg = reg.with_resource(p.resolve().as_uri(), resource)

        return reg
