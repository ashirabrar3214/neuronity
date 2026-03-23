"""
Single-agent reasoning graph — replaces the BDI execute_agent_turn() loop.

Graph structure:
  [START] -> build_context -> deliberate -> {decision?}
                                             CLARIFY  -> respond -> END
                                             RE_PLAN  -> respond -> END
                                             SOLVE    -> call_model -> {tool_call?}
                                                                        yes -> execute_tool -> call_model (loop)
                                                                        no  -> respond -> END
"""
import os
import json
import datetime
from typing import Literal

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from graph.state import AgentState
from graph.llm import get_llm
from graph.tool_definitions import get_tools_for_agent, SILENT_TOOLS, TERMINAL_TOOLS
from graph.checkpointer import get_checkpointer


# ---------------------------------------------------------------------------
# Graph Nodes
# ---------------------------------------------------------------------------

AGENTS_CODE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents_code")


async def build_context(state: AgentState) -> dict:
    """Assemble the system prompt from agent identity, tools, connected agents, and date."""
    agent_id = state["agent_id"]
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_id)

    # Load agent prompt.md
    current_agent_prompt = ""
    prompt_file = os.path.join(agent_dir, "prompt.md")
    if os.path.exists(prompt_file):
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                current_agent_prompt = f.read()
        except Exception:
            pass

    permissions = state["permissions"]
    connected_agents = state["connected_agents"]
    is_master = state["agent_type"] == "master"
    is_training = state["mode"] == "training"

    # Build tool manifest (human-readable list for the system prompt)
    tools = get_tools_for_agent(permissions, len(connected_agents) > 0, is_training, is_master)
    tool_manifest = "\n".join([f"- {t.name}: {t.description}" for t in tools])

    connected_str = "\n".join([
        f"- {a['name']} (ID: {a['id']}): {a.get('responsibility', '')}"
        for a in connected_agents
    ]) or "None"

    # Agent directory (project-wide awareness)
    agent_dir_content = ""
    dir_path = os.path.join(AGENTS_CODE_DIR, "agent_directory.md")
    if os.path.exists(dir_path):
        try:
            with open(dir_path, "r", encoding="utf-8") as f:
                agent_dir_content = f.read()
        except Exception:
            pass

    if is_training:
        system_prompt = (
            f"# YOU ARE A CURIOUS AI INTERN: {state['agent_name']}\n"
            f"You are currently in **TRAINING MODE**. Focus on learning your role.\n\n"
            f"**TRAINING OVERRIDE**: In this mode, you ARE allowed to chat casually with the user, "
            f"answer their questions, and help them refine your behavioral prompt. "
            f"Be helpful, conversational, and non-refusing.\n\n"
            f"## YOUR CURRENT WORK PROMPT (prompt.md):\n```\n{current_agent_prompt}\n```\n"
            f"\n## AVAILABLE TOOLS\n{tool_manifest}\n"
            f"\n## CONNECTED AGENTS\n{connected_str}\n"
            f"\nCURRENT DATE: {datetime.datetime.now().strftime('%Y-%m-%d')}\n"
        )
    else:
        identity_layer = (
            f"IDENTITY: You are an agent named '{state['agent_name']}' working for the User.\n"
            f"DESCRIPTION: {state.get('system_prompt', 'No description.')}\n"
        )

        # Read personality for description/responsibility
        personality_path = os.path.join(agent_dir, "personality.json")
        description = "No description."
        responsibility = "No responsibility set."
        if os.path.exists(personality_path):
            try:
                with open(personality_path, "r", encoding="utf-8") as f:
                    p = json.load(f)
                    description = p.get("description", description)
                    responsibility = p.get("responsibility", responsibility)
            except Exception:
                pass

        identity_layer = (
            f"IDENTITY: You are an agent named '{state['agent_name']}' working for the User.\n"
            f"DESCRIPTION: {description}\n"
            f"RESPONSIBILITY: {responsibility}\n"
        )

        tool_manual_layer = f"## CAPABILITY MANIFEST\n{tool_manifest}\n"

        transient_task_layer = (
            f"## TRANSIENT TASK CONTEXT\n"
            f"CURRENT DATE: {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"{agent_dir_content}\n\n"
            f"IMPORTANT (COLLABORATION RULE): You can ONLY message agents you are DIRECTLY connected to on the canvas.\n"
            f"Reachable Connected Agents:\n{connected_str}\n"
        )

        system_prompt = f"{identity_layer}\n{tool_manual_layer}\n{transient_task_layer}\n"

        if is_master:
            system_prompt += (
                "\n## MASTER PROTOCOL\n"
                "You are a Master Project Manager. Your ONLY job is coordination — NEVER do research yourself.\n\n"
                "When the user gives you a task or project:\n"
                "1. If the request is vague, ask 1-2 clarifying questions (scope, deadline, focus).\n"
                "2. Once you have a clear task, IMMEDIATELY call `create_project_workmap` with the full task description.\n"
                "3. After the workmap is created, tell the user to review it on the canvas and press PLAY.\n\n"
                "CRITICAL RULES:\n"
                "- NEVER use `report_generation` or `generate_report` — those are for worker agents.\n"
                "- NEVER write reports, summaries, or research yourself.\n"
                "- ALWAYS delegate work through `create_project_workmap`.\n"
                "- Your output to the user should ONLY be: clarifying questions OR 'workmap is ready, press PLAY'.\n"
            )

    return {"system_prompt": system_prompt, "current_prompt_md": current_agent_prompt}


