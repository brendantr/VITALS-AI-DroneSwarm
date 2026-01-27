
# VITALS Drone Software

This is a python project aimed at creating automation software for the SOAR senior design 
 drones. 

## Installation

Install necessary dependencys

```bash
  $ cd app
  $ pip install -r requirements.txt
```

## Ollama 
Open Windows command prompt
ollama pull llama3.2
ollama pull llava

##  Configure Mission Planner
    
This software runs from mirrored mavlink packets through mission planner.

Mission Planner install link found [here](https://ardupilot.org/planner/docs/mission-planner-installation.html) 

In mission planner navigate to Setup->Advanced->Mavlink Mirror -> Select "TCP Host  - 14550" -> Check "Write Access" -> hit "Connect"

## Launch Application

from the `app` directory run:

```bash
  $ python missionState.py
```