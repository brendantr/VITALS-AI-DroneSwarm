# VITALS — C4 Level 2: Container Diagram

> **Audience:** Developers, DevOps, technical leads, Lockheed Martin engineering sponsors.
> **Purpose:** Shows the major deployable units (Docker containers) inside VITALS, their technologies, and how they communicate.
> **C4 Rule:** Every container must show: Name, [Technology], and a short description. Label every relationship with protocol/format.

```mermaid
C4Container
    title Container Diagram - VITALS Drone Swarm AI (SAR)

    Person(operator, "SAR Operator", "Plans and monitors drone search-and-rescue missions")

    System_Ext(missionPlanner, "Mission Planner", "GCS: ArduPilot MAVLink router and telemetry hub")
    System_Ext(droneHW, "Drone Swarm Hardware", "Physical UAVs running ArduPilot firmware")
    System_Ext(ollama, "Ollama", "Local LLM server - LLaMA 3.2 and LLaVA")
    System_Ext(postGIS, "PostGIS", "Offline geospatial map database")

    System_Boundary(vitals, "VITALS System") {

        Container(gui, "GUI", "Python, CustomTkinter", "Operator-facing interface. Displays map, drone telemetry, job queues, and detections")

        Container(missionState, "MissionState", "Python 3.11", "Central orchestrator. Manages drone state, routes commands, and coordinates all containers")

        Container(dispatcher, "Dispatcher", "Python, pymavlink", "MAVLink communication layer. Connects to Mission Planner via TCP, uploads waypoints, processes telemetry")

        Container(agentA, "Agent A - Vision and Perception", "Python, YOLOv11, OpenCV", "Processes raw drone video. Runs object detection via YOLO and scene captioning via LLaVA. Emits MCP detection events")

        Container(agentB, "Agent B - Data and Knowledge", "Python, ChromaDB, Parquet", "Centralized semantic memory. Ingests MCP events, validates schema, stores in vector DB and structured archive. Handles RAG retrieval queries")

        Container(agentC, "Agent C - Coordinator and Reasoner", "Python, LangGraph, LLaMA 3.2", "Cognitive hub of VITALS. Synthesizes mission context from Agent B RAG, interprets operator directives, generates ACP mission intents for Agent D")

        Container(agentD, "Agent D - Mapping and Planning", "Python, OSMnx, A-Star", "Converts ACP mission intents into executable waypoints. Builds terrain cost maps from OSM polygons, runs A* search, outputs MAVLink-ready paths")

        ContainerDb(chromaDB, "ChromaDB", "ChromaDB Docker volume", "Vector database for semantic embeddings of mission events and detection context")

        ContainerDb(parquet, "Parquet Archive", "Apache Parquet filesystem", "Structured append-only log of all mission events, detections, and actions")
    }

    Rel(operator, gui, "Views mission map, issues directives, monitors drones", "GUI Interaction")
    Rel(gui, missionState, "Calls orchestration methods for mission control", "Python method calls")

    Rel(missionState, dispatcher, "Sends waypoint commands and drone control instructions", "Python async")
    Rel(missionState, agentA, "Triggers frame capture and detection pipeline", "Python method calls")
    Rel(missionState, agentC, "Passes operator directives for LLM reasoning", "Python / ACP JSON")
    Rel(missionState, agentD, "Requests path generation for search grid", "Python / ACP JSON")

    Rel(agentA, agentB, "Publishes detection events and scene descriptions", "MCP JSON Schema over Docker network")
    Rel(agentB, agentC, "Returns ranked mission context - RAG results", "MCP JSON Schema over Docker network")
    Rel(agentC, agentD, "Sends structured mission intents for path generation", "ACP JSON Schema over Docker network")
    Rel(agentC, agentB, "Stores reasoning logs and event records", "MCP JSON Schema over Docker network")
    Rel(agentD, agentB, "Records actions taken and terrain updates", "MCP JSON Schema over Docker network")
    Rel(agentD, agentC, "Returns drone paths and processed map tile results", "ACP JSON Schema over Docker network")

    Rel(agentB, chromaDB, "Reads and writes semantic vector embeddings", "ChromaDB Python SDK")
    Rel(agentB, parquet, "Appends structured mission event records", "PyArrow / Parquet")

    Rel(dispatcher, missionPlanner, "Mirrors MAVLink packets, uploads waypoint missions, reads telemetry", "TCP MAVLink port 14550")
    Rel(missionPlanner, droneHW, "Relays commands and receives telemetry", "MAVLink / RF / USB")
    Rel(agentC, ollama, "Sends prompts, receives LLM-generated reasoning", "HTTP REST JSON")
    Rel(agentA, ollama, "Sends drone image frames, receives scene captions", "HTTP REST JSON")
    Rel(agentD, postGIS, "Queries terrain polygons via SQL for cost maps", "SQL / PostGIS Docker")

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
