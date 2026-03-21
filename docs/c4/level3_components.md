# VITALS — C4 Level 3: Component Diagrams

> **Audience:** Developers working inside each agent container.
> **Purpose:** Shows the internal components of each container, their responsibilities, and how they connect.
> **C4 Rule:** Components are not separately deployable — they are logical groupings inside a container (classes, modules, subsystems).

---

## Agent A — Vision & Perception (Component Diagram)

```mermaid
C4Component
    title Component Diagram - Agent A: Vision and Perception

    Container_Ext(droneCamera, "Drone Camera Feed", "OpenCV VideoCapture", "Raw video stream from drone payload")
    Container_Ext(flightController, "Flight Controller", "ArduPilot MAVLink", "Provides GPS, altitude, and heading via MAVLink")
    Container_Ext(ollamaA, "Ollama", "HTTP REST API", "LLaVA model for scene captioning")
    Container_Ext(agentBext, "Agent B - Data and Knowledge", "Docker network HTTP", "Receives MCP detection events")

    Container_Boundary(agentA, "Agent A - Vision and Perception [Container]") {

        Component(frameCapture, "Frame Capture Module", "Python, OpenCV", "Extracts key frames from drone video stream at configured intervals")

        Component(yoloDetector, "YOLO Detector", "Python, YOLOv11 custom SAR model", "Runs bounding-box object detection on key frames. Outputs class, confidence, and bounding-box coordinates")

        Component(llavaClient, "LLaVA Scene Client", "Python, HTTP client", "Sends frames to Ollama LLaVA endpoint with SAR-specific prompt. Receives 2-sentence scene captions")

        Component(telemetryReader, "Telemetry Reader", "Python, pymavlink", "Reads GPS, altitude, and heading from flight controller for geolocation of detections")

        Component(fusionEngine, "Fusion Engine", "Python", "Combines YOLO detections, LLaVA captions, and GPS telemetry into a unified detection record")

        Component(mcpPublisher, "MCP Publisher", "Python, JSON Schema 2020-12", "Serializes fused detection records into MCP packets and publishes to Agent B over Docker network")
    }

    Rel(droneCamera, frameCapture, "Streams raw video frames", "OpenCV VideoCapture")
    Rel(flightController, telemetryReader, "Sends GPS, heading, altitude data", "MAVLink TCP")
    Rel(frameCapture, yoloDetector, "Passes key frames for detection", "In-process numpy array")
    Rel(frameCapture, llavaClient, "Passes key frames for scene captioning", "In-process base64 image")
    Rel(llavaClient, ollamaA, "POST image and SAR prompt, receive scene description", "HTTP REST JSON")
    Rel(yoloDetector, fusionEngine, "Sends bounding boxes, class labels, confidence", "In-process dict")
    Rel(llavaClient, fusionEngine, "Sends scene description text string", "In-process str")
    Rel(telemetryReader, fusionEngine, "Provides GPS and orientation context", "In-process dict")
    Rel(fusionEngine, mcpPublisher, "Sends complete detection record for publication", "In-process dict")
    Rel(mcpPublisher, agentBext, "Publishes MCP detection event packet", "HTTP Docker network JSON Schema 2020-12")

    UpdateLayoutConfig($c4ShapeInRow="4", $c4BoundaryInRow="1")
```

---

## Agent B — Data & Knowledge (Component Diagram)

