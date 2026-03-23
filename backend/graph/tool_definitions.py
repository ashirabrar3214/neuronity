"""
LangChain @tool wrappers around existing toolkit.py functions.

Each tool delegates to the real implementation in toolkit.py.
Runtime context (agent_id, working_dir, api_key) is injected via
LangGraph's RunnableConfig so the LLM never sees those parameters.
"""
import os
import json
import re
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from typing import Annotated


# ---------------------------------------------------------------------------
# Helpers to extract injected state
# ---------------------------------------------------------------------------

def _get(state: dict, key: str, default=""):
    return state.get(key, default)


# ---------------------------------------------------------------------------
# WEB SEARCH TOOLS
# ---------------------------------------------------------------------------

@tool
async def web_search(
    query: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Quickly fetch facts and snippets from the web. Use this for targeted, specific lookups."""
    import toolkit
    agent_id = _get(state, "agent_id")
    api_key = _get(state, "api_key")
    return await toolkit.web_search(query, agent_id, api_key=api_key)


@tool
async def deep_search(
    query: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Perform an in-depth research exploration with multiple filtered sources. Use for comprehensive research."""
    import toolkit
    agent_id = _get(state, "agent_id")
    api_key = _get(state, "api_key")
    return await toolkit.deep_search(query, agent_id, api_key=api_key)


# ---------------------------------------------------------------------------
# REPORT GENERATION TOOLS
# ---------------------------------------------------------------------------

@tool
async def report_generation(
    topic: str,
    context: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Generate a polished PDF report. Use when the task calls for a final deliverable document."""
    import toolkit
    agent_id = _get(state, "agent_id")
    working_dir = _get(state, "working_dir")
    api_key = _get(state, "api_key")
    agent_name = _get(state, "agent_name", "Agent")
    tool_input = f"{topic}|{context}"
    return await toolkit.report_generation(agent_id, tool_input, working_dir, api_key, agent_name=agent_name)


@tool
async def generate_report(
    title: str,
    content: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Generate a structured markdown report file in the working directory."""
    import toolkit
    agent_id = _get(state, "agent_id")
    working_dir = _get(state, "working_dir")
    tool_input = f"{title}|{content}"
    return await toolkit.generate_report(agent_id, tool_input, working_dir)


# ---------------------------------------------------------------------------
# AGENT-TO-AGENT COMMUNICATION
# ---------------------------------------------------------------------------

@tool
async def message_agent(
    target_id: str,
    message: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Send a message and delegate a task to a connected specialist agent. You can ONLY message agents you are directly connected to."""
    import toolkit
    agent_id = _get(state, "agent_id")
    api_key = _get(state, "api_key")

    # Load agents to validate connection and get metadata
    from interpreter import load_data, AGENTS_CODE_DIR
    agents = load_data()
    sender = next((a for a in agents if a["id"] == agent_id), None)
    target = next((a for a in agents if a["id"] == target_id), None)

    if not sender:
        return f"Error: Sender agent {agent_id} not found."
    if not target:
        return f"Error: Target agent {target_id} not found."

    # Bidirectional connection check
    sender_conns = sender.get("connections", [])
    target_conns = target.get("connections", [])
    if target_id not in sender_conns and agent_id not in target_conns:
        return (
            f"Error: You are not connected to agent '{target_id}'. "
            f"There is no canvas wire between you. "
            f"Draw a connection on the canvas to enable communication."
        )

    # Pre-delegation capability check
    target_perms = target.get("permissions", [])
    target_conns_list = target.get("connections", [])
    if not target_perms and not target_conns_list:
        target_name = target.get("name", target_id)
        return (
            f"DELEGATION BLOCKED: Agent '{target_name}' has no capabilities enabled "
            f"(no permissions, no connections). Sending them this task will produce no results."
        )

    sender_name = sender.get("name", "Unknown Agent")
    target_provider = target.get("brain", "gemini").lower()

    # Build task context
    sender_plan_path = os.path.join(AGENTS_CODE_DIR, agent_id, "plan.json")
    task_context_lines = []
    try:
        if os.path.exists(sender_plan_path):
            with open(sender_plan_path, "r", encoding="utf-8") as f:
                plan = json.load(f)
                obj = plan.get("objective", "")
                if obj and obj.strip() and obj.strip().lower() not in ("objective", "none", ""):
                    task_context_lines.append(f"Sender's Active Plan: {obj}")
    except Exception:
        pass
    task_context_lines.append(f"Task being delegated: {message[:250]}")
    cap_summary = ", ".join(target_perms) if target_perms else "none"
    task_context_lines.append(f"Your available capabilities: {cap_summary}")
    sender_context_snippet = "\n".join(task_context_lines)

    # Get API key for target provider
    target_api_key = api_key
    config_path = os.path.join(os.getenv('APPDATA', ''), 'easy-company', 'config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
                keys = config_data.get("apiKeys", {})
                if keys.get(target_provider):
                    target_api_key = keys[target_provider]
        except Exception:
            pass

    # Signal the UI
    print(f"[AGENT_MSG:{agent_id}->{target_id}] Contacting {target.get('name', target_id)}", flush=True)

    return await toolkit.message_agent(
        target_id, message.strip(), agent_id, sender_name,
        target_api_key, target_provider,
        context_snippet=sender_context_snippet,
        intent_priority="NORMAL"
    )


# ---------------------------------------------------------------------------
# FILE SYSTEM TOOLS
# ---------------------------------------------------------------------------

@tool
def list_workspace(
    state: Annotated[dict, InjectedState],
) -> str:
    """List all files and folders in the agent's working directory."""
    agent_id = _get(state, "agent_id")
    working_dir = _get(state, "working_dir")
    print(f"[STATUS:{agent_id}] Listing Workspace Files (Real-time Scan)", flush=True)
    if not working_dir or not os.path.exists(working_dir):
        return "Error: Working directory is invalid or not set."

    lines = []
    file_count = 0
    for root, dirs, files in os.walk(working_dir):
        if file_count > 1000:
            break
        rel = os.path.relpath(root, working_dir)
        if rel == ".":
            lines.append("Directory: . (Root)")
        else:
            lines.append(f"Directory: {rel}")
        for d in sorted(dirs):
            lines.append(f"  [DIR]  {d}")
        for fname in sorted(files):
            lines.append(f"  [FILE] {fname}")
        lines.append("")
        file_count += len(files)

    return f"Workspace Directory Map:\n" + "\n".join(lines)


@tool
def scout_file(
    file_path: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Get metadata about a file (size, type, line count) without reading its full contents."""
    import toolkit
    agent_id = _get(state, "agent_id")
    working_dir = _get(state, "working_dir")
    return toolkit.scout_file(agent_id, file_path, working_dir)


@tool
def read_file(
    file_path: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Read a file's contents. Use format 'path' or 'path|start-end' for line ranges."""
    import toolkit
    agent_id = _get(state, "agent_id")
    working_dir = _get(state, "working_dir")
    return toolkit.read_file(agent_id, file_path, working_dir)


@tool
def write_file(
    filename: str,
    content: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Write content to a file in the working directory."""
    import toolkit
    agent_id = _get(state, "agent_id")
    working_dir = _get(state, "working_dir")
    tool_input = f"{filename}|{content}"
    return toolkit.write_file(agent_id, tool_input, working_dir)


# ---------------------------------------------------------------------------
# PLANNING & INTERNAL STATE TOOLS
# ---------------------------------------------------------------------------

@tool
async def update_plan(
    objective_and_steps: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Update your execution plan. Format: 'objective|step1, step2, step3' or just 'objective' with steps on separate lines."""
    import toolkit
    agent_id = _get(state, "agent_id")
    return await toolkit.update_plan(agent_id, objective_and_steps)


@tool
async def ask_user(
    question: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Halt execution and ask the user a question for guidance or clarification."""
    import toolkit
    agent_id = _get(state, "agent_id")
    return await toolkit.ask_user(agent_id, question)


# ---------------------------------------------------------------------------
# TRAINING MODE TOOLS
# ---------------------------------------------------------------------------

@tool
def read_prompt(
    state: Annotated[dict, InjectedState],
) -> str:
    """Read your current identity and behavioral rules (prompt.md)."""
    from interpreter import AGENTS_CODE_DIR
    agent_id = _get(state, "agent_id")
    prompt_file = os.path.join(AGENTS_CODE_DIR, agent_id, "prompt.md")
    try:
        if os.path.exists(prompt_file):
            with open(prompt_file, "r", encoding="utf-8") as f:
                return f"### Current prompt.md:\n\n{f.read()}"
        return "No prompt.md found for this agent yet."
    except Exception as e:
        return f"Error reading prompt: {e}"


@tool
def update_prompt(
    new_content: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Directly rewrite your system instructions (prompt.md) to fix bugs or refine identity."""
    from interpreter import AGENTS_CODE_DIR
    agent_id = _get(state, "agent_id")
    prompt_file = os.path.join(AGENTS_CODE_DIR, agent_id, "prompt.md")
    try:
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(new_content.strip())
        print(f"[TRAINING] Agent {agent_id} updated its own prompt.", flush=True)
        return "prompt.md has been successfully updated. The new prompt is now active."
    except Exception as e:
        return f"Error updating prompt: {e}"


@tool
def read_memory(
    state: Annotated[dict, InjectedState],
) -> str:
    """Read your long-term memory summary (summary.json)."""
    from interpreter import AGENTS_CODE_DIR
    agent_id = _get(state, "agent_id")
    summary_file = os.path.join(AGENTS_CODE_DIR, agent_id, "summary.json")
    try:
        if os.path.exists(summary_file):
            with open(summary_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return f"### Long-Term Memory:\n\n{data.get('summary', 'No summary recorded yet.')}"
        return "No long-term memory exists for this agent yet."
    except Exception as e:
        return f"Error reading memory: {e}"


# ---------------------------------------------------------------------------
# MASTER AGENT TOOLS
# ---------------------------------------------------------------------------

@tool
async def create_project_workmap(
    finalized_task: str,
    state: Annotated[dict, InjectedState],
) -> str:
    """Generate the DAG execution tree for the project and save it as a workmap. Call this ONLY after scouting is complete and the user has confirmed the goal and deadline."""
    agent_id = _get(state, "agent_id")
    api_key = _get(state, "api_key")

    from interpreter import load_data, AGENTS_CODE_DIR
    agents = load_data()
    sender = next((a for a in agents if a["id"] == agent_id), None)
    connections = sender.get("connections", []) if sender else []

    agents_info_lines = []
    for a in agents:
        if a["id"] == agent_id:
            continue
        if a["id"] in connections or agent_id in a.get("connections", []):
            perms = ", ".join(a.get("permissions", [])) or "none"
            agents_info_lines.append(
                f"- {a['name']} (ID: {a['id']}): {a.get('responsibility', '')} | Tools: {perms}"
            )
    agents_info = "\n".join(agents_info_lines)

    from graph.orchestration_graph import run_autonomous
    await run_autonomous(agent_id, finalized_task, api_key, "gemini", agents_info, autonomous=True)

    return (
        "SYSTEM: Workmap successfully generated and saved to disk. "
        "INSTRUCTION: Tell the user the plan is ready. Tell them to review the DAG Workmap "
        "inside your agent card on the canvas, and click the PLAY button to start the background execution engine."
    )


# ---------------------------------------------------------------------------
# TOOL LIST BUILDER
# ---------------------------------------------------------------------------

# Tools whose results should not be streamed to the UI
SILENT_TOOLS = {"update_plan"}

# Tools that terminate the agent turn after execution
TERMINAL_TOOLS = {"report_generation", "ask_user"}


def get_tools_for_agent(permissions: list, has_connections: bool,
                        is_training: bool = False, is_master: bool = False) -> list:
    """Build the tool list based on agent permissions.

    Replaces get_gemini_tools_from_permissions() entirely.
    """
    tools = []

    if "web search" in permissions:
        tools.extend([web_search, deep_search])
    # Master agents should never generate reports — only workers do
    if "report generation" in permissions and not is_master:
        tools.extend([report_generation, generate_report])
    if "file access" in permissions:
        tools.extend([list_workspace, scout_file, read_file, write_file])
    if has_connections:
        tools.append(message_agent)

    # Always-available tools
    tools.extend([ask_user, update_plan])

    # Training-only tools
    if is_training:
        tools.extend([update_prompt, read_prompt, read_memory])

    # Master-only tool
    if is_master:
        tools.append(create_project_workmap)

    return tools
