# VITALS — C4 Level 2: Container Diagram

> **Audience:** Developers, DevOps, technical leads, Lockheed Martin engineering sponsors.
> **Purpose:** Shows the major deployable units (Docker containers) inside VITALS, their technologies, and how they communicate.
> **C4 Rule:** Every container must show: Name, [Technology], and a short description. Label every relationship with protocol/format.

```mermaid
C4Container
    title Container Diagram — VITALS Drone Swarm AI (SAR)

    Person(operator, "SAR Operator", "Plans and monitors drone\nsearch-and-rescue missions")

    System_Ext(missionPlanner, "Mission Planner", "GCS: ArduPilot MAVLink\nrouter and telemetry hub")
    System_Ext(ollama, "Ollama", "Local LLM server\n(LLaMA 3.2 + LLaVA)")
    System_Ext(postGIS, "PostGIS", "Offline geospatial\nmap database")
    System_Ext(droneHW, "Drone Swarm Hardware", "Physical UAVs running\nArduPilot firmware")

    System_Boundary(vitals, "VITALS System") {

        Container(gui, "GUI", "Python, CustomTkinter\n+ tkintermapview", "Operator-facing interface.\nDisplays map, drone telemetry,\njob queues, and detections")

        Container(missionState, "MissionState", "Python 3.11",
            "Central orchestrator.\nManages drone state, routes\ncommands, and coordinates\nall containers")

        Container(agentA, "Agent A — Vision & Perception", "Python, YOLOv11\n+ LLaVA, OpenCV",
            "Processes raw drone video.\nRuns object detection (YOLO)\nand scene captioning (LLaVA).\nEmits MCP detection events")

        Container(agentB, "Agent B — Data & Knowledge", "Python, ChromaDB\n+ Parquet",
            "Centralized semantic memory.\nIngests MCP events, validates\nschema, stores in vector DB\nand structured archive.\nHandles RAG retrieval queries")

        Container(agentC, "Agent C — Coordinator & Reasoner", "Python, LangGraph\n+ LLaMA 3.2 via Ollama",
            "Cognitive hub of VITALS.\nSynthesizes mission context\nfrom Agent B RAG, interprets\noperator directives, generates\nACP mission intents for Agent D")

        Container(agentD, "Agent D — Mapping & Planning", "Python, OSMnx\n+ A* Pathfinding",
            "Converts ACP mission intents\ninto executable waypoints.\nBuilds terrain cost maps from\nOSM polygons, runs A* search,\noutp MAVLink-ready paths")

        Container(dispatcher, "Dispatcher", "Python, pymavlink",
            "MAVLink communication layer.\nConnects to Mission Planner\nvia TCP, uploads waypoints,\nprocesses telemetry messages\nfrom drone fleet")

        ContainerDb(chromaDB, "ChromaDB", "ChromaDB\n(Docker volume)",
            "Vector database for semantic\nembeddings of mission events\nand detection context")

        ContainerDb(parquet, "Parquet Archive", "Apache Parquet\n(local filesystem)",
            "Structured append-only log\nof all mission events,\ndetections, and actions")
    }

    %% Operator flows
    Rel(operator, gui, "Views mission map, issues\ndirectives, monitors drones", "GUI Interaction")
    Rel(gui, missionState, "Calls orchestration methods\nfor mission control", "Python method calls")

    %% MissionState orchestration
    Rel(missionState, dispatcher, "Sends waypoint commands\nand drone control instructions", "Python / async")
    Rel(missionState, agentA, "Triggers frame capture\nand detection pipeline", "Python method calls")
    Rel(missionState, agentC, "Passes operator directives\nfor LLM reasoning", "Python / ACP JSON")
    Rel(missionState, agentD, "Requests path generation\nfor search grid", "Python / ACP JSON")

    %% Agent data flows
    Rel(agentA, agentB, "Publishes detection events\nand scene descriptions", "MCP (JSON Schema 2020-12)\nover Docker network")
    Rel(agentB, agentC, "Returns ranked mission\ncontext (RAG results)", "MCP (JSON Schema 2020-12)\nover Docker network")
    Rel(agentC, agentD, "Sends structured mission\nintents for path generation", "ACP (JSON Schema 2020-12)\nover Docker network")
    Rel(agentC, agentB, "Stores reasoning logs\nand event records", "MCP (JSON Schema 2020-12)\nover Docker network")
    Rel(agentD, agentB, "Records actions taken\nand terrain updates", "MCP (JSON Schema 2020-12)\nover Docker network")
    Rel(agentD, agentC, "Returns drone paths and\nprocessed map tile results", "ACP (JSON Schema 2020-12)\nover Docker network")

    %% Storage
    Rel(agentB, chromaDB, "Reads/writes semantic\nvector embeddings", "ChromaDB Python SDK")
    Rel(agentB, parquet, "Appends structured\nmission event records", "PyArrow / Parquet")

    %% External connections
    Rel(dispatcher, missionPlanner, "Mirrors MAVLink packets,\nuploads waypoint missions,\nreads telemetry", "TCP MAVLink port 14550")
    Rel(missionPlanner, droneHW, "Relays commands and\nreceives telemetry", "MAVLink / RF / USB")
    Rel(agentC, ollama, "Sends prompts, receives\nLLM-generated reasoning", "HTTP REST (JSON)")
    Rel(agentA, ollama, "Sends drone image frames,\nreceives scene captions", "HTTP REST (JSON)")
    Rel(agentD, postGIS, "Queries terrain polygons\nvia SQL for cost maps", "SQL / PostGIS Docker")

    UpdateLayoutConfig($c4ShapeInRow="4", $c4BoundaryInRow="1")
```

## Container Inventory

| Container | Technology | Responsibility | Agent Role |
|---|---|---|---|
| GUI | Python, CustomTkinter | Operator interface: map, telemetry, jobs | — |
| MissionState | Python 3.11 | Central orchestrator, state machine | — |
| Agent A — Vision & Perception | YOLOv11, LLaVA, OpenCV | Object detection + scene captioning from drone video | A |
| Agent B — Data & Knowledge | ChromaDB, Parquet | Semantic memory, event storage, RAG retrieval | B |
| Agent C — Coordinator & Reasoner | LangGraph, LLaMA 3.2 | Mission reasoning, intent generation | C |
| Agent D — Mapping & Planning | OSMnx, A* | Terrain cost maps, waypoint generation | D |
| Dispatcher | pymavlink | MAVLink protocol bridge to Mission Planner | — |
| ChromaDB | ChromaDB | Vector database (persistent Docker volume) | B (storage) |
| Parquet Archive | Apache Parquet | Structured event log archive | B (storage) |

## Protocol Glossary

| Protocol | Full Name | Usage |
|---|---|---|
| MCP | Message Communication Protocol | Standardized JSON Schema events: facts, detections, queries, logs |
| ACP | Agent Communication Protocol | Action-oriented JSON Schema intents: planning requests, mission coordination |
| MAVLink | Micro Air Vehicle Link | Drone waypoint upload, telemetry reception |
