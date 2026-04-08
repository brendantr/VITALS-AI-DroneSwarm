import json
import ollama
import requests


AGENT_B_URL = "http://localhost:8081"


def _query_agent_b(user_message: str, n_results: int = 5) -> str:
    """Query Agent B for relevant detection history and mission context."""
    try:
        resp = requests.post(
            f"{AGENT_B_URL}/query",
            json={
                "schema": "agentb.api.v0.1",
                "type": "AgentB.QueryRequest",
                "query": user_message,
                "n_results": n_results,
                "rerank": False,
            },
            timeout=3,
        )
        if resp.status_code != 200:
            return ""
        results = resp.json().get("results", [])
        if not results:
            return ""
        lines = []
        for r in results:
            text = r.get("text", "")
            meta = r.get("metadata", {})
            ts = meta.get("ts", "")
            if text:
                entry = f"- {text}"
                if ts:
                    entry += f" (at {ts})"
                lines.append(entry)
        return "\n".join(lines)
    except Exception:
        return ""


def call_llm(prompt, mission_area, drones, pois):

    # -- Tool definitions (Ollama reads the docstrings + type hints) --

    def create_poi_investigate_job(poi_id: int, drone_id: int, priority: int = 5):
        """
        Send a drone to investigate a specific point of interest (POI).
        Use this when the user wants a drone to go look at or check on a POI.

        Args:
            poi_id: The numeric ID of the POI to investigate
            drone_id: The numeric ID of the drone to send
            priority: Job priority 5-7, higher is more urgent. Default 5.
        """
        pass

    def call_return_to_launch(drone_id: int):
        """
        Command a single drone to return to its launch position (RTL).
        Only use this when the user explicitly asks to bring a specific drone home or call it back.

        Args:
            drone_id: The numeric ID of the drone to recall
        """
        pass

    def call_end_mission():
        """
        End the entire mission and recall ALL drones to their launch positions.
        Only use this when the user explicitly wants to end or abort the whole mission.
        Do NOT use this for a single drone — use call_return_to_launch instead.
        """
        pass

    def call_start_mission():
        """
        Start the search mission, deploying all drones on their planned search paths.
        Use this when the user wants to begin or launch the mission.
        """
        pass

    def resume_drone_mission(drone_id: int):
        """
        Resume a paused drone's mission. The drone will stop circling and continue its search path.
        Use this when the user says to continue, resume, or unpause a specific drone.

        Args:
            drone_id: The numeric ID of the drone to resume
        """
        pass

    # -- Build context --

    rag_context = _query_agent_b(prompt)

    detection_context = ""
    if rag_context:
        detection_context = (
            "\n\nRecent detection and mission history from Agent B:\n"
            f"{rag_context}\n"
        )

    system_prompt = f"""You are a search and rescue drone mission operator assistant for the VITALS system.
You help the user manage their drone fleet during SAR missions.

Current mission state:
- Mission area polygon: {json.dumps(mission_area) if mission_area else 'Not set'}
- Active drones: {json.dumps(drones) if drones else 'None connected'}
- Points of interest: {json.dumps(pois) if pois else 'None detected'}{detection_context}

CRITICAL RULES — you MUST follow these:
1. ONLY call a tool when the user gives a DIRECT, EXPLICIT command to control a drone or mission.
2. For questions, greetings, conversation, or anything that is NOT a direct command, just reply with text. Do NOT call any tool.
3. If you are unsure whether the user wants an action, DO NOT call a tool. Just ask for clarification.

Tool usage guide (ONLY when user gives a direct command):
- "send drone X to investigate poi Y" → create_poi_investigate_job
- "bring drone X home" or "recall drone X" → call_return_to_launch
- "end mission" or "abort mission" → call_end_mission
- "start mission" or "begin search" → call_start_mission
- "continue drone X" or "resume drone X" → resume_drone_mission

Keep responses concise — 1-2 sentences maximum."""

    # Stage 1: Ask the LLM WITHOUT tools whether this is a command or a question.
    classify_prompt = (
        "You are a classifier. The user sent a message to a drone control system.\n"
        "Decide: is this a DIRECT COMMAND to control drones/mission, or is it a QUESTION/CONVERSATION?\n"
        "Reply with ONLY one word: COMMAND or QUESTION\n\n"
        f"User message: \"{prompt}\""
    )
    classify_resp = ollama.chat(
        model="llama3.2",
        messages=[{"role": "user", "content": classify_prompt}],
    )
    classification = classify_resp.message.content.strip().upper()

    # Stage 2: Only provide tools if classified as a command
    if "COMMAND" in classification:
        response = ollama.chat(
            model="llama3.2",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            tools=[
                create_poi_investigate_job,
                call_return_to_launch,
                call_end_mission,
                call_start_mission,
                resume_drone_mission,
            ],
        )
    else:
        response = ollama.chat(
            model="llama3.2",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
    return response.message


def give_image_description(image_path):
    system_prompt = """You are part of a drone flight operator system. You are tasked with describing images taken by drones
    to create a useful description of what is located at the point of interest. Descriptions should be no longer than a couple of sentences.
    And only describe simple details which would be useful in a search and rescue operation."""

    response = ollama.chat(
        model="llava",
        messages=[{
            "role": "user",
            "content": system_prompt,
            "images": [image_path],
        }],
    )
    return response.message
