from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

# Mission boundaries and drone data
MISSION_BOUNDARIES = {"x_min": 0, "x_max": 100, "y_min": 0, "y_max": 100}

# Define a function to validate coordinates
def validate_coordinates(coords: List[Dict[str, float]]) -> bool:
    for coord in coords:
        if not (MISSION_BOUNDARIES["x_min"] <= coord["x"] <= MISSION_BOUNDARIES["x_max"] and
                MISSION_BOUNDARIES["y_min"] <= coord["y"] <= MISSION_BOUNDARIES["y_max"]):
            return False
    return True

# Define drone status (mock data for now)
drones = [
    {"id": "drone1", "x": 10, "y": 10, "battery": 80},
    {"id": "drone2", "x": 50, "y": 50, "battery": 60},
]

# Tool for querying drone data
@tool("get_drone_status")
def get_drone_status() -> str:
    """
    Returns the status of all drones including position and battery levels.
    """
    return str(drones)

# Tool for generating movement commands
@tool("generate_path")
def generate_path(start: Dict[str, float], end: Dict[str, float], battery: int) -> str:
    """
    Generates a series of movement commands for a drone.
    Validates the path based on mission boundaries and battery levels.
    """
    path = [
        {"x": start["x"], "y": start["y"]},
        {"x": (start["x"] + end["x"]) / 2, "y": (start["y"] + end["y"]) / 2},
        {"x": end["x"], "y": end["y"]},
    ]
    if validate_coordinates(path):
        return f"Path generated: {path}"
    else:
        return "Error: Path is out of mission boundaries."

# Prompt template for the LLM
prompt_template = """
You are a drone control agent. Your job is to translate user instructions into actionable movement commands.
The mission area is defined by the following boundaries: {boundaries}.
Drones have limited battery life and cannot move outside the mission area.

Here is the current drone status: {drone_status}

User Instruction: {instruction}

Based on this, provide a detailed plan of coordinates for the drone to follow, considering battery levels and mission boundaries.
"""

# Initialize the Ollama LLM
llm = Ollama(model="deepseek-r1:8b")  # Specify the Llama version

# Create the LangChain prompt
prompt = PromptTemplate(
    input_variables=["boundaries", "drone_status", "instruction"],
    template=prompt_template,
)

# Initialize the LangChain LLMChain
llm_chain = LLMChain(llm=llm, prompt=prompt)

# Initialize LangChain agent with tools
tools = [
    Tool(name="Get Drone Status", func=get_drone_status, description="Get the status of drones"),
    Tool(name="Generate Path", func=generate_path, description="Generate a movement path for drones"),
]
agent = initialize_agent(tools, llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=True)

# Example User Instruction
user_instruction = "Survey the northern part of the mission area while conserving battery."

# Run the chain
response = llm_chain.run({
    "boundaries": MISSION_BOUNDARIES,
    "drone_status": get_drone_status(),
    "instruction": user_instruction,
})

print(response)