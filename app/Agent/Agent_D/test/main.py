"""Batch runner for Agent D pathing demos at multiple drone scales."""

from __future__ import annotations

from pathlib import Path

from pathing_visualization_demo import run_demo


def main() -> None:
    demo_counts = [1, 10, 100, 1000, 10000]
    output_dir = Path(__file__).resolve().parent / "demo_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    for png_file in output_dir.glob("demo_*.png"):
        png_file.unlink(missing_ok=True)

    for drones in demo_counts:
        save_prefix = str(output_dir / f"demo_{drones}.png")
        show_plots = False
        run_demo(
            drone_count=drones,
            save_prefix=save_prefix,
            show_plots=show_plots,
            auto_scale=True,
        )


if __name__ == "__main__":
    main()
