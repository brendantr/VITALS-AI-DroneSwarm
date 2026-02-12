"""Legacy Agent D test launcher.

Runs the local pathing visualization demo that does not require missionState.py.
"""

from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parents[2]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from Agent_D.test.pathing_visualization_demo import main


if __name__ == "__main__":
    main()