async def deliberate(state: AgentState) -> dict:
    """Decide SOLVE / CLARIFY / RE-PLAN using a fast LLM call with structured output."""
    # Skip deliberation in training mode or autonomous steps
    if state["mode"] == "training" or state["is_auto_step"]:
        return {"decision": "SOLVE", "decision_reason": "Auto/training mode — proceeding directly."}

    # Get last user message
    last_message = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            last_message = msg.content
            break

    if not last_message or len(last_message.strip()) < 3:
        return {"decision": "CLARIFY", "decision_reason": "Message too short to act on."}

    # Build deliberation prompt
    permissions = state["permissions"]
    capabilities_str = ", ".join(permissions) if permissions else "unknown"

    # Recent history context
    recent = state["messages"][-10:]
    h_lines = []
    for h in recent:
        role_label = "Agent" if isinstance(h, AIMessage) else "User"
        content = h.content[:300] if h.content else ""
        if content:
            h_lines.append(f"[{role_label}]: {content}")
    history_str = "\n".join(h_lines) if h_lines else "No recent history."

    deliberation_prompt = f"""You are the Deliberation Module. Decide the next action.

--- AGENT IDENTITY ---
Role: {state['agent_name']}
Available Tools: {capabilities_str}

--- RECENT HISTORY ---
{history_str}

Incoming Request: "{last_message[:500]}"

Decide:
1. SOLVE: Clear task within our capability. Proceed to execute.
2. CLARIFY: Request is vague or we lack critical context. Ask for more info.
3. RE-PLAN: New data contradicts current approach. Need to pivot.

RULES:
- If the user request is broad (e.g., "research the Iran war"), you MUST choose CLARIFY and state exactly what context you are missing.
- If you are a 'master' agent, you MUST gather full context first. Only choose SOLVE to explicitly use the 'create_project_workmap' tool once you have perfect clarity.
- NEVER choose RE-PLAN due to a "missing capability" if the required tool IS listed.


Return ONLY a JSON object:
{{"decision": "SOLVE" | "CLARIFY" | "RE-PLAN", "reason": "Short explanation."}}
"""

    try:
        llm = get_llm("fast", state["api_key"], streaming=False)
        result = await llm.ainvoke([HumanMessage(content=deliberation_prompt)])
        text = result.content.strip()

        # Clean JSON from markdown fences
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].strip()

        parsed = json.loads(text)
        decision = parsed.get("decision", "CLARIFY")
        reason = parsed.get("reason", "")
        return {"decision": decision, "decision_reason": reason}
    except Exception as e:
        print(f"!!! [DELIBERATOR ERROR] {e}", flush=True)
        return {"decision": "SOLVE", "decision_reason": f"Deliberation failed ({e}), defaulting to SOLVE."}


