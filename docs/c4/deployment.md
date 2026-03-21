# VITALS — C4 Deployment Diagram

> **Audience:** DevOps, hardware integration leads, Lockheed Martin technical reviewers.
> **Purpose:** Shows where VITALS containers run physically — the Jetson hardware, Docker environment, and network topology.
> **C4 Rule:** Use Deployment Nodes to represent infrastructure. Containers are instances of the software containers from Level 2.

```mermaid
C4Deployment
    title Deployment Diagram - VITALS Drone Swarm AI (Field Deployment)

    Deployment_Node(jetson, "NVIDIA Jetson (Field Device)", "ARM64 Linux Ubuntu 22.04 with JetPack SDK") {

        Deployment_Node(dockerHost, "Docker Host", "Docker Engine 24+ with Docker Compose") {

            Deployment_Node(vitalsNet, "vitals_network (Docker Bridge)", "Internal Docker bridge network. Isolated container-to-container communication via hostname") {

                Container(gui, "GUI Container", "Python, CustomTkinter", "Operator-facing mission control interface")

                Container(missionState, "MissionState Container", "Python 3.11", "Central orchestrator and drone state machine")

                Container(agentA, "Agent A Container - Vision and Perception", "Python, YOLOv11, LLaVA", "Video processing and object detection pipeline")

                Container(agentB, "Agent B Container - Data and Knowledge", "Python, ChromaDB, Parquet", "Semantic memory and RAG retrieval service")

                Container(agentC, "Agent C Container - Coordinator and Reasoner", "Python, LangGraph", "LLM reasoning hub and mission coordinator")

                Container(agentD, "Agent D Container - Mapping and Planning", "Python, OSMnx, A-Star", "Terrain analysis and waypoint generation service")

                Container(dispatcher, "Dispatcher Container", "Python, pymavlink", "MAVLink communication layer to Mission Planner")

                Container(ollamaContainer, "Ollama Container", "Ollama Docker image", "Local LLM server hosting LLaMA 3.2 and LLaVA models")

                Container(postGISContainer, "PostGIS Container", "PostgreSQL with PostGIS Docker image", "Offline OpenStreetMap tile and polygon database")
            }

            Deployment_Node(volumeStorage, "Docker Volumes - Persistent Storage", "Local SSD on Jetson") {
                ContainerDb(chromaVol, "ChromaDB Volume", "ChromaDB data directory", "Persisted vector embeddings across container restarts")
                ContainerDb(parquetVol, "Parquet Volume", "Filesystem Arrow IPC", "Append-only mission event archive files")
                ContainerDb(osmVol, "OSM Map Volume", "PostGIS data directory", "Pre-loaded offline OSM map tiles for field area")
            }
        }

        Deployment_Node(jetsonGPU, "Jetson GPU - CUDA", "NVIDIA GPU cores with CUDA 12.x") {
            Component(yoloInference, "YOLOv11 CUDA Inference", "PyTorch with CUDA", "GPU-accelerated bounding box detection on video frames")
            Component(llavaGPU, "LLaVA GPU Inference", "Ollama GPU backend", "GPU-accelerated vision-language model inference")
        }
    }

    Deployment_Node(gcsLaptop, "GCS Laptop / Ground Station", "Windows or macOS operator workstation") {
        Container(missionPlannerApp, "Mission Planner", "ArduPilot GCS .NET", "Ground control station. Routes MAVLink telemetry to VITALS via TCP mirror")
    }

    Deployment_Node(droneFleet, "Drone Swarm", "Physical UAVs in the field") {
        Deployment_Node(pixhawk, "Pixhawk Flight Controller", "ArduPilot Firmware MAVLink 2.0") {
            Component(ardupilot, "ArduPilot", "C++ Firmware", "Executes waypoints, returns telemetry, GPS, and attitude data")
        }
        Deployment_Node(jetsonPayload, "Jetson Nano Payload", "ARM Linux per-drone camera payload") {
            Component(cameraFeed, "Camera Feed", "V4L2 / CSI Camera", "Raw video stream to Agent A via network")
        }
    }

    Rel(dispatcher, missionPlannerApp, "Upstream MAVLink mirror and waypoint upload", "TCP port 14550 LAN / WiFi")
    Rel(missionPlannerApp, ardupilot, "Relays commands and receives telemetry", "MAVLink 2.0 RF telemetry / USB")
    Rel(agentA, cameraFeed, "Receives raw video frames for processing", "Video stream LAN / WiFi")
    Rel(agentC, ollamaContainer, "Sends LLM prompts", "HTTP REST port 11434")
    Rel(agentA, ollamaContainer, "Sends image frames for LLaVA captioning", "HTTP REST port 11434")
    Rel(agentD, postGISContainer, "SQL terrain polygon queries", "TCP port 5432")
    Rel(agentB, chromaVol, "Read and write vector embeddings", "ChromaDB client")
    Rel(agentB, parquetVol, "Append event records", "PyArrow file I/O")
    Rel(postGISContainer, osmVol, "Reads map tile data", "File I/O")
    Rel(ollamaContainer, llavaGPU, "Offloads inference to GPU", "CUDA via Ollama")
    Rel(agentA, yoloInference, "Offloads YOLO detection to GPU", "PyTorch CUDA")
```

## Deployment Topology Summary

| Node | Hardware | Purpose |
|---|---|---|
| NVIDIA Jetson (Field) | ARM64 + NVIDIA GPU | Runs all VITALS Docker containers during field operations |
| Docker Bridge Network | Software (internal) | Isolated container communication; no external port exposure |
| GCS Laptop | Operator workstation | Runs Mission Planner; TCP mirrors MAVLink to VITALS |
| Drone Swarm | Physical UAVs | Execute waypoints; stream video and telemetry |
| Pixhawk (per drone) | ArduPilot controller | MAVLink endpoint; waypoint execution |
| Jetson Nano Payload | Per-drone Jetson | Camera capture and video stream to Agent A |

## Port Reference

| Service | Port | Protocol |
|---|---|---|
| Mission Planner MAVLink mirror | 14550 | TCP |
| Ollama LLM API | 11434 | HTTP REST |
| PostGIS / PostgreSQL | 5432 | TCP (SQL) |
| Docker container-to-container (vitals_network) | Internal only | HTTP / JSON |
