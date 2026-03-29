import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import time
import asyncio
import threading
import sys
import io
import shutil
import re
from dotenv import load_dotenv

load_dotenv()

import toolkit

# Ensure UTF-8 for standard output on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, io.UnsupportedOperation):
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, io.UnsupportedOperation):
        pass


def safe_log(message):
    """Prints a message safely, handling potential Unicode encoding issues on Windows."""
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        try:
            print(message.encode('ascii', 'replace').decode('ascii'), flush=True)
        except Exception:
            pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Background directory scanner
# ---------------------------------------------------------------------------

def background_dir_scanner():
    while True:
        try:
            agents = load_data()
            if agents:
                for agent in agents:
                    wdir = agent.get('workingDir')
                    if wdir and os.path.exists(wdir):
                        dir_map = {}
                        try:
                            file_count = 0
                            for root, dirs, files in os.walk(wdir):
                                if file_count > 1500:
                                    break
                                rel = os.path.relpath(root, wdir)
                                dir_map[rel] = {"files": files, "dirs": dirs}
                                file_count += len(files)

                            out_path = os.path.join(AGENTS_CODE_DIR, agent['id'], "dir_map.json")
                            os.makedirs(os.path.dirname(out_path), exist_ok=True)
                            with open(out_path, "w", encoding="utf-8") as f:
                                json.dump(dir_map, f)
                        except Exception:
                            pass
        except Exception:
            pass
        time.sleep(5)


threading.Thread(target=background_dir_scanner, daemon=True).start()

# ---------------------------------------------------------------------------
# Workmap tick engine
# ---------------------------------------------------------------------------

_main_event_loop = None


def execution_engine_tick():
    """Background tick: every 5 seconds, scan for RUNNING workmaps and dispatch nodes."""
    while _main_event_loop is None:
        time.sleep(0.1)
    while True:
        try:
            agents = load_data()
            for agent in agents:
                agent_id = agent.get("id")
                if not agent_id:
                    continue
                wm_path = os.path.join(AGENTS_CODE_DIR, agent_id, "workmap.json")
                if not os.path.exists(wm_path):
                    continue
                try:
                    with open(wm_path, "r", encoding="utf-8") as f:
                        wm = json.load(f)
                    if wm.get("status") != "RUNNING":
                        continue
                    if any(n.get("status") == "IN_PROGRESS" for n in wm.get("nodes", [])):
                        safe_log(f"[TICK] {agent_id}: node IN_PROGRESS — skipping this tick")
                        continue
                    api_key = os.getenv("GEMINI_API_KEY", "")
                    provider = wm.get("provider", "gemini")
                    safe_log(f"[TICK] {agent_id}: dispatching next node (provider={provider})")
                    from graph.orchestration_graph import execute_next_node
                    asyncio.run_coroutine_threadsafe(
                        execute_next_node(agent_id, api_key, provider),
                        _main_event_loop
                    )
                    safe_log(f"+++ [TICK] {agent_id}: coroutine submitted to event loop")
                except Exception as e:
                    safe_log(f"!!! [TICK] Error reading workmap for {agent_id}: {e}")
        except Exception as e:
            safe_log(f"!!! [TICK] Outer error: {e}")
        time.sleep(5)


threading.Thread(target=execution_engine_tick, daemon=True).start()

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _main_event_loop
    _main_event_loop = asyncio.get_running_loop()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data Storage
DATA_FILE = os.path.join(os.path.dirname(__file__), "agents.json")
AGENTS_CODE_DIR = os.path.join(os.path.dirname(__file__), "agents_code")


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class AgentModel(BaseModel):
    id: str
    name: str
    description: str = ""
    brain: str = ""
    channel: str = "Gmail"
    workingDir: str = ""
    permissions: List[str] = []
    tools: str = "Custom"
    responsibility: str = ""
    agentType: str = "worker"
    specialRole: str = "custom"
    userEffort: int = 1
    humanExpertise: int = 5
    projectSize: str = "small"
    x: float = 0
    y: float = 0
    connections: List[str] = []


