"""Interactive-first launcher for Agent D pathing demos."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .pathing_visualization_demo import run_demo, run_interactive_demo
except ImportError:  # Script execution fallback.
    from pathing_visualization_demo import run_demo, run_interactive_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch Agent D pathing demos.")
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Run the legacy batch exporter that saves PNG files.",
    )
    args = parser.parse_args()

    if not args.batch:
        run_interactive_demo()
        return

    demo_counts = [1, 10, 100, 1000, 10000]
    output_dir = Path(__file__).resolve().parent / "demo_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    for png_file in output_dir.glob("demo_*.png"):
        png_file.unlink(missing_ok=True)

    for drones in demo_counts:
        save_prefix = str(output_dir / f"demo_{drones}.png")
        run_demo(
            drone_count=drones,
            save_prefix=save_prefix,
            show_plots=False,
            auto_scale=True,
        )


if __name__ == "__main__":
    main()