```mermaid
C4Component
    title Component Diagram - Agent B: Data and Knowledge Management

    Container_Ext(agentAext, "Agent A - Vision", "Docker network HTTP", "Publishes detection MCP events")
    Container_Ext(agentCext, "Agent C - Coordinator", "Docker network HTTP", "Sends queries, receives RAG context")
    Container_Ext(agentDext, "Agent D - Planning", "Docker network HTTP", "Records planning actions taken")
    Container_Ext(guiOp, "GUI / Operator", "Docker network HTTP", "Sends user queries for memory retrieval")
    Container_Ext(chromaDBext, "ChromaDB", "ChromaDB Python SDK", "Vector database for embeddings")
    Container_Ext(parquetExt, "Parquet Archive", "PyArrow file I/O", "Structured event log storage")

    Container_Boundary(agentB, "Agent B - Data and Knowledge [Container]") {

        Component(schemaValidator, "Schema Validator", "Python, jsonschema", "Validates all incoming MCP packets against JSON Schema 2020-12 specification before processing")

        Component(queryRouter, "Query Router", "Python", "Routes incoming messages: validated events to Memory Engine and Event Logger; queries to Retrieval Engine")

        Component(memoryEngine, "Memory Engine", "Python, sentence-transformers", "Embeds validated events into vector space and writes to ChromaDB for semantic retrieval")

        Component(eventLogger, "Event Logger", "Python, PyArrow", "Appends all validated events to Parquet archive with timestamps and source agent metadata")

        Component(retrievalEngine, "Retrieval Engine", "Python, ChromaDB SDK", "Accepts retrieval queries, performs vector similarity search, returns Top-K ranked mission context")
    }

    Rel(agentAext, schemaValidator, "Sends detection MCP events", "HTTP / Docker network")
    Rel(agentCext, schemaValidator, "Sends reasoning log MCP events", "HTTP / Docker network")
    Rel(agentDext, schemaValidator, "Sends action log MCP events", "HTTP / Docker network")
    Rel(guiOp, schemaValidator, "Sends operator query MCP messages", "HTTP / Docker network")
    Rel(schemaValidator, queryRouter, "Passes validated messages for routing", "In-process")
    Rel(queryRouter, memoryEngine, "Routes events for embedding and storage", "In-process")
    Rel(queryRouter, retrievalEngine, "Routes retrieval queries", "In-process")
    Rel(memoryEngine, chromaDBext, "Writes vector embeddings", "ChromaDB Python SDK")
    Rel(memoryEngine, eventLogger, "Forwards event records for archiving", "In-process")
    Rel(eventLogger, parquetExt, "Appends structured records", "PyArrow write")
    Rel(retrievalEngine, chromaDBext, "Performs vector similarity search Top-K", "ChromaDB Python SDK")
    Rel(retrievalEngine, agentCext, "Returns ranked mission context as MCP response", "HTTP / Docker network")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

---

## Agent C — Coordinator & Reasoner (Component Diagram)

```mermaid
C4Component
    title Component Diagram - Agent C: Coordinator and Reasoner

    Container_Ext(agentAext, "Agent A - Vision", "Docker network HTTP", "Sends real-time detection MCP events")
    Container_Ext(agentBext, "Agent B - Memory", "Docker network HTTP", "Returns RAG context for reasoning")
    Container_Ext(agentDext, "Agent D - Planning", "Docker network HTTP", "Receives ACP mission intents")
    Container_Ext(guiOp, "GUI / Operator", "HTTP / ACP JSON", "Issues mission directives")
    Container_Ext(ollamaC, "Ollama", "HTTP REST API", "LLaMA 3.2 model for LLM inference")

    Container_Boundary(agentC, "Agent C - Coordinator and Reasoner [Container]") {

        Component(directiveIngester, "Directive Ingester", "Python", "Receives and parses operator directives from GUI. Normalises into structured task objects")

        Component(contextFetcher, "Context Fetcher", "Python, HTTP client", "Queries Agent B Retrieval Engine for relevant mission context using semantic search")

        Component(llmClient, "LLM Client", "Python, LangGraph, Ollama HTTP API", "Assembles prompt with operator directive and RAG context. Sends to LLaMA 3.2 via Ollama. Parses response")

        Component(reasoningEngine, "Reasoning Engine", "Python, LangGraph", "Orchestrates multi-step reasoning graph. Routes outputs to ACP intent generator or event emitter")

        Component(acpIntentGenerator, "ACP Intent Generator", "Python, JSON Schema 2020-12", "Converts reasoning output into structured ACP intent messages for Agent D including mission type, priority, and target coordinates")

        Component(eventEmitter, "Event Emitter", "Python", "Serializes reasoning logs as MCP events and sends to Agent B for mission record archiving")
    }

    Rel(guiOp, directiveIngester, "Sends operator mission directives", "ACP JSON / HTTP")
    Rel(agentAext, reasoningEngine, "Sends detection context via MCP events", "HTTP / Docker network")
    Rel(directiveIngester, contextFetcher, "Passes parsed directive for context retrieval", "In-process")
    Rel(contextFetcher, agentBext, "Queries semantic memory for relevant context", "HTTP / Docker network")
    Rel(agentBext, contextFetcher, "Returns Top-K ranked mission context", "HTTP / Docker network")
    Rel(contextFetcher, llmClient, "Passes RAG context and operator directive", "In-process")
    Rel(llmClient, ollamaC, "POST prompt to LLaMA 3.2 endpoint", "HTTP REST JSON")
    Rel(ollamaC, llmClient, "Returns generated reasoning response text", "HTTP REST JSON")
    Rel(llmClient, reasoningEngine, "Passes structured reasoning output", "In-process")
    Rel(reasoningEngine, acpIntentGenerator, "Routes mission planning decisions", "In-process")
    Rel(reasoningEngine, eventEmitter, "Routes reasoning logs for archiving", "In-process")
    Rel(acpIntentGenerator, agentDext, "Sends ACP mission intent with type, priority, location", "HTTP / Docker network")
    Rel(eventEmitter, agentBext, "Publishes reasoning event MCP packet", "HTTP / Docker network")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