class ChatRequest(BaseModel):
    agent_id: str
    message: str
    mode: Optional[str] = "work"
    api_key: Optional[str] = ""
    provider: Optional[str] = "Gemini"


class NodeUpdate(BaseModel):
    label: Optional[str] = None
    task: Optional[str] = None
    agent: Optional[str] = None
    dependencies: Optional[List[str]] = None
    status: Optional[str] = None
    estimated_minutes: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None


class NodeCreate(BaseModel):
    label: str = ""
    task: str
    agent: str = "self"
    dependencies: List[str] = []
    estimated_minutes: int = 0
    x: float = 0
    y: float = 0


class WorkmapUpdate(BaseModel):
    deadline_hours: Optional[int] = None
    status: Optional[str] = None


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"!!! [BACKEND ERROR] Could not parse {DATA_FILE}: {e}")
        return []
    except Exception as e:
        print(f"!!! [BACKEND ERROR] An unexpected error occurred in load_data: {e}")
        return []


def update_agent_directory_md(agents_data):
    try:
        dir_path = os.path.join(AGENTS_CODE_DIR, "agent_directory.md")
        os.makedirs(os.path.dirname(dir_path), exist_ok=True)

        content = "## PROJECT AGENT DIRECTORY\n"
        content += "Below are all agents currently in this project. Use this to identify who to delegate tasks to.\n\n"

        if not agents_data:
            content += "*No agents currently configured.*"
        else:
            for a in agents_data:
                name = a.get("name", "Unknown Agent")
                aid = a.get("id", "Unknown ID")
                resp = a.get("responsibility", "No responsibility set.")
                content += f"- **{name}** (ID: `{aid}`): {resp}\n"
                perms = ", ".join(a.get("permissions", []))
                if perms:
                    content += f"  Capabilities: {perms}\n"
                content += "\n"

        with open(dir_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        safe_log(f"!!! [BACKEND ERROR] Failed to update agent_directory.md: {e}")


def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        update_agent_directory_md(data)
    except Exception as e:
        print(f"!!! [BACKEND ERROR] An unexpected error occurred in save_data: {e}")


CANVASES_DIR = os.path.join(os.path.dirname(__file__), "canvases")
os.makedirs(CANVASES_DIR, exist_ok=True)


def generate_agent_structure(agent_data):
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_data['id'])
    if not os.path.exists(agent_dir):
        os.makedirs(agent_dir)

    # 1. Main Agent Python File
    main_py_path = os.path.join(agent_dir, "main.py")
    class_name = agent_data['id'].replace('-', '_')
    if class_name and class_name[0].isdigit():
        class_name = "A_" + class_name

    main_py_content = f"""
class {class_name}:
    def __init__(self):
        self.id = "{agent_data['id']}"
        self.name = "{agent_data['name']}"
        self.working_dir = r"{agent_data.get('workingDir', '')}"
        self.permissions = {agent_data.get('permissions', [])}
        self.tools = "{agent_data.get('tools', 'Custom')}"

    def get_personality(self):
        import json
        import os
        try:
            with open(os.path.join(os.path.dirname(__file__), 'personality.json'), 'r', encoding="utf-8") as f:
                return json.load(f)
        except:
            return {{}}

if __name__ == "__main__":
    agent = {class_name}()
    print(f"Agent {{agent.name}} initialized.")
"""
    with open(main_py_path, "w", encoding="utf-8") as f:
        f.write(main_py_content)

    # 2. Personality
    personality_path = os.path.join(agent_dir, "personality.json")
    personality_data = {
        "name": agent_data['name'],
        "description": agent_data['description'],
        "responsibility": agent_data.get('responsibility', ''),
        "tools": agent_data.get('tools', 'Custom')
    }
    with open(personality_path, "w", encoding="utf-8") as f:
        json.dump(personality_data, f, indent=2)

    # 3. prompt.md — use template if available, otherwise generic
    prompt_path = os.path.join(agent_dir, "prompt.md")
    special_role = agent_data.get('specialRole', 'custom')
    template_prompt_path = os.path.join(
        os.path.dirname(__file__), "agent_templates", special_role, "prompt.md"
    )

    if special_role != 'custom' and os.path.exists(template_prompt_path):
        with open(template_prompt_path, "r", encoding="utf-8") as f:
            prompt_content = f.read()
    else:
        prompt_content = f"""# Agent Instructions: {agent_data['name']}
Identity: You are an agent sitting in a desktop PC working for the User.
Description: {agent_data['description']}
Responsibility: {agent_data.get('responsibility', 'General purpose assistance')}

## OPERATION RULES
1. **Tool Use**: Use your available tools to complete tasks. Do not explain that you are using a tool; just execute the tool call.
2. **Intent Gate**: Do NOT execute tool calls for casual greetings. Only use research tools if a specific objective is provided.
3. **Planning**: Use `update_plan` ONLY when starting a complex multi-step task.
4. **Citations**: Every fact discovered via research MUST include a source URL citation.
"""
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt_content)

    # 4. Plan
    plan_path = os.path.join(agent_dir, "plan.json")
    if not os.path.exists(plan_path):
        initial_plan = {
            "objective": agent_data.get('responsibility', 'General assistance'),
            "steps": ["Observe Workspace", "Execute requested task"],
            "completed": []
        }
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(initial_plan, f, indent=2)

    # 5. History
    history_path = os.path.join(agent_dir, "history.json")
    if not os.path.exists(history_path):
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump([], f)

    # 6. Manifest
    agent_type = agent_data.get("agentType", "worker")
    manifest = {
        "agent_id": agent_data.get("id", ""),
        "extraction_logic": "RAW_CHUNKS",
        "verification_required": False,
        "output_format": "STRUCTURED_FINDINGS",
        "knowledge_gate": "READ_WRITE" if agent_type == "master" else "WRITE_ONLY_LEDGER"
    }
    manifest_path = os.path.join(agent_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    safe_log(f"+++ [BACKEND] Generated agent structure in: {agent_dir}")


def delete_agent_structure(agent_id):
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_id)
    if os.path.exists(agent_dir):
        try:
            shutil.rmtree(agent_dir)
            safe_log(f"--- [BACKEND] Deleted agent directory: {agent_dir}")
        except Exception as e:
            safe_log(f"!!! [BACKEND ERROR] Could not delete agent directory: {e}")


