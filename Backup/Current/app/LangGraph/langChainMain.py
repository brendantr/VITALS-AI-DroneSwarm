import requests
import json
import ollama
import base64




def call_llm(prompt, mission_area, drones, pois):
    
    def create_drone_job(job_name: str, drone_id:str, waypoints: list):
        """
        Creates a job with the given parameters

        Args:
        job_name (str): The name of the job
        drone_id (str): The id of the drone
        waypoints (list): A list of waypoints in the form [(lat, lon), (lat, lon)...]

        Returns:
        Job: A Job object
        """
        return Job(job_name, drone_id, waypoints)

    def create_poi_investigate_job(poi_id, drone_id, priority = 5):
        """
        Calls the drone to investigate a point of interest
        Args:
        poi_id (int): The id of the point of interest
        drone_id (str): The id of the drone
        priority (int): The priority of the job(can be 5,6,7, 5 is default)

        Returns:
        Job: A Job object
        """
        return Job(f"Investigate POI {poi_id}", drone_id, [(poi_id.lat, poi_id.lon)], priority)

    def call_return_to_launch(drone_id):
        """
        Calls the drone to return to launch
        Args:
        drone_id (str): The id of the drone

        Returns:
        Job: A Job object
        """
        return Job(f"Return to Launch", drone_id, [(0, 0)])
    
    def call_end_mission():
        """
        calls all of the drones to return to their launch positions

        Returns:
        Job: A Job object
        """
       
       
        return Job(f"Return to Launch", drone_id, [(0, 0)])

    system_prompt = f"""
    You are a drone flight planner. 
    We have a mission polygon: {mission_area}
    We have these drones: {drones}
    We have these points of interest: {pois}

    The user says: "{prompt}"

    You will use the available tools to coplete the task.
    if you dont have the tool to complete the task, you will say "I dont have the tool to complete this task"
    You absolutely must respond with a short message to the user telling them what you did.
    
    """


    response = ollama.chat(
        model="llama3.2",
        messages=[{
            "role": "user",
            "content": system_prompt
        }],
        tools=[create_poi_investigate_job, call_return_to_launch, call_end_mission]
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
    