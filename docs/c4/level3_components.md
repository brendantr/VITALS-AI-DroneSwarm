# VITALS — C4 Level 3: Component Diagrams

> **Audience:** Developers working inside each agent container.
> **Purpose:** Shows the internal components of each container, their responsibilities, and how they connect.
> **C4 Rule:** Components are not separately deployable — they are logical groupings inside a container (classes, modules, subsystems).

---

## Agent A — Vision & Perception (Component Diagram)

```mermaid
C4Component
    title Component Diagram — Agent A: Vision & Perception

    Container_Ext(droneCamera, "Drone Camera Feed", "Raw video stream\nfrom drone payload")
    Container_Ext(flightController, "Flight Controller", "Provides GPS, altitude,\nheading via MAVLink")
    Container_Ext(ollama, "Ollama", "LLaVA model for\nscene captioning")
    Container_Ext(agentB, "Agent B (Memory)", "Receives MCP\ndetection events")

    Container_Boundary(agentA, "Agent A — Vision & Perception [Container]") {

        Component(frameCapture, "Frame Capture Module", "Python, OpenCV",
            "Extracts key frames from\ndrone video stream at\nconfigured intervals")

        Component(yoloDetector, "YOLO Detector", "Python, YOLOv11\n(custom SAR model)",
            "Runs bounding-box object\ndetection on key frames.\nOutputs class, confidence,\nand bounding-box coordinates")

        Component(llavaClient, "LLaVA Scene Client", "Python, HTTP client",
            "Sends frames to Ollama's\nLLaVA endpoint with SAR-\nspecific prompt template.\nReceives 2-sentence scene\ncaptions")

        Component(telemetryReader, "Telemetry Reader", "Python, pymavlink",
            "Reads GPS, altitude, and\nheading from flight controller\nfor geolocation of detections")

        Component(fusionEngine, "Fusion Engine", "Python",
            "Combines YOLO detections,\nLLaVA captions, and GPS\ntelemetry into a unified\ndetection record")

        Component(mcpPublisher, "MCP Publisher", "Python, JSON Schema\n2020-12",
            "Serializes fused detection\nrecords into MCP packets\nand publishes to Agent B\nover Docker network")
    }

    Rel(droneCamera, frameCapture, "Streams raw video frames", "OpenCV VideoCapture")
    Rel(flightController, telemetryReader, "Sends GPS, heading,\naltitude data", "MAVLink TCP")
    Rel(frameCapture, yoloDetector, "Passes key frames\nfor detection", "In-process (numpy array)")
    Rel(frameCapture, llavaClient, "Passes key frames\nfor scene captioning", "In-process (base64 image)")
    Rel(llavaClient, ollama, "POST image + SAR prompt,\nreceive scene description", "HTTP REST (JSON)")
    Rel(yoloDetector, fusionEngine, "Sends bounding boxes,\nclass labels, confidence", "In-process (dict)")
    Rel(llavaClient, fusionEngine, "Sends scene description\ntext string", "In-process (str)")
    Rel(telemetryReader, fusionEngine, "Provides GPS and\norientation context", "In-process (dict)")
    Rel(fusionEngine, mcpPublisher, "Sends complete detection\nrecord for publication", "In-process (dict)")
    Rel(mcpPublisher, agentB, "Publishes MCP detection\nevent packet", "HTTP / Docker network\n(JSON Schema 2020-12)")
```

---

## Agent B — Data & Knowledge (Component Diagram)