def get_connected_agents(agent_id, agents):
    """Return list of connected agent info dicts for the given agent."""
    agent_data = next((a for a in agents if a["id"] == agent_id), None)
    if not agent_data:
        return []
    connections_list = agent_data.get("connections", [])
    result = []
    for a in agents:
        if a["id"] in connections_list or agent_id in a.get("connections", []):
            result.append({
                "id": a["id"],
                "name": a.get("name", "Unknown"),
                "responsibility": a.get("responsibility", ""),
                "permissions": a.get("permissions", [])
            })
    return result


def _build_workflow_agents(master_agent_id: str, agents: list) -> dict:
    """Build a role→agent_id mapping from the master agent's workflow.
    Walks the full connection graph (BFS) so agents 2+ hops away
    (e.g. Research → Synthesis → PDF) are still discovered."""
    mapping = {"research": master_agent_id}  # master IS the research agent

    master = next((a for a in agents if a["id"] == master_agent_id), None)
    if not master or not master.get("workflowId"):
        # No workflowId — BFS through connections to find all reachable agents
        if master:
            agents_by_id = {a["id"]: a for a in agents}
            visited = {master_agent_id}
            queue = list(master.get("connections", []))
            while queue:
                aid = queue.pop(0)
                if aid in visited:
                    continue
                visited.add(aid)
                a = agents_by_id.get(aid)
                if not a:
                    continue
                role = a.get("specialRole", "")
                if role == "synthesis":
                    mapping["synthesis"] = a["id"]
                elif role == "pdf-generation":
                    mapping["pdf"] = a["id"]
                # Walk this agent's connections too
                for cid in a.get("connections", []):
                    if cid not in visited:
                        queue.append(cid)
        return mapping

    # Walk all agents in the same workflow
    workflow_id = master.get("workflowId")
    for a in agents:
        if a["id"] == master_agent_id:
            continue
        if a.get("workflowId") == workflow_id:
            role = a.get("specialRole", "")
            if role == "synthesis":
                mapping["synthesis"] = a["id"]
            elif role == "pdf-generation":
                mapping["pdf"] = a["id"]

    return mapping


