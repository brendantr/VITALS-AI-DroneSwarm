from langchain_ollama import ChatOllama
import os

os.environ["LANGCHAIN_TRACING_V2"]="true"
os.environ["LANGCHAIN_ENDPOINT"]="https://api.smith.langchain.com"
os.environ["LANGCHAIN_API_KEY"]="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"
os.environ["LANGCHAIN_PROJECT"]="VITALSToolCalls"

def find_coordinates(image_path):
    """
    This function takes an image path as input and returns the gps coordinates of an object in the image.
    args:
        image_path: str, path to the image
    """
    return [22.5726, 88.3639]
def detect_object(image_path):
    """
    This function takes an image path as input and returns the object detected in the image.
    args:
        image_path: str, path to the image
    """
    return "car"

def find_priority(object_name, context):
    """
    This function takes the object name and context as input and returns the priority of the object.
    args:
        object_name: str, name of the object
        context: str, context of the object
    """
    return 6

llm = ChatOllama(
    model="llama3-groq-tool-use",
    temperature=0.5
).bind_tools([find_coordinates, detect_object, find_priority])

result = llm.invoke("You are an AI agent tasked with identifying objects from drone imagery and calculating distance to the object and priority of the object. You are given an image with the path ./images/drone.jpg. What is the object in the image?", )

print(result.response)