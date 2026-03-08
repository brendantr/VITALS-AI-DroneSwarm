import requests
import json
import ollama
import base64




def call_llm(prompt, mission_area, drones, pois):

    def create_poi_investigate_job(poi_id: int, drone_id: int, priority: int = 5):
        """
        Navigate a drone to a specific Point of Interest (POI) to investigate it.
        Use this when the user wants to SEND a drone TO a POI, FLY to a POI, GO to a POI, or INVESTIGATE a POI.

        Args:
            poi_id: The numeric ID of the POI to investigate (e.g. 1, 2, 3)
            drone_id: The numeric ID of the drone to send (e.g. 1, 2, 3)
            priority: Job priority, 5 is default, higher numbers mean higher priority
        """
        pass

    def call_return_to_launch(drone_id: int):
        """
        Command a drone to return to its home/launch position (RTL).
        Use this when the user says "RTL", "return to launch", "bring home", "recall", or "send back".
        Do NOT use this when the user wants to send a drone to a POI.
        Do NOT confuse this with call_start_mission. RTL means GO HOME, not start.

        Args:
            drone_id: The numeric ID of the drone to recall (e.g. 1, 2, 3)
        """
        pass

    def call_end_mission():
        """
        STOP and END the entire mission. Recall ALL drones back to their launch positions.
        Use this when the user says "end mission", "stop mission", "abort mission", or "cancel mission".
        Do NOT confuse this with start mission. END means STOP everything.
        """
        pass

    def call_start_mission():
        """
        Start the search mission for the FIRST TIME ONLY when drones have not yet been deployed.
        Use this ONLY when the user says "start mission" or "begin mission" and no mission is currently running.
        Do NOT use this if the user says "end", "stop", or "abort".
        """
        pass

    def resume_drone_mission(drone_id: int):
        """
        Resume a specific drone's mission after it was paused or recalled via RTL.
        Use this when the user wants to RESUME, CONTINUE, or RESTART a drone's mission.

        Args:
            drone_id: The numeric ID of the drone to resume (e.g. 1, 2, 3)
        """
        pass

    system_prompt = f"""You are a drone mission command interpreter. Your job is to pick the correct tool based on what the user wants.

CRITICAL RULES — read carefully:
- "end mission" or "stop mission" or "abort" = call_end_mission(). This STOPS everything.
- "start mission" or "begin mission" (first time only) = call_start_mission(). This STARTS the search.
- "resume mission for drone X" = resume_drone_mission(drone_id=X).
- "send drone X to POI Y" = create_poi_investigate_job(poi_id=Y, drone_id=X).
- "bring drone X home" or "RTL drone X" = call_return_to_launch(drone_id=X).

The words END, STOP, ABORT, CANCEL always mean call_end_mission.
The word START only means call_start_mission.
The words RTL, HOME, RETURN, RECALL, BACK always mean call_return_to_launch.
Never confuse END with START. They are OPPOSITES.
Never confuse RTL with START. RTL means RETURN HOME, not start mission.

Available drones: {drones}
Available POIs: {pois}
Mission area: {mission_area}

Respond with a short confirmation of what action you are taking."""


    response = ollama.chat(
        model="llama3.2",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        tools=[create_poi_investigate_job, call_return_to_launch, call_end_mission, call_start_mission, resume_drone_mission]
    )
    return response.message


def give_image_description(image_path):
    system_prompt = f"""
    You are part of a drone flight operator system. You are tasked with describing images taken by drones.
    to create a useful description of what is located at the point of interest. Descriptions should be no longer than a couple of sentences.
    And only describe simple details which would be useful in a searh and rescue operation.

    
    """
    print(f"image-Path:{image_path}")
    # with open(image_path, "rb") as image_file:
    #     encoded_string = base64.b64encode(image_file.read())
    response = ollama.chat(
        model="llava",
        messages=[{
            "role": "user",
            "content": system_prompt,
            'images': [image_path]

        }],
        
    )
    return response.message
    