# ---------------------------------------------------------------------------
# Agent CRUD Endpoints
# ---------------------------------------------------------------------------

@app.get("/agents")
def get_agents():
    agents = load_data()
    if agents is None:
        raise HTTPException(status_code=500, detail="Agent data file is corrupted or unreadable.")
    if not agents:
        master = {
            "id": "agent-MasterBot-001",
            "name": "MasterBot",
            "description": "Main orchestrator agent.",
            "agentType": "master",
            "x": 100, "y": 150,
            "brain": "Gemini",
            "tools": "Gmail",
            "responsibility": "Coordinate all agents",
            "permissions": []
        }
        agents.append(master)
        save_data(agents)
        generate_agent_structure(master)
        safe_log("+++ [BACKEND] No agents found. Created default 'MasterBot'.")
    return agents


@app.post("/agents")
def create_agent(agent: AgentModel):
    agents = load_data()
    for a in agents:
        if a["id"] == agent.id:
            safe_log(f"--- [BACKEND] Agent with ID '{agent.id}' already exists.")
            return a
    agents.append(agent.model_dump())
    save_data(agents)
    generate_agent_structure(agent.model_dump())
    safe_log(f"+++ [BACKEND] Created new agent: '{agent.name}' (ID: {agent.id})")
    return agent


@app.put("/agents/{agent_id}")
def update_agent(agent_id: str, agent: AgentModel):
    agents = load_data()
    for i, a in enumerate(agents):
        if a["id"] == agent_id:
            updated_data = agent.model_dump()
            if updated_data.get("id") != agent_id:
                updated_data["id"] = agent_id
            agents[i] = updated_data
            save_data(agents)
            generate_agent_structure(updated_data)
            safe_log(f"*** [BACKEND] Updated agent: '{agent.name}' (ID: {agent_id})")
            return agents[i]
    raise HTTPException(status_code=404, detail="Agent not found")


@app.delete("/agents/{agent_id}")
def delete_agent(agent_id: str):
    agents = load_data()
    agent_to_delete = next((a for a in agents if a["id"] == agent_id), None)
    if agent_to_delete:
        agents.remove(agent_to_delete)
        save_data(agents)
        delete_agent_structure(agent_id)
        safe_log(f"--- [BACKEND] Deleted agent: '{agent_to_delete.get('name')}' (ID: {agent_id})")
        return {"status": "success", "message": "Agent deleted"}
    raise HTTPException(status_code=404, detail="Agent not found")


# ---------------------------------------------------------------------------
# Canvas Save / Load Endpoints
# ---------------------------------------------------------------------------