```mermaid
C4Component
    title Component Diagram — Agent B: Data & Knowledge Management

    Container_Ext(agentA, "Agent A (Vision)", "Publishes detection\nMCP events")
    Container_Ext(agentC, "Agent C (Coordinator)", "Sends queries,\nreceives RAG context")
    Container_Ext(agentD, "Agent D (Planning)", "Records planning\nactions taken")
    Container_Ext(guiOp, "GUI / Operator", "Sends user queries\nfor memory retrieval")

    Container_Ext(chromaDB, "ChromaDB", "Vector database\nfor embeddings")
    Container_Ext(parquet, "Parquet Archive", "Structured event\nlog storage")

    Container_Boundary(agentB, "Agent B — Data & Knowledge [Container]") {

        Component(schemaValidator, "Schema Validator", "Python, jsonschema",
            "Validates all incoming MCP\npackets against JSON Schema\n2020-12 specification before\nprocessing")

        Component(memoryEngine, "Memory Engine", "Python, sentence-\ntransformers",
            "Embeds validated events\ninto vector space and\nwrites to ChromaDB for\nsemantic retrieval")

        Component(eventLogger, "Event Logger", "Python, PyArrow",
            "Appends all validated\nevents to Parquet archive\nwith timestamps and source\nagent metadata")

        Component(retrievalEngine, "Retrieval Engine", "Python, ChromaDB SDK",
            "Accepts retrieval queries,\nperforms vector similarity\nsearch, returns Top-K\nranked mission context")

        Component(queryRouter, "Query Router", "Python",
            "Routes incoming messages:\nvalidated events → Memory\nEngine + Event Logger;\nqueries → Retrieval Engine")
    }

    Rel(agentA, schemaValidator, "Sends detection MCP events", "HTTP / Docker network")
    Rel(agentC, schemaValidator, "Sends reasoning log MCP events", "HTTP / Docker network")
    Rel(agentD, schemaValidator, "Sends action log MCP events", "HTTP / Docker network")
    Rel(guiOp, schemaValidator, "Sends operator query MCP messages", "HTTP / Docker network")
    Rel(schemaValidator, queryRouter, "Passes validated messages\nfor routing", "In-process")
    Rel(queryRouter, memoryEngine, "Routes events for embedding\nand storage", "In-process")
    Rel(queryRouter, retrievalEngine, "Routes retrieval queries", "In-process")
    Rel(memoryEngine, chromaDB, "Writes vector embeddings", "ChromaDB Python SDK")
    Rel(memoryEngine, eventLogger, "Forwards event records\nfor archiving", "In-process")
    Rel(eventLogger, parquet, "Appends structured records", "PyArrow write")
    Rel(retrievalEngine, chromaDB, "Performs vector similarity\nsearch (Top-K)", "ChromaDB Python SDK")
    Rel(retrievalEngine, agentC, "Returns ranked mission\ncontext as MCP response", "HTTP / Docker network")
```

---

## Agent C — Coordinator & Reasoner (Component Diagram)

```mermaid
C4Component
    title Component Diagram — Agent C: Coordinator & Reasoner

    Container_Ext(agentA, "Agent A (Vision)", "Sends real-time\ndetection MCP events")
    Container_Ext(agentB, "Agent B (Memory)", "Returns RAG context\nfor reasoning")
    Container_Ext(agentD, "Agent D (Planning)", "Receives ACP\nmission intents")
    Container_Ext(guiOp, "GUI / Operator", "Issues mission\ndirectives")
    Container_Ext(ollama, "Ollama", "LLaMA 3.2 model\nfor LLM inference")

    Container_Boundary(agentC, "Agent C — Coordinator & Reasoner [Container]") {

        Component(directiveIngester, "Directive Ingester", "Python",
            "Receives and parses\noperator directives from\nGUI. Normalises into\nstructured task objects")

        Component(contextFetcher, "Context Fetcher", "Python, HTTP client",
            "Queries Agent B's Retrieval\nEngine for relevant mission\ncontext using semantic search")

        Component(llmClient, "LLM Client", "Python, LangGraph\n+ Ollama HTTP API",
            "Assembles prompt with\noperator directive + RAG\ncontext. Sends to LLaMA 3.2\nvia Ollama. Parses response")

        Component(reasoningEngine, "Reasoning Engine", "Python, LangGraph",
            "Orchestrates multi-step\nreasoning graph. Routes\noutputs to ACP intent\ngenerator or event logger")

        Component(acpIntentGenerator, "ACP Intent Generator", "Python, JSON Schema\n2020-12",
            "Converts reasoning output\ninto structured ACP intent\nmessages for Agent D\n(mission type, priority,\ntarget coordinates)")

        Component(eventEmitter, "Event Emitter", "Python",
            "Serializes reasoning logs\nas MCP events and sends\nto Agent B for mission\nrecord archiving")
    }

    Rel(guiOp, directiveIngester, "Sends operator mission\ndirectives", "ACP JSON / HTTP")
    Rel(agentA, reasoningEngine, "Sends detection context\nvia MCP events", "HTTP / Docker network")
    Rel(directiveIngester, contextFetcher, "Passes parsed directive\nfor context retrieval", "In-process")
    Rel(contextFetcher, agentB, "Queries semantic memory\nfor relevant context", "HTTP / Docker network")
    Rel(agentB, contextFetcher, "Returns Top-K ranked\nmission context", "HTTP / Docker network")
    Rel(contextFetcher, llmClient, "Passes RAG context +\noperator directive", "In-process")
    Rel(llmClient, ollama, "POST prompt to LLaMA 3.2\nendpoint", "HTTP REST (JSON)")
    Rel(ollama, llmClient, "Returns generated reasoning\nresponse text", "HTTP REST (JSON)")
    Rel(llmClient, reasoningEngine, "Passes structured\nreasoning output", "In-process")
    Rel(reasoningEngine, acpIntentGenerator, "Routes mission\nplanning decisions", "In-process")
    Rel(reasoningEngine, eventEmitter, "Routes reasoning logs\nfor archiving", "In-process")
    Rel(acpIntentGenerator, agentD, "Sends ACP mission intent\n(type, priority, location)", "HTTP / Docker network")
    Rel(eventEmitter, agentB, "Publishes reasoning event\nMCP packet", "HTTP / Docker network")
```

