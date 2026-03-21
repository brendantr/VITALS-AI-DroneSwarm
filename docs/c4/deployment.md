# VITALS — C4 Deployment Diagram

> **Audience:** DevOps, hardware integration leads, Lockheed Martin technical reviewers.
> **Purpose:** Shows where VITALS containers run physically — the Jetson hardware, Docker environment, and network topology.
> **C4 Rule:** Use Deployment Nodes to represent infrastructure. Containers are instances of the software containers from Level 2.

```mermaid
C4Deployment
    title Deployment Diagram — VITALS Drone Swarm AI (Field Deployment)

    Deployment_Node(jetson, "NVIDIA Jetson (Field Device)", "ARM64 Linux (Ubuntu 22.04)\nNVIDIA JetPack SDK") {

        Deployment_Node(dockerHost, "Docker Host", "Docker Engine 24+\nDocker Compose") {

            Deployment_Node(vitalsNet, "vitals_network (Docker Bridge)", "Internal Docker bridge network\nIsolated container-to-container\ncommunication via hostname") {

                Container(gui, "GUI Container", "Python, CustomTkinter",
                    "Operator-facing mission\ncontrol interface")

                Container(missionState, "MissionState Container", "Python 3.11",
                    "Central orchestrator,\ndrone state machine")

                Container(agentA, "Agent A Container\n(Vision & Perception)", "Python, YOLOv11, LLaVA",
                    "Video processing and\nobject detection pipeline")

                Container(agentB, "Agent B Container\n(Data & Knowledge)", "Python, ChromaDB, Parquet",
                    "Semantic memory and\nRAG retrieval service")

                Container(agentC, "Agent C Container\n(Coordinator & Reasoner)", "Python, LangGraph",
                    "LLM reasoning hub\nand mission coordinator")

                Container(agentD, "Agent D Container\n(Mapping & Planning)", "Python, OSMnx, A*",
                    "Terrain analysis and\nwaypoint generation service")

                Container(dispatcher, "Dispatcher Container", "Python, pymavlink",
                    "MAVLink communication\nlayer to Mission Planner")

                Container(ollamaContainer, "Ollama Container", "Ollama (Docker image)",
                    "Local LLM server hosting\nLLaMA 3.2 and LLaVA models")

                Container(postGISContainer, "PostGIS Container", "PostgreSQL + PostGIS\n(Docker image)",
                    "Offline OpenStreetMap\ntile and polygon database")
            }

            Deployment_Node(volumeStorage, "Docker Volumes (Persistent)", "Local SSD/NVMe\non Jetson") {
                ContainerDb(chromaVol, "ChromaDB Volume", "ChromaDB data directory",
                    "Persisted vector embeddings\nacross container restarts")
                ContainerDb(parquetVol, "Parquet Volume", "Filesystem (Arrow IPC)",
                    "Append-only mission\nevent archive files")
                ContainerDb(osmVol, "OSM Map Volume", "PostGIS data directory",
                    "Pre-loaded offline OSM\nmap tiles for field area")
            }
        }

        Deployment_Node(jetsonGPU, "Jetson GPU (CUDA)", "NVIDIA GPU cores\nCUDA 12.x") {
            Component(yoloInference, "YOLOv11 CUDA Inference", "PyTorch + CUDA",
                "GPU-accelerated bounding\nbox detection on video frames")
            Component(llavaGPU, "LLaVA GPU Inference", "Ollama GPU backend",
                "GPU-accelerated vision-\nlanguage model inference")
        }
    }

    Deployment_Node(gcsLaptop, "GCS Laptop / Ground Station", "Windows / macOS\n(Operator workstation)") {
        Container(missionPlannerApp, "Mission Planner", "ArduPilot GCS (.NET / Mono)",
            "Ground control station.\nRoutes MAVLink telemetry\nto VITALS via TCP mirror")
    }

    Deployment_Node(droneFleet, "Drone Swarm", "Physical UAVs (field)") {
        Deployment_Node(pixhawk, "Pixhawk Flight Controller", "ArduPilot Firmware\n(MAVLink 2.0)") {
            Component(ardupilot, "ArduPilot", "C++ Firmware",
                "Executes waypoints,\nreturns telemetry, GPS,\nand attitude data")
        }
        Deployment_Node(jetsonPayload, "Jetson Nano Payload", "ARM Linux\n(per-drone camera payload)") {
            Component(cameraFeed, "Camera Feed", "V4L2 / CSI Camera",
                "Raw video stream\nto Agent A via network")
        }
    }

    %% Network relationships
    Rel(dispatcher, missionPlannerApp, "Upstream MAVLink mirror,\nwaypoint upload", "TCP port 14550\n(LAN / WiFi)")
    Rel(missionPlannerApp, ardupilot, "Relays commands\nand receives telemetry", "MAVLink 2.0\n(RF telemetry / USB)")
    Rel(agentA, cameraFeed, "Receives raw video\nframes for processing", "Video stream\n(LAN / WiFi)")
    Rel(agentC, ollamaContainer, "Sends LLM prompts", "HTTP REST port 11434")
    Rel(agentA, ollamaContainer, "Sends image frames\nfor LLaVA captioning", "HTTP REST port 11434")
    Rel(agentD, postGISContainer, "SQL terrain polygon\nqueries", "TCP port 5432")
    Rel(agentB, chromaVol, "Read/write\nvector embeddings", "ChromaDB client")
    Rel(agentB, parquetVol, "Append event\nrecords", "PyArrow file I/O")
    Rel(postGISContainer, osmVol, "Reads map tile data", "File I/O")
    Rel(ollamaContainer, llavaGPU, "Offloads inference\nto GPU", "CUDA via Ollama")
    Rel(agentA, yoloInference, "Offloads YOLO detection\nto GPU", "PyTorch CUDA")
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