@app.get("/canvases")
def list_canvases():
    """Return list of saved canvas files."""
    saves = []
    for fname in sorted(os.listdir(CANVASES_DIR), reverse=True):
        if fname.endswith(".json"):
            fpath = os.path.join(CANVASES_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                saves.append({
                    "filename": fname,
                    "name": data.get("name", fname.replace(".json", "")),
                    "agent_count": len(data.get("agents", [])),
                    "saved_at": data.get("saved_at", ""),
                })
            except Exception:
                pass
    return saves


class CanvasSaveRequest(BaseModel):
    name: str


@app.post("/canvases/save")
def save_canvas(req: CanvasSaveRequest):
    """Snapshot current agents.json into a named canvas save."""
    agents = load_data() or []
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    safe_name = re.sub(r'[^a-zA-Z0-9_\- ]', '', req.name).strip() or "Untitled"
    filename = f"{safe_name.replace(' ', '_')}.json"
    fpath = os.path.join(CANVASES_DIR, filename)
    save_obj = {
        "name": req.name,
        "saved_at": timestamp,
        "agents": agents,
    }
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(save_obj, f, indent=2)
    return {"status": "ok", "filename": filename, "saved_at": timestamp}


@app.post("/canvases/load/{filename}")
def load_canvas(filename: str):
    """Load a saved canvas — replaces current agents.json."""
    fpath = os.path.join(CANVASES_DIR, filename)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Canvas save not found.")
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    agents = data.get("agents", [])
    save_data(agents)
    return {"status": "ok", "agent_count": len(agents), "name": data.get("name", "")}


@app.delete("/canvases/{filename}")
def delete_canvas(filename: str):
    fpath = os.path.join(CANVASES_DIR, filename)
    if os.path.exists(fpath):
        os.remove(fpath)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# History Endpoints
# ---------------------------------------------------------------------------

@app.get("/history/{agent_id}")
def get_history(agent_id: str):
    history_path = os.path.join(AGENTS_CODE_DIR, agent_id, "history.json")
    if not os.path.exists(history_path):
        return []
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


@app.delete("/history/{agent_id}")
def clear_history(agent_id: str):
    history_path = os.path.join(AGENTS_CODE_DIR, agent_id, "history.json")
    try:
        if os.path.exists(history_path):
            os.remove(history_path)
        internal_path = os.path.join(AGENTS_CODE_DIR, agent_id, "internal_history.json")
        if os.path.exists(internal_path):
            os.remove(internal_path)
        comm_log = os.path.join(AGENTS_CODE_DIR, agent_id, "communication.log")
        if os.path.exists(comm_log):
            os.remove(comm_log)
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump([], f)
        safe_log(f"--- [BACKEND] Cleared history for agent: {agent_id}")
        return {"status": "success", "message": "History and logs cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Chat Endpoint — LangGraph powered
# ---------------------------------------------------------------------------

@app.post("/chat")
async def chat_with_agent(request: ChatRequest):
    """Chat endpoint: invokes the LangGraph agent graph and streams SSE events."""
    from langchain_core.messages import HumanMessage
    from graph.agent_graph import build_agent_graph
    from graph.streaming import langgraph_to_sse

    agents = load_data()
    agent_data = next((a for a in agents if a["id"] == request.agent_id), None)
    if not agent_data:
        safe_log(f"!!! [CHAT] agent_id={request.agent_id!r} NOT FOUND in agents.json")
        raise HTTPException(status_code=404, detail="Agent not found")

    connected = get_connected_agents(request.agent_id, agents)
    api_key = request.api_key or os.getenv("GEMINI_API_KEY", "")
    mode = request.mode or "work"
    is_auto = "[AUTO_STEP" in request.message

    safe_log(f">>> [CHAT] agent={request.agent_id} type={agent_data.get('agentType')} mode={mode} is_auto={is_auto} connected={len(connected)} api_key_present={bool(api_key)}")
    safe_log(f"    [CHAT] msg={request.message[:80]!r}")

    graph = build_agent_graph()

    input_state = {
        "messages": [HumanMessage(content=request.message)],
        "agent_id": request.agent_id,
        "agent_name": agent_data.get("name", "Agent"),
        "agent_type": agent_data.get("agentType", "worker"),
        "permissions": agent_data.get("permissions", []),
        "connected_agents": connected,
        "working_dir": agent_data.get("workingDir", ""),
        "system_prompt": "",
        "decision": "",
        "decision_reason": "",
        "mode": mode,
        "is_auto_step": is_auto,
        "iteration": 0,
        "max_iterations": 5 if is_auto else 10,
        "api_key": api_key,
        "session_id": "",
        "current_prompt_md": "",
        # ReAct loop fields — initialized here so LangGraph state has no missing keys
        # build_context will overwrite these with proper values
        "goal": request.message,
        "user_effort": agent_data.get("userEffort", 1),
        "human_expertise": agent_data.get("humanExpertise", 5),
        "project_size": agent_data.get("projectSize", "small"),
        "plan_iterations": 0,
        "max_plan_iterations": 50,
        "current_steps": [],
        "iteration_summaries": [],
        "planner_decision": "",
        "consecutive_clarifications": 0,
        "planner_response": "",
        "planner_question": "",
        # HITL engine fields
        "hitl_phase": "",
        "hitl_session_id": "",
        # Workflow agent mapping — routes STATUS logs to correct agent terminals
        "workflow_agents": _build_workflow_agents(request.agent_id, agents),
    }

    config = {
        "configurable": {"thread_id": request.agent_id},
    }

    async def stream_and_save():
        """Wrap the SSE stream and save history after completion."""
        final_text = ""
        async for chunk in langgraph_to_sse(graph, input_state, config):
            yield chunk
            # Collect final text for history saving
            if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                try:
                    data = json.loads(chunk[6:])
                    if data.get("type") in ("text", "response"):
                        final_text += data.get("content", "")
                except Exception:
                    pass

        # Save to history.json for the UI
        history_path = os.path.join(AGENTS_CODE_DIR, request.agent_id, "history.json")
        os.makedirs(os.path.dirname(history_path), exist_ok=True)
        history = []
        if os.path.exists(history_path):
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                pass

        # Don't save AUTO_STEP messages to UI history
        if not is_auto:
            history.append({"role": "user", "content": request.message})
            if final_text.strip():
                history.append({"role": "assistant", "content": final_text.strip()})
            try:
                with open(history_path, "w", encoding="utf-8") as f:
                    json.dump(history, f, indent=2)
                safe_log(f"--- [CHAT] {request.agent_id}: done — response_len={len(final_text)} history_entries={len(history)}")
            except Exception as e:
                safe_log(f"!!! [CHAT] Failed to save history for {request.agent_id}: {e}")
        else:
            safe_log(f"--- [CHAT] {request.agent_id}: AUTO_STEP done — response_len={len(final_text)} (not saved)")

    return StreamingResponse(
        stream_and_save(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Autonomous Endpoints
# ---------------------------------------------------------------------------

@app.post("/run_autonomous")
async def run_autonomous_agent(request: ChatRequest):
    """Generate intentions (plan + workmap) for a master agent."""
    safe_log(f">>> [RUN_AUTONOMOUS] agent_id={request.agent_id} msg={request.message[:60]!r}")
    agents = load_data()
    agent_data = next((a for a in agents if a["id"] == request.agent_id), None)

    if not agent_data or agent_data.get("agentType", "worker") != "master":
        safe_log(f"    [RUN_AUTONOMOUS] not a master — routing to /chat")
        return await chat_with_agent(request)

    if request.mode != "work":
        safe_log(f"    [RUN_AUTONOMOUS] mode={request.mode!r} — routing to /chat")
        return await chat_with_agent(request)

    provider = request.provider or "gemini"
    api_key = request.api_key or os.getenv("GEMINI_API_KEY", "")

    # Build connected agents info
    connections = agent_data.get("connections", [])
    agents_info_lines = []
    for a in agents:
        if a["id"] == request.agent_id:
            continue
        if a["id"] in connections or request.agent_id in a.get("connections", []):
            perms = ", ".join(a.get("permissions", [])) or "none"
            agents_info_lines.append(
                f"- {a['name']} (ID: {a['id']}): {a.get('responsibility', '')} | Tools: {perms}"
            )
    agents_info = "\n".join(agents_info_lines)
    safe_log(f"    [RUN_AUTONOMOUS] connected_agents={len(agents_info_lines)} provider={provider} api_key_present={bool(api_key)}")

    from graph.orchestration_graph import run_autonomous
    try:
        steps = await run_autonomous(
            request.agent_id, request.message, api_key, provider,
            agents_info, autonomous=True
        )
    except Exception as e:
        safe_log(f"!!! [RUN_AUTONOMOUS] Error on attempt 1: {e}")
        steps = None

    if not steps:
        safe_log(f"    [RUN_AUTONOMOUS] attempt 1 failed — retrying...")
        try:
            steps = await run_autonomous(
                request.agent_id, request.message, api_key, provider,
                agents_info, autonomous=True
            )
        except Exception as e:
            safe_log(f"!!! [RUN_AUTONOMOUS] Retry failed: {e}")
            steps = None

    if not steps:
        safe_log(f"!!! [RUN_AUTONOMOUS] All attempts failed")
        return {"response": "Plan generation failed. Please check your API key and try again."}

    safe_log(f"+++ [RUN_AUTONOMOUS] plan generated: {len(steps)} steps")
    steps_md = "\n".join([f"{i + 1}. {s}" for i, s in enumerate(steps)])
    final_response = (
        f"### Workmap Generated\n\n"
        f"I've created a project Workmap with the following steps:\n\n"
        f"{steps_md}\n\n"
        f"---\n"
        f"Open the Workmap on the canvas to review, edit, or add steps — then click PLAY to start execution."
    )
    return {"response": final_response}


@app.post("/execute_autonomous")
async def execute_autonomous(request: ChatRequest):
    """Triggered by the 'Start' button. Activates the workmap for tick engine dispatch."""
    safe_log(f">>> [EXECUTE_AUTONOMOUS] agent_id={request.agent_id}")
    provider = request.provider or "gemini"
    api_key = request.api_key or os.getenv("GEMINI_API_KEY", "")
    from graph.orchestration_graph import run_execution_loop
    result = await run_execution_loop(request.agent_id, request.message, api_key, provider)
    safe_log(f"+++ [EXECUTE_AUTONOMOUS] result={str(result)[:80]!r}")
    return {"response": result}


# ---------------------------------------------------------------------------
# Workmap Endpoints
# ---------------------------------------------------------------------------

@app.get("/workmap/{agent_id}")
async def get_workmap(agent_id: str):
    wm_path = os.path.join(AGENTS_CODE_DIR, agent_id, "workmap.json")
    if not os.path.exists(wm_path):
        return {"nodes": [], "edges": [], "status": "IDLE"}
    with open(wm_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/workmap/{agent_id}/play")
async def play_workmap(agent_id: str):
    safe_log(f">>> [WORKMAP:PLAY] agent_id={agent_id}")
    wm_path = os.path.join(AGENTS_CODE_DIR, agent_id, "workmap.json")
    if not os.path.exists(wm_path):
        safe_log(f"!!! [WORKMAP:PLAY] No workmap found for {agent_id}")
        raise HTTPException(status_code=404, detail="No workmap found for this agent")
    with open(wm_path, "r", encoding="utf-8") as f:
        wm = json.load(f)
    prev = wm.get("status", "UNKNOWN")
    wm["status"] = "RUNNING"
    with open(wm_path, "w", encoding="utf-8") as f:
        json.dump(wm, f, indent=2)
    safe_log(f"+++ [WORKMAP:PLAY] {agent_id}: {prev} → RUNNING ({len(wm.get('nodes',[]))} nodes)")
    return {"status": "RUNNING", "agent_id": agent_id}


@app.post("/workmap/{agent_id}/pause")
async def pause_workmap(agent_id: str):
    safe_log(f">>> [WORKMAP:PAUSE] agent_id={agent_id}")
    wm_path = os.path.join(AGENTS_CODE_DIR, agent_id, "workmap.json")
    if not os.path.exists(wm_path):
        safe_log(f"!!! [WORKMAP:PAUSE] No workmap found for {agent_id}")
        raise HTTPException(status_code=404, detail="No workmap found for this agent")
    with open(wm_path, "r", encoding="utf-8") as f:
        wm = json.load(f)
    wm["status"] = "PAUSED"
    with open(wm_path, "w", encoding="utf-8") as f:
        json.dump(wm, f, indent=2)
    safe_log(f"+++ [WORKMAP:PAUSE] {agent_id}: now PAUSED")
    return {"status": "PAUSED", "agent_id": agent_id}


def _load_workmap(agent_id: str):
    wm_path = os.path.join(AGENTS_CODE_DIR, agent_id, "workmap.json")
    if not os.path.exists(wm_path):
        raise HTTPException(status_code=404, detail="No workmap found for this agent")
    with open(wm_path, "r", encoding="utf-8") as f:
        return json.load(f), wm_path


def _save_workmap(wm, wm_path):
    with open(wm_path, "w", encoding="utf-8") as f:
        json.dump(wm, f, indent=2)


@app.patch("/workmap/{agent_id}")
async def update_workmap(agent_id: str, body: WorkmapUpdate):
    wm, wm_path = _load_workmap(agent_id)
    if body.deadline_hours is not None:
        wm["deadline_hours"] = body.deadline_hours
    if body.status is not None and body.status in ("PAUSED", "RUNNING", "COMPLETED"):
        wm["status"] = body.status
    _save_workmap(wm, wm_path)
    return wm


@app.put("/workmap/{agent_id}/node/{node_id}")
async def update_node(agent_id: str, node_id: str, body: NodeUpdate):
    wm, wm_path = _load_workmap(agent_id)
    node = next((n for n in wm.get("nodes", []) if n["id"] == node_id), None)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    if body.label is not None:
        node["label"] = body.label
    if body.task is not None:
        node["task"] = body.task
    if body.agent is not None:
        node["agent"] = body.agent
    if body.status is not None and body.status in ("PENDING", "IN_PROGRESS", "COMPLETED", "ERROR"):
        node["status"] = body.status
    if body.estimated_minutes is not None:
        node["estimated_minutes"] = body.estimated_minutes
    if body.x is not None:
        node["x"] = body.x
    if body.y is not None:
        node["y"] = body.y
    if body.dependencies is not None:
        all_ids = {n["id"] for n in wm["nodes"]}
        for dep in body.dependencies:
            if dep == node_id:
                raise HTTPException(status_code=400, detail="A node cannot depend on itself")
            if dep not in all_ids:
                raise HTTPException(status_code=400, detail=f"Dependency '{dep}' does not exist")
        node["dependencies"] = body.dependencies
    _save_workmap(wm, wm_path)
    return node


@app.post("/workmap/{agent_id}/node")
async def add_node(agent_id: str, body: NodeCreate):
    wm, wm_path = _load_workmap(agent_id)
    nodes = wm.get("nodes", [])
    existing_nums = []
    for n in nodes:
        parts = n["id"].split("_")
        if len(parts) >= 2 and parts[-1].isdigit():
            existing_nums.append(int(parts[-1]))
    next_num = max(existing_nums, default=0) + 1
    new_id = f"task_{next_num}"
    all_ids = {n["id"] for n in nodes}
    for dep in body.dependencies:
        if dep not in all_ids:
            raise HTTPException(status_code=400, detail=f"Dependency '{dep}' does not exist")
    new_node = {
        "id": new_id,
        "label": body.label or body.task[:30],
        "agent": body.agent,
        "task": body.task,
        "dependencies": body.dependencies,
        "status": "PENDING",
        "result_summary": "",
        "estimated_minutes": body.estimated_minutes,
        "x": body.x,
        "y": body.y
    }
    nodes.append(new_node)
    wm["nodes"] = nodes
    _save_workmap(wm, wm_path)
    return new_node


@app.delete("/workmap/{agent_id}/node/{node_id}")
async def delete_node(agent_id: str, node_id: str):
    wm, wm_path = _load_workmap(agent_id)
    nodes = wm.get("nodes", [])
    found = any(n["id"] == node_id for n in nodes)
    if not found:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    wm["nodes"] = [n for n in nodes if n["id"] != node_id]
    for n in wm["nodes"]:
        if node_id in n.get("dependencies", []):
            n["dependencies"].remove(node_id)
    _save_workmap(wm, wm_path)
    return {"deleted": node_id, "remaining_nodes": len(wm["nodes"])}


@app.get("/workmap/{agent_id}/agents")
async def get_available_agents(agent_id: str):
    agents = load_data()
    sender = next((a for a in agents if a["id"] == agent_id), None)
    if not sender:
        raise HTTPException(status_code=404, detail="Agent not found")
    connections = sender.get("connections", [])
    result = [{"id": "self", "name": "Master (self)"}]
    for a in agents:
        if a["id"] == agent_id:
            continue
        if a["id"] in connections or agent_id in a.get("connections", []):
            result.append({"id": a["id"], "name": a.get("name", a["id"])})
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, loop="asyncio", access_log=False)
