#!/usr/bin/env python3
"""
Clear Agent B datastores (/app/agent_b).

This script wipes:
- Parquet events lake directory
- Chroma persistent directory
- ingest_dedupe.db (SQLite)

It resolves paths using:
1) Environment variables (if set): VITALS_PARQUET_DIR, VITALS_CHROMA_PATH, VITALS_INGEST_DEDUPE_DB
2) Otherwise defaults under the detected project /app root:
   - app/agent_b/data/lake/events
   - app/agent_b/chroma_data
   - app/agent_b/data/lake/ingest_dedupe.db

Usage:
  python clear_agent_b_datastores.py
  python clear_agent_b_datastores.py --yes
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def find_app_root(start: Path) -> Path:
    """
    Walk upward until we find a directory literally named 'app'.
    This avoids clearing the wrong tree (e.g. app/agents_tools/agent_b/...).
    """
    p = start.resolve()
    for _ in range(25):
        if p.name == "app":
            return p
        if p.parent == p:
            break
        p = p.parent
    raise RuntimeError(f"Could not locate 'app' root starting from: {start}")


def rm_tree(path: Path) -> bool:
    if path.exists():
        shutil.rmtree(path)
        return True
    return False


def rm_file(path: Path) -> bool:
    if path.exists():
        path.unlink()
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Wipe Agent B datastores (parquet lake, chroma, dedupe DB).")
    ap.add_argument("--yes", action="store_true", help="Do not prompt for confirmation.")
    args = ap.parse_args()

    # Detect real /app root
    app_root = find_app_root(Path(__file__))
    # Default Agent B base under real /app
    agent_b_dir = app_root / "agent_b"

    # Resolve targets (env overrides supported)
    parquet_events_dir = Path(os.getenv("VITALS_PARQUET_DIR", str(agent_b_dir / "data" / "lake" / "events")))
    chroma_dir = Path(os.getenv("VITALS_CHROMA_PATH", str(agent_b_dir / "chroma_data")))
    dedupe_db = Path(os.getenv("VITALS_INGEST_DEDUPE_DB", str(agent_b_dir / "data" / "lake" / "ingest_dedupe.db")))

    print("== Agent B datastore wipe ==")
    print(f"App root detected: {app_root}")
    print(f"Agent B dir:       {agent_b_dir}")
    print(f"- Parquet events:  {parquet_events_dir} {'(missing)' if not parquet_events_dir.exists() else ''}")
    print(f"- Chroma dir:      {chroma_dir} {'(missing)' if not chroma_dir.exists() else ''}")
    print(f"- Dedupe DB:       {dedupe_db} {'(missing)' if not dedupe_db.exists() else ''}")
    print()

    if not args.yes:
        confirm = input("Type 'DELETE' to confirm: ").strip()
        if confirm != "DELETE":
            print("Aborted.")
            return 1

    # Wipe targets
    ok1 = rm_tree(parquet_events_dir)
    print(f"[OK] Cleared: Parquet events dir" if ok1 else "[OK] Parquet events dir already missing")

    ok2 = rm_tree(chroma_dir)
    print(f"[OK] Cleared: Chroma persistent dir" if ok2 else "[OK] Chroma dir already missing")

    ok3 = rm_file(dedupe_db)
    print(f"[OK] Cleared: Ingest dedupe sqlite db" if ok3 else "[OK] Dedupe DB already missing")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
