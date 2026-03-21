# VITALS — C4 Architecture Documentation
**System:** VITALS Drone Swarm AI (Search & Rescue)
**Sponsor:** Lockheed Martin
**Team:** UCF Senior Design — VITALS Team
**Methodology:** C4 Model (Simon Brown) — [c4model.com](https://c4model.com)
**Notation:** Mermaid C4 (JSON Schema 2020-12 / Structurizr-compatible)
**Language:** Python 3.11 | Docker | Jetson | MAVLink

---

## Document Index

| File | C4 Level | Audience | Scope |
|---|---|---|---|
| [level1_context.md](./level1_context.md) | L1 — System Context | Everyone | VITALS as a black box + external actors |
| [level2_container.md](./level2_container.md) | L2 — Container | Developers, DevOps | Docker containers + protocols inside VITALS |
| [level3_components.md](./level3_components.md) | L3 — Component | Internal developers | Internal modules of each Agent container |
| [deployment.md](./deployment.md) | Deployment | DevOps, Hardware leads | Physical infrastructure: Jetson, Docker, drones |

---

## C4 Abstraction Hierarchy

```
L1: System Context
└── VITALS (black box) ↔ Operator, Mission Planner, Ollama, PostGIS, Drone Hardware

    L2: Container
    └── GUI, MissionState, Agent A, Agent B, Agent C, Agent D, Dispatcher, ChromaDB, Parquet

        L3: Component (per container)
        ├── Agent A: FrameCapture → YOLO → LLaVA → FusionEngine → MCPPublisher
        ├── Agent B: SchemaValidator → QueryRouter → MemoryEngine / RetrievalEngine
        ├── Agent C: DirectiveIngester → ContextFetcher → LLMClient → ReasoningEngine → ACPIntentGenerator
        └── Agent D: ACPIngester → OSMFetcher → TerrainCostMap → A*Planner → WaypointSerializer

            Deployment
            └── Jetson ARM64 + Docker Bridge Network + GCS Laptop + Drone Fleet
```

---

## C4 Notation Key

| Shape | Meaning |
|---|---|
| `Person(...)` | A human actor (user, operator) |
| `System(...)` | The system under design (VITALS) |
| `System_Ext(...)` | An external software system (Mission Planner, Ollama, etc.) |
| `Container(...)` | A deployable Docker container or runtime process |
| `ContainerDb(...)` | A data store (database, volume) |
| `Component(...)` | A logical internal module or class grouping |
| `Deployment_Node(...)` | Physical or virtual infrastructure node |
| `Rel(A, B, "label", "protocol")` | A directed relationship from A to B |
| `System_Boundary(...)` | Dashed boundary enclosing the system under design |
| `Container_Boundary(...)` | Dashed boundary enclosing a container's components |

---

## Communication Protocol Reference

| Protocol | Layer | Format | Usage in VITALS |
|---|---|---|---|
| **MCP** (Message Communication Protocol) | Event / Data | JSON Schema 2020-12 | Facts, detections, events, queries between all agents |
| **ACP** (Agent Communication Protocol) | Intent / Action | JSON Schema 2020-12 | Mission intents, planning requests, C ↔ D coordination |
| **MAVLink 2.0** | Drone control | Binary (over TCP) | Waypoint upload, telemetry, heartbeat |
| **HTTP REST** | LLM inference | JSON | Agent A/C → Ollama for LLaVA / LLaMA 3.2 |
| **SQL (PostGIS)** | Geodata | SQL over TCP 5432 | Agent D → PostGIS for terrain polygon queries |

---

## C4 Best Practices Applied

1. **Every element has**: Name, Type label `[Container]`, technology, and a short description
2. **Unidirectional arrows only** — bidirectional relationships are modeled as two separate `Rel` entries where needed
3. **All relationships labeled** with both *what* (semantic purpose) and *how* (protocol/format)
4. **Technology tagged** on every container and component
5. **External systems clearly bounded** — Ollama, PostGIS, and MissionPlanner are outside the VITALS system boundary
6. **No cross-level leakage** — L1 shows no containers; L2 shows no components
7. **Deployment diagram is separate** from L2 — avoids mixing logical and physical architecture
8. **Consistent terminology** across all levels (same names for same elements)

---

## Rendering Instructions

These diagrams use [Mermaid C4](https://mermaid.js.org/syntax/c4.html) syntax.

**GitHub:** Paste any diagram block directly into a `.md` file — GitHub renders Mermaid natively.
**VS Code:** Install the "Mermaid Preview" extension.
**Notion:** Use the Mermaid code block — paste diagram content inside.
**Structurizr:** Convert to Structurizr DSL for export-quality PDF/SVG rendering.
**Live editor:** [mermaid.live](https://mermaid.live) — paste the diagram block to preview instantly.
