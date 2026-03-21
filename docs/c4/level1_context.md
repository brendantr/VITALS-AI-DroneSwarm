# VITALS — C4 Level 1: System Context Diagram

> **Audience:** Everyone — technical and non-technical stakeholders, sponsors (Lockheed Martin), SAR operators.
> **Purpose:** Defines what VITALS is, who uses it, and which external systems it depends on.
> **C4 Rule:** Show the system as a single box. Do NOT show internals. Label every relationship with *what* and *how*.

```mermaid
C4Context
    title System Context Diagram - VITALS Drone Swarm AI (SAR)

    Person(operator, "SAR Operator", "Mission operator who plans, launches, and monitors drone search-and-rescue missions")

    System_Ext(missionPlanner, "Mission Planner", "Ground control station (GCS). Manages drone initialization, telemetry, and MAVLink routing")
    System_Ext(osm, "OpenStreetMap / PostGIS", "Offline geospatial map database. Provides terrain polygon data for path planning")
    System_Ext(ollama, "Ollama", "Local LLM server. Hosts LLaMA 3.2 and LLaVA models for on-device inference")
    System_Ext(droneHardware, "Drone Swarm Hardware", "Physical UAV fleet running ArduPilot firmware. Executes waypoints via MAVLink protocol")

    System_Boundary(vitals_boundary, "VITALS System") {
        System(vitals, "VITALS", "AI-powered software system enabling autonomous drone swarm coordination for search-and-rescue operations")
    }

    Rel(operator, vitals, "Defines search area, issues mission directives, monitors status and detections", "GUI - HTTP/WebSocket")
    Rel(vitals, missionPlanner, "Mirrors MAVLink packets, reads telemetry and GPS", "TCP MAVLink port 14550")
    Rel(missionPlanner, droneHardware, "Forwards waypoints and commands, receives telemetry", "MAVLink / USB / RF")
    Rel(vitals, ollama, "Sends scene images and operator queries, receives LLM reasoning and object descriptions", "HTTP REST - JSON")
    Rel(vitals, osm, "Queries terrain polygons for cost-map generation and path planning", "SQL via PostGIS Docker")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Element Descriptions

| Element | Type | Description |
|---|---|---|
| SAR Operator | Person | The human user who controls the mission via the VITALS GUI |
| VITALS | Software System | The system under design — orchestrates agents, processes video, plans paths |
| Mission Planner | External Software System | ArduPilot GCS acting as MAVLink router between VITALS and drones |
| Ollama | External Software System | On-device LLM server; never calls external cloud APIs |
| OpenStreetMap / PostGIS | External Software System | Offline map database containerized locally for field operations |
| Drone Swarm Hardware | External System | Physical UAVs; not owned or developed by VITALS team |
