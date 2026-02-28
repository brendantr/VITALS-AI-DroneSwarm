from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Union

from jsonschema import ValidationError
try:
    from app.Agent.schema_validator import SchemaValidator
except ImportError:
    from schema_validator import SchemaValidator


def load_json_any(path: Path) -> Union[Dict[str, Any], List[Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_file(path: Path, v: SchemaValidator) -> int:
    data = load_json_any(path)

    msgs = data if isinstance(data, list) else [data]
    failures = 0

    for i, msg in enumerate(msgs):
        if not isinstance(msg, dict):
            print(f"[FAIL] {path} item[{i}] is not an object")
            failures += 1
            continue

        try:
            v.validate(msg)
            print(f"[OK]   {path} item[{i}] {msg.get('schema')} {msg.get('type')} event_id={msg.get('event_id')}")
        except (ValidationError, ValueError) as e:
            failures += 1
            print(f"[FAIL] {path} item[{i}] reason: {e}")
            # Print a bit more detail for schema errors
            if isinstance(e, ValidationError):
                print(f"       at: {'/'.join(str(x) for x in e.path)}")
                print(f"  schema at: {'/'.join(str(x) for x in e.schema_path)}")

    return failures


def main():
    ap = argparse.ArgumentParser(description="Validate MCP/ACP messages against local JSON Schemas.")
    ap.add_argument("file", type=str, help="Path to a JSON file (single object or list of objects).")
    ap.add_argument("--schemas", type=str, default="schemas", help="Schema root directory (default: ./schemas)")
    args = ap.parse_args()

    v = SchemaValidator(schema_root=args.schemas)
    failures = validate_file(Path(args.file), v)

    if failures:
        print(f"\nValidation failed: {failures} error(s)")
        raise SystemExit(1)

    print("\nValidation succeeded.")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
