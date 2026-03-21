# VITALS — C4 Level 1: System Context Diagram

> **Audience:** Everyone — technical and non-technical stakeholders, sponsors (Lockheed Martin), SAR operators.
> **Purpose:** Defines what VITALS is, who uses it, and which external systems it depends on.
> **C4 Rule:** Show the system as a single box. Do NOT show internals. Label every relationship with *what* and *how*.

```mermaid
C4Context
    title System Context Diagram — VITALS Drone Swarm AI (SAR)

    Person(operator, "SAR Operator", "Mission operator who plans,\nlaunches, and monitors drone\nsearch-and-rescue missions")

    System_Boundary(vitals_boundary, "VITALS System") {
        System(vitals, "VITALS", "AI-powered software system enabling\nautonomous drone swarm coordination\nfor search-and-rescue operations")
    }

    System_Ext(missionPlanner, "Mission Planner", "Ground control station (GCS).\nManages drone initialization,\ntelemetry, and MAVLink routing")

    System_Ext(ollama, "Ollama", "Local LLM server.\nHosts LLaMA 3.2 and LLaVA\nmodels for on-device inference")

    System_Ext(osm, "OpenStreetMap (PostGIS)", "Offline geospatial map database.\nProvides terrain polygon data\nfor path planning")

    System_Ext(droneHardware, "Drone Swarm Hardware", "Physical UAV fleet running\nArduPilot firmware. Executes\nwaypoints via MAVLink protocol")

    Rel(operator, vitals, "Defines search area, issues\nmission directives, monitors\nstatus and detections", "GUI (HTTP/WebSocket)")

    Rel(vitals, missionPlanner, "Mirrors MAVLink packets,\nreads telemetry and GPS", "TCP MAVLink over port 14550")

    Rel(missionPlanner, droneHardware, "Forwards waypoints and\ncommands, receives telemetry", "MAVLink / USB / RF")

    Rel(vitals, ollama, "Sends scene images and operator\nqueries, receives LLM reasoning\nand object descriptions", "HTTP REST (JSON)")

    Rel(vitals, osm, "Queries terrain polygons\nfor cost-map generation\nand path planning", "SQL via PostGIS Docker")

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
