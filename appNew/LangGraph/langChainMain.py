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
        Use this ONLY when the user wants to bring a drone HOME, BACK TO BASE, or RETURN TO LAUNCH.
        Do NOT use this when the user wants to send a drone to a POI.

        Args:
            drone_id: The numeric ID of the drone to recall (e.g. 1, 2, 3)
        """
        pass

    def call_end_mission():
        """
        End the entire mission and recall ALL drones back to their launch positions.
        Use this ONLY when the user wants to END or STOP the entire mission for all drones.
        """
        pass

    def call_start_mission():
        """
        Start the search mission. This deploys all drones to begin searching the mission area.
        Use this when the user wants to START, BEGIN, or LAUNCH the mission.
        """
        pass

    system_prompt = f"""You are a drone mission command interpreter. Your job is to pick the correct tool based on what the user wants.

IMPORTANT RULES:
- If the user wants to START or BEGIN the mission, use call_start_mission.
- If the user wants to send/fly a drone TO A POI, use create_poi_investigate_job.
- If the user wants to send a drone HOME or back to LAUNCH, use call_return_to_launch.
- If the user wants to END the entire MISSION, use call_end_mission.
- "Start mission" means call_start_mission().
- "Send drone X to POI Y" means create_poi_investigate_job(poi_id=Y, drone_id=X).
- "Bring drone X home" means call_return_to_launch(drone_id=X).

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
        tools=[create_poi_investigate_job, call_return_to_launch, call_end_mission, call_start_mission]
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
    