async def call_model(state: AgentState) -> dict:
    """Invoke the LLM with the current messages and bound tools."""
    permissions = state["permissions"]
    connected_agents = state["connected_agents"]
    is_master = state["agent_type"] == "master"
    is_training = state["mode"] == "training"

    tools = get_tools_for_agent(permissions, len(connected_agents) > 0, is_training, is_master)
    llm = get_llm("fast", state["api_key"], streaming=True)

    # Build the messages list with system prompt prepended
    system_msg = SystemMessage(content=state["system_prompt"])
    conversation = [system_msg] + list(state["messages"])

    if tools:
        llm_with_tools = llm.bind_tools(tools)
        response = await llm_with_tools.ainvoke(conversation)
    else:
        response = await llm.ainvoke(conversation)

    return {"messages": [response], "iteration": state["iteration"] + 1}


async def respond(state: AgentState) -> dict:
    """Terminal node — no-op, the last message in state is the response."""
    # If we came from CLARIFY, inject an interactive clarification message
    if state["decision"] == "CLARIFY":
        reason = state["decision_reason"]
        
        # NEW: Claude-style interactive prompt
        content = (
            f"🧠 **Clarification Required:**\n{reason}\n\n"
            f"How would you like me to proceed?\n"
            f"[BUTTON: Proceed using your best judgment]\n"
            f"[BUTTON: Wait, I will provide more context]"
        )
        msg = AIMessage(content=content)
        return {"messages": [msg]}
        
    return {}



# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------

def after_deliberation(state: AgentState) -> str:
    if state["decision"] in ("CLARIFY", "RE-PLAN"):
        return "respond"
    return "call_model"


def after_model(state: AgentState) -> str:
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "execute_tool"
    return "respond"


def after_tool(state: AgentState) -> str:
    # Check iteration limit
    if state["iteration"] >= state["max_iterations"]:
        return "respond"

    # Check if a terminal tool was called (report_generation, ask_user)
    messages = state["messages"]
    # Find the last AI message with tool calls
    for msg in reversed(messages):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            last_tool_name = msg.tool_calls[0]["name"]
            if last_tool_name in TERMINAL_TOOLS:
                return "respond"
            break

    return "call_model"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_agent_graph():
    """Compile the single-agent reasoning graph."""
    # We need a broad tool list for the ToolNode — it handles routing based on the
    # tool_calls in the AI message. The actual permission filtering happens in call_model
    # where we bind only the allowed tools to the LLM.
    # For ToolNode, we register ALL possible tools so it can execute any tool call the LLM makes.
    all_tools = get_tools_for_agent(
        ["web search", "report generation", "file access"],
        has_connections=True, is_training=True, is_master=True
    )

    graph = StateGraph(AgentState)

    graph.add_node("build_context", build_context)
    graph.add_node("deliberate", deliberate)
    graph.add_node("call_model", call_model)
    graph.add_node("execute_tool", ToolNode(all_tools))
    graph.add_node("respond", respond)

    graph.add_edge(START, "build_context")
    graph.add_edge("build_context", "deliberate")
    graph.add_conditional_edges("deliberate", after_deliberation, ["call_model", "respond"])
    graph.add_conditional_edges("call_model", after_model, ["execute_tool", "respond"])
    graph.add_conditional_edges("execute_tool", after_tool, ["call_model", "respond"])
    graph.add_edge("respond", END)

    return graph.compile(checkpointer=get_checkpointer())
