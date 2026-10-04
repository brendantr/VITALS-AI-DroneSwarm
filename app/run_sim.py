import os

os.environ["VITALS_SIM_ONLY"] = "1"

from GUI.GUI import GUI
from missionState import missionState

if __name__ == "__main__":
    gui = GUI()
    state = missionState(gui, sim_only=True, mavlink_endpoint="tcp:127.0.0.1:14550")
    gui.link_mission_state(state)

    try:
        gui.run()
    finally:
        state._detection_poll_stop.set()