---

## Agent D — Mapping & Planning (Component Diagram)

```mermaid
C4Component
    title Component Diagram — Agent D: Mapping & Planning

    Container_Ext(agentC, "Agent C (Coordinator)", "Sends ACP\nmission intents")
    Container_Ext(guiOp, "GUI / Operator", "Defines map tile\n(search area polygon)")
    Container_Ext(postGIS, "PostGIS (OSM Database)", "Provides terrain\npolygon data")
    Container_Ext(agentB, "Agent B (Memory)", "Receives action\nlog MCP events")
    Container_Ext(agentCback, "Agent C (Coordinator)", "Receives completed\npath results")

    Container_Boundary(agentD, "Agent D — Mapping & Planning [Container]") {

        Component(acpIngester, "ACP Ingester / Schema Validator", "Python, jsonschema",
            "Receives ACP intents from\nAgent C and MCP context\nfrom GUI. Validates against\nJSON Schema 2020-12")

        Component(osmFetcher, "OSM Data Fetcher", "Python, OSMnx\n+ PostGIS",
            "Queries PostGIS for terrain\npolygons within the defined\nsearch area. Hydrates the\nterrain cost map data")

        Component(terrainCostMap, "Terrain Cost Map Builder", "Python, NumPy",
            "Converts OSM polygon data\ninto a weighted grid. Assigns\ncost values based on terrain\ntype (obstacle, open, water)")

        Component(pathPlanner, "A* Path Planner", "Python (A*\nalgorithm)",
            "Runs A* search on the terrain\ncost map. Generates optimal\nwaypoint sequences for each\ndrone in the swarm")

        Component(waypointSerializer, "Waypoint Serializer", "Python",
            "Converts A* waypoint output\ninto MAVLink-compatible GPS\ncoordinate lists for the\nDispatcher container")

        Component(acpResponder, "ACP / MCP Responder", "Python, JSON Schema\n2020-12",
            "Packages completed path and\nmap tile as ACP response to\nAgent C. Packages action log\nas MCP event to Agent B")
    }

    Rel(agentC, acpIngester, "Sends ACP mission intent\n(search type, target, priority)", "HTTP / Docker network")
    Rel(guiOp, acpIngester, "Sends user-defined\nmap tile polygon", "HTTP / Docker network")
    Rel(acpIngester, osmFetcher, "Passes validated search\narea for terrain fetch", "In-process")
    Rel(osmFetcher, postGIS, "SQL query for OSM\npolygons in search area", "SQL / PostGIS TCP")
    Rel(osmFetcher, terrainCostMap, "Passes raw OSM polygon\nfeature set", "In-process")
    Rel(terrainCostMap, pathPlanner, "Provides weighted grid\nfor A* search", "In-process (2D array)")
    Rel(pathPlanner, waypointSerializer, "Passes ordered waypoint\ncoordinate sequence", "In-process")
    Rel(waypointSerializer, acpResponder, "Passes serialized\nwaypoint payload", "In-process")
    Rel(acpResponder, agentCback, "Returns drone paths and\nprocessed map tile", "ACP / HTTP Docker network")
    Rel(acpResponder, agentB, "Sends action log\nMCP event record", "MCP / HTTP Docker network")
```
