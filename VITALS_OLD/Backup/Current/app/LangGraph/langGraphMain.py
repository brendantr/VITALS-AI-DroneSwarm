#THIS DOES NOT CURRENTLY WORK, IT IS A WORK IN PROGRESS



from langgraph.graph import StateGraph
from typing import TypedDict, Annotated, List, Union
from langchain_core.agents import AgentAction, AgentFinish
import operator
from langchain_core.tools import tool


class AgentState(TypedDict):
    input: str
    agent_out: Union[AgentAction, AgentFinish, None]
    intermediate_steps: Annotated[list[tuple[AgentAction, str]], operator.add]

#TOOLS#
@tool("find_available_drone")
def find_available_drone():
    """Searches drone list for available drones, returns first available drone or None"""
    return None
@tool("get_poi_loaction")
def get_poi_location(poi_name: str):
    """Returns the location of a point of interest"""

    return None
@tool("command_drone")
def command_drone(drone_id: str, gps_location: tuple[float, float], command: str):
    """Sends a command to a drone to move to a location or perform an action"""
    return None
@tool("terminate_search")
def terminate_search():
    """Terminates the search sending a command to all drones to return to base"""
    return None
@tool("object_identification")
def object_identification(image: str):
    """Identifies an object in an image using a machine learning model"""
    return None
@tool("rate_object_priority")
def rate_object_priority(object_name: str, geographic_context: str):
    """Rates the priority of an object to be searched utelizing an AI model"""
    return None
@tool("calcualte_gps_coordinates")
def calcualte_gps_coordinates(
    object_pixel_location: tuple[int, int],
    image: str,
     drone_gps_location: tuple[float, float],
     drone_altitude: float,
     drone_fov: float,
     drone_heading: float,
     drone_pitch: float):
    """Converts a location name to GPS coordinates"""
    return None
@tool("send_poi_to_backend")
def send_poi_to_backend(poi_name: str,
                        poi_desc:str,
                        search_priority:float,
                        poi_location: tuple[float, float]):
    """Sends a point of interest to the backend for storage"""
    return None

#Graph Construction
graph = StateGraph()

#State Definitions


