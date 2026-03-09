from mcp.server import Server
from mcp.server.stdio import stdio_server

from tools.detect import detect_objects
import json

server = Server(name="mcp_server")

@server.tool(
    name="detect_objSects",
    description="Detect objects in an image",
)
def detect_tool(image_path: str):
    return detect_objects(image_path)

if __name__ == "__main__":
    stdio_server(server)