---

## Agent D — Mapping & Planning (Component Diagram)

```mermaid
C4Component
    title Component Diagram - Agent D: Mapping and Planning

    Container_Ext(agentCext, "Agent C - Coordinator", "Docker network HTTP", "Sends ACP mission intents and receives completed path results")
    Container_Ext(guiOp, "GUI / Operator", "Docker network HTTP", "Defines map tile search area polygon")
    Container_Ext(postGIS, "PostGIS - OSM Database", "SQL TCP port 5432", "Provides terrain polygon data")
    Container_Ext(agentBext, "Agent B - Memory", "Docker network HTTP", "Receives action log MCP events")

    Container_Boundary(agentD, "Agent D - Mapping and Planning [Container]") {

        Component(acpIngester, "ACP Ingester and Schema Validator", "Python, jsonschema", "Receives ACP intents from Agent C and MCP context from GUI. Validates against JSON Schema 2020-12")

        Component(osmFetcher, "OSM Data Fetcher", "Python, OSMnx, PostGIS", "Queries PostGIS for terrain polygons within the defined search area. Hydrates the terrain cost map data")

        Component(terrainCostMap, "Terrain Cost Map Builder", "Python, NumPy", "Converts OSM polygon data into a weighted grid. Assigns cost values based on terrain type: obstacle, open, or water")

        Component(pathPlanner, "A-Star Path Planner", "Python A-Star algorithm", "Runs A* search on the terrain cost map. Generates optimal waypoint sequences for each drone in the swarm")

        Component(waypointSerializer, "Waypoint Serializer", "Python", "Converts A* waypoint output into MAVLink-compatible GPS coordinate lists for the Dispatcher container")

        Component(acpResponder, "ACP and MCP Responder", "Python, JSON Schema 2020-12", "Packages completed path and map tile as ACP response to Agent C. Packages action log as MCP event to Agent B")
    }

    Rel(agentCext, acpIngester, "Sends ACP mission intent: search type, target, priority", "HTTP / Docker network")
    Rel(guiOp, acpIngester, "Sends user-defined map tile polygon", "HTTP / Docker network")
    Rel(acpIngester, osmFetcher, "Passes validated search area for terrain fetch", "In-process")
    Rel(osmFetcher, postGIS, "SQL query for OSM polygons in search area", "SQL / PostGIS TCP")
    Rel(osmFetcher, terrainCostMap, "Passes raw OSM polygon feature set", "In-process")
    Rel(terrainCostMap, pathPlanner, "Provides weighted grid for A* search", "In-process 2D array")
    Rel(pathPlanner, waypointSerializer, "Passes ordered waypoint coordinate sequence", "In-process")
    Rel(waypointSerializer, acpResponder, "Passes serialized waypoint payload", "In-process")
    Rel(acpResponder, agentCext, "Returns drone paths and processed map tile", "ACP / HTTP Docker network")
    Rel(acpResponder, agentBext, "Sends action log MCP event record", "MCP / HTTP Docker network")

    UpdateLayoutConfig($c4ShapeInRow="4", $c4BoundaryInRow="1")
```
