"""
Orchestration graph — replaces planner.py.

Handles:
- Plan generation (flat step list)
- DAG workmap generation
- Agent provisioning
- Workmap execution (tick-driven node dispatch)
"""
import os
import re
import json
import time
import asyncio

from graph.llm import get_llm, FAST_MODEL

AGENTS_CODE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents_code")


def safe_log(message):
    try:
        print(message, flush=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# LLM helper (one-shot call for plan/workmap generation)
# ---------------------------------------------------------------------------

async def _call_llm(prompt: str, api_key: str, mode: str = "fast") -> str:
    """One-shot LLM call for plan generation. Falls back to fast model on error."""
    from langchain_core.messages import HumanMessage

    for attempt_mode in ([mode, "fast"] if mode != "fast" else ["fast"]):
        try:
            llm = get_llm(attempt_mode, api_key, streaming=False)
            result = await llm.ainvoke([HumanMessage(content=prompt)])
            content = result.content
            if isinstance(content, list):
                text_parts = [p if isinstance(p, str) else p.get("text", "") for p in content]
                text = text_parts[-1].strip() if text_parts else ""
            else:
                text = content.strip()
            if text:
                return text
            safe_log(f"!!! [ORCHESTRATION] LLM returned empty with mode={attempt_mode}")
        except Exception as e:
            safe_log(f"!!! [ORCHESTRATION] LLM error (mode={attempt_mode}): {e}")

    return ""


# ---------------------------------------------------------------------------
# Plan generation
# ---------------------------------------------------------------------------

async def generate_plan(task, agent_id, api_key, provider, agents_info="", autonomous=False):
    """Generate a numbered list of execution steps."""
    safe_log(f"[STATUS:{agent_id}] Generating execution plan...")

    agents_context = f"\n\nAVAILABLE CONNECTED AGENTS:\n{agents_info}" if agents_info else ""

    if autonomous:
        rule3 = '3. Plan all the way to task completion. Do NOT add an ask_user or check-in step at the end.'
        rule4_note = '4. You MAY use report_generation when the task calls for a final report.'
    else:
        rule3 = '3. The FINAL step must ALWAYS be: "Use ask_user to summarize findings and ask the user where to focus next."'
        rule4_note = '4. NEVER use report_generation unless the user explicitly says "write the report" or "generate the pdf".'

    prompt = f"""You are a master task planner for an autonomous agent workforce. Break the following task into a numbered list of execution steps.{agents_context}

TASK: {task}

CRITICAL RULES:
1. DO NOT plan the entire project from start to finish.
2. Plan ONLY the "Next Logical Phase" (maximum 3 to 4 steps).
{rule3}
{rule4_note}
5. If agents are listed above, name the specific agent and their ID for each step.

Return ONLY a numbered list.

YOUR PLAN:"""

    text = await _call_llm(prompt, api_key, mode="fast")

    if not text:
        safe_log(f"!!! [PLAN] LLM returned empty text for agent {agent_id}")
        return []

    safe_log(f"[PLAN] Raw LLM response ({len(text)} chars): {text[:200]}")

    steps = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if re.match(r'^\d+[\.\)]\s', line):
            step = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
            if step:
                steps.append(step)

    safe_log(f"[PLAN] Parsed {len(steps)} steps from response")
    return steps


def save_plan_json(steps, task, agent_id):
    """Save the committed plan as JSON."""
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_id)
    os.makedirs(agent_dir, exist_ok=True)
    plan_path = os.path.join(agent_dir, "plan.json")
    plan = {"objective": task, "steps": steps, "completed": []}
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
    return plan_path


# ---------------------------------------------------------------------------
# Workmap generation
# ---------------------------------------------------------------------------

async def generate_workmap(task, agent_id, api_key, provider, agents_info=""):
    """Generate a DAG workmap for master agents."""
    safe_log(f"[STATUS:{agent_id}] Generating DAG workmap...")

    agents_context = f"\n\nAVAILABLE CONNECTED AGENTS:\n{agents_info}" if agents_info else ""

    prompt = f"""You are a task planner for an autonomous multi-agent system.
Your job is to decompose the following task into a Directed Acyclic Graph (DAG) of work nodes.{agents_context}

TASK: {task}

OUTPUT RULES (STRICT):
1. Return ONLY a valid JSON array. No markdown, no explanation, no preamble.
2. Each node must have: "id" (string, use "task_1", "task_2" etc.), "label" (short 2-4 word title), "agent" (agent ID string or "self"), "task" (clear instruction string), "dependencies" (array of node IDs that must complete first, empty [] for root nodes).
3. Maximum 6 nodes. Keep each task focused.
4. The FINAL node should generate the report/deliverable.
5. Parallel nodes (no shared dependencies) will run concurrently.

EXAMPLE OUTPUT:
[
  {{"id": "task_1", "label": "Military Analysis", "agent": "agent-geopolitics-001", "task": "Search for current military positions.", "dependencies": []}},
  {{"id": "task_2", "label": "Economic Impact", "agent": "agent-economics-002", "task": "Research economic sanctions.", "dependencies": []}},
  {{"id": "task_3", "label": "Final Report", "agent": "self", "task": "Generate final PDF report.", "dependencies": ["task_1", "task_2"]}}
]

YOUR DAG (JSON array only):"""

    text = await _call_llm(prompt, api_key, mode="fast")

    nodes = None
    if text:
        safe_log(f"    [WORKMAP] LLM response {len(text)} chars — parsing JSON...")
        try:
            raw = re.sub(r"^[\s\S]*?(\[[\s\S]*\])[\s\S]*$", r"\1", text, flags=re.DOTALL)
            raw = re.sub(r"```(?:json)?|```", "", raw).strip()
            nodes = json.loads(raw)
            safe_log(f"+++ [WORKMAP] JSON parsed OK — {len(nodes)} nodes")
        except Exception as e:
            safe_log(f"!!! [WORKMAP] JSON parse failed ({e}), falling back to generate_plan()")

    # Fallback: convert flat steps to sequential nodes
    if not nodes:
        safe_log(f"    [WORKMAP] Using sequential fallback from generate_plan")
        fallback_steps = await generate_plan(task, agent_id, api_key, provider, agents_info, autonomous=True)
        nodes = []
        for i, step in enumerate(fallback_steps):
            nodes.append({
                "id": f"task_{i + 1}",
                "label": f"Step {i + 1}",
                "agent": agent_id,
                "task": step,
                "dependencies": [f"task_{i}"] if i > 0 else []
            })

    workmap = {
        "project_id": f"proj_{int(time.time())}",
        "status": "PAUSED",
        "deadline_hours": 48,
        "provider": provider,
        "nodes": [
            {
                "id": n.get("id", f"task_{i + 1}"),
                "label": n.get("label", n.get("task", "")[:30]),
                "agent": n.get("agent", agent_id),
                "task": n.get("task", ""),
                "dependencies": n.get("dependencies", []),
                "status": "PENDING",
                "result_summary": ""
            }
            for i, n in enumerate(nodes)
        ]
    }

    safe_log(f"[STATUS:{agent_id}] Workmap generated: {len(workmap['nodes'])} nodes")
    return workmap


async def update_workmap_logic(agent_id, instructions, api_key, provider):
    """Reads current workmap, applies user instructions, and saves updated version."""
    workmap_path = os.path.join(AGENTS_CODE_DIR, agent_id, "workmap.json")
    
    if not os.path.exists(workmap_path):
        return "Error: No existing workmap found to update. Please generate a plan first."

    with open(workmap_path, "r", encoding="utf-8") as f:
        current_workmap = json.load(f)

    current_nodes_json = json.dumps(current_workmap.get("nodes", []), indent=2)

    prompt = f"""You are a master task planner updating an existing DAG workmap.
The user has requested changes to the current plan. 

USER INSTRUCTIONS: {instructions}

CURRENT WORKMAP NODES:
{current_nodes_json}

RULES:
1. Apply the user's changes to the existing nodes. 
2. You may modify tasks, change assigned agents, add new nodes, or delete nodes.
3. PRESERVE the "status" and "result_summary" of any nodes you do not change.
4. Return ONLY a valid JSON array of the updated nodes. No markdown.

YOUR UPDATED DAG (JSON array only):"""

    text = await _call_llm(prompt, api_key, mode="fast")

    if not text:
        return "Error: LLM failed to generate updated nodes."

    try:
        raw = re.sub(r"^[\s\S]*?(\[[\s\S]*\])[\s\S]*$", r"\1", text, flags=re.DOTALL)
        raw = re.sub(r"```(?:json)?|```", "", raw).strip()
        updated_nodes = json.loads(raw)
        
        # Merge updated nodes back into workmap
        current_workmap["nodes"] = updated_nodes
        
        with open(workmap_path, "w", encoding="utf-8") as f:
            json.dump(current_workmap, f, indent=2)
            
        provision_workmap_agents(current_workmap, agent_id)
        
        return f"Workmap successfully updated with {len(updated_nodes)} nodes. Please review on the canvas."
    except Exception as e:
        return f"Error parsing updated workmap: {e}"


def save_workmap_json(workmap, agent_id):
    """Persist the DAG workmap to disk."""
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_id)
    os.makedirs(agent_dir, exist_ok=True)
    wm_path = os.path.join(agent_dir, "workmap.json")
    with open(wm_path, "w", encoding="utf-8") as f:
        json.dump(workmap, f, indent=2)
    return wm_path


# ---------------------------------------------------------------------------
# Agent provisioning
# ---------------------------------------------------------------------------

def provision_workmap_agents(workmap, master_agent_id):
    """Auto-create any agents referenced in the workmap that don't yet exist."""
    from interpreter import load_data, save_data, generate_agent_structure

    agents = load_data()
    if agents is None:
        agents = []
    existing_ids = {a["id"] for a in agents}

    master = next((a for a in agents if a["id"] == master_agent_id), None)
    master_x = master.get("x", 0) if master else 0
    master_y = master.get("y", 0) if master else 0

    nodes = workmap.get("nodes", [])
    referenced_agents = set()
    for node in nodes:
        agent = node.get("agent", "")
        if agent and agent not in ("self", "", master_agent_id):
            referenced_agents.add(agent)

    safe_log(f">>> [PROVISION] checking {len(referenced_agents)} referenced agents (existing={len(existing_ids)})")

    created = []
    offset = 0
    for agent_id in referenced_agents:
        if agent_id in existing_ids:
            safe_log(f"    [PROVISION] {agent_id} already exists — skipping")
            continue

        parts = agent_id.replace("agent-", "").split("-")
        name_part = parts[0] if parts else agent_id
        display_name = name_part.replace("_", " ").title()

        task_hint = ""
        for node in nodes:
            if node.get("agent") == agent_id:
                task_hint = node.get("task", "")[:120]
                break

        offset += 1
        new_x = master_x + (offset * 320) - 320
        new_y = master_y + 280

        master_work_dir = (master.get("workingDir", "") if master else "") or ""
        if master_work_dir:
            agent_work_dir = os.path.join(master_work_dir, agent_id)
            os.makedirs(agent_work_dir, exist_ok=True)
        else:
            agent_work_dir = ""

        # Inherit permissions from master so spawned workers can use the same tools
        master_perms = (master.get("permissions", []) if master else []) or ["web_search", "report_generation"]

        new_agent = {
            "id": agent_id,
            "name": display_name,
            "description": task_hint or f"Worker agent for {display_name} tasks",
            "brain": master.get("brain", "") if master else "",
            "channel": "Gmail",
            "workingDir": agent_work_dir,
            "permissions": list(master_perms),
            "tools": "Custom",
            "responsibility": task_hint or f"{display_name} research and analysis",
            "agentType": "worker",
            "x": new_x,
            "y": new_y,
            "connections": []
        }

        agents.append(new_agent)
        generate_agent_structure(new_agent)
        created.append(agent_id)
        safe_log(f"+++ [PROVISION] created '{display_name}' @ x={new_x} y={new_y} workdir={agent_work_dir!r}")

    if created:
        if master:
            existing_conns = master.get("connections", [])
            master["connections"] = existing_conns + created
        save_data(agents)
        safe_log(f"--- [PROVISION] {len(created)} new / {len(referenced_agents)-len(created)} already existed, connected to {master_agent_id}")
    else:
        safe_log(f"--- [PROVISION] No new agents needed")

    return created


# ---------------------------------------------------------------------------
# Autonomous execution orchestration
# ---------------------------------------------------------------------------

async def run_autonomous(agent_id, task, api_key, provider, agents_info="", autonomous=False):
    """Phase 1: Generate plan + workmap."""
    safe_log(f"[STATUS:{agent_id}] Autonomous deliberation complete: Plan generated")

    steps = await generate_plan(task, agent_id, api_key, provider, agents_info, autonomous=autonomous)
    if steps:
        save_plan_json(steps, task, agent_id)

    try:
        workmap = await generate_workmap(task, agent_id, api_key, provider, agents_info)
        provision_workmap_agents(workmap, agent_id)
        save_workmap_json(workmap, agent_id)
        safe_log(f"[STATUS:{agent_id}] Workmap saved — {len(workmap['nodes'])} nodes, status: PAUSED")
    except Exception as e:
        safe_log(f"!!! [WORKMAP] Failed to generate workmap: {e}")

    return steps


async def run_execution_loop(agent_id, task, api_key, provider):
    """Phase 2: Activate the workmap for tick engine dispatch."""
    workmap_path = os.path.join(AGENTS_CODE_DIR, agent_id, "workmap.json")

    if os.path.exists(workmap_path):
        try:
            with open(workmap_path, "r", encoding="utf-8") as f:
                workmap = json.load(f)
            workmap["status"] = "RUNNING"
            workmap["provider"] = provider
            with open(workmap_path, "w", encoding="utf-8") as f:
                json.dump(workmap, f, indent=2)
            node_count = len(workmap.get("nodes", []))
            safe_log(f"[STATUS:{agent_id}] Workmap activated — {node_count} nodes queued for tick engine")
            return (
                f"Execution started. The tick engine is now processing your workmap "
                f"({node_count} nodes). Monitor progress in the canvas — nodes will turn "
                f"blue while running and green when complete."
            )
        except Exception as e:
            safe_log(f"!!! [WORKMAP] Failed to activate workmap: {e}")

    return "No workmap found. Please generate a plan first."


# ---------------------------------------------------------------------------
# Tick engine: execute next workmap node
# ---------------------------------------------------------------------------

async def execute_next_node(agent_id, api_key, provider):
    """Find the next eligible PENDING node and execute it via /chat."""
    workmap_path = os.path.join(AGENTS_CODE_DIR, agent_id, "workmap.json")
    if not os.path.exists(workmap_path):
        return "no_workmap"

    with open(workmap_path, "r", encoding="utf-8") as f:
        workmap = json.load(f)

    if workmap.get("status") != "RUNNING":
        return "paused"

    nodes = workmap.get("nodes", [])
    completed_ids = {n["id"] for n in nodes if n["status"] == "COMPLETED"}
    safe_log(f">>> [TICK_NODE] agent={agent_id} nodes={len(nodes)} completed={len(completed_ids)}")

    # Find first PENDING node with all deps completed
    next_node = None
    for node in nodes:
        if node["status"] == "PENDING":
            deps = node.get("dependencies", [])
            if all(d in completed_ids for d in deps):
                next_node = node
                break

    if next_node is None:
        all_done = all(n["status"] in ("COMPLETED", "ERROR") for n in nodes)
        if all_done:
            workmap["status"] = "COMPLETED"
            with open(workmap_path, "w", encoding="utf-8") as f:
                json.dump(workmap, f, indent=2)
            safe_log(f"[TICK] {agent_id}: All nodes complete — workmap COMPLETED")
            return "done"
        return "blocked"

    # Mark IN_PROGRESS
    next_node["status"] = "IN_PROGRESS"
    with open(workmap_path, "w", encoding="utf-8") as f:
        json.dump(workmap, f, indent=2)

    # Build accumulated context from completed nodes
    accumulated_context = "\n".join(
        f"### {n['task'][:60]}\n{n['result_summary']}"
        for n in nodes
        if n["status"] == "COMPLETED" and n.get("result_summary")
    )

    step_num = next((i + 1 for i, n in enumerate(nodes) if n["id"] == next_node["id"]), 1)
    total = len(nodes)
    target_agent = next_node.get("agent", agent_id)
    if target_agent in ("self", "", None):
        target_agent = agent_id

    PDF_KEYWORDS = ["report", "pdf", "generate", "create", "generation"]
    is_pdf = any(w in next_node["task"].lower() for w in PDF_KEYWORDS)
    session_id = workmap.get("project_id", f"wm_{int(time.time())}")

    safe_log(f"    [TICK_NODE] dispatching: id={next_node['id']} agent={target_agent} is_pdf={is_pdf} task={next_node['task'][:60]!r}")

    result = await _execute_step(
        step_num, total, next_node["task"], target_agent,
        accumulated_context, api_key, provider,
        is_pdf_step=is_pdf, session_id=session_id
    )

    # Reload workmap to ensure we have the latest state before updating
    with open(workmap_path, "r", encoding="utf-8") as f:
        workmap = json.load(f)

    result_str = str(result)

    for node in workmap.get("nodes", []):
        if node["id"] == next_node["id"]:
            node["status"] = "ERROR" if result_str.startswith("Step failed") else "COMPLETED"
            node["result_summary"] = result_str[:300]
            safe_log(f"+++ [TICK_NODE] {next_node['id']} -> {node['status']} summary_len={len(node['result_summary'])}")
            break

    all_done = all(n["status"] in ("COMPLETED", "ERROR") for n in workmap.get("nodes", []))
    if all_done:
        workmap["status"] = "COMPLETED"
        safe_log(f"--- [TICK_NODE] ALL nodes done — workmap COMPLETED")

    with open(workmap_path, "w", encoding="utf-8") as f:
        json.dump(workmap, f, indent=2)

    return "in_progress"


async def _execute_step(step_num, total_steps, step_text, agent_id,
                        accumulated_context, api_key, provider,
                        is_pdf_step=False, session_id=None):
    """Execute a single plan step by calling /chat internally."""
    safe_log(f">>> [STEP_EXEC] step={step_num}/{total_steps} agent={agent_id} is_pdf={is_pdf_step} task={step_text[:60]!r}")

    ctx = accumulated_context.strip()
    if len(ctx) > 12000:
        ctx = ctx[:12000] + "\n\n[... earlier context truncated ...]"

    ctx_section = f"\n\nGATHERED RESEARCH SO FAR:\n{ctx}" if ctx else ""

    if is_pdf_step:
        message = (
            f"[AUTO_STEP {step_num}/{total_steps}] AUTONOMOUS EXECUTION MODE — PDF GENERATION.\n\n"
            f"All research is complete. Your ONLY job now is:\n"
            f"Call the report_generation tool with the topic and context.\n\n"
            f"ORIGINAL TASK: {step_text}\n"
            f"{ctx_section}"
        )
    else:
        message = (
            f"[AUTO_STEP {step_num}/{total_steps}] AUTONOMOUS EXECUTION MODE — EXTRACTION PHASE.\n"
            f"Execute ONLY this specific research step.\n\n"
            f"STEP: {step_text}\n"
            f"{ctx_section}\n\n"
            f"## RULES:\n"
            f"1. Use your tools to research and gather information.\n"
            f"2. Include source URLs for every fact.\n"
            f"3. After completing research, write a brief 2-3 line summary."
        )

    try:
        import httpx
        url = "http://127.0.0.1:8000/chat"
        data = {
            "agent_id": agent_id,
            "message": message,
            "api_key": api_key,
            "provider": provider
        }

        full_text = ""
        safe_log(f"    [STEP_EXEC] POSTing to /chat agent={agent_id} msg_len={len(message)}")
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", url, json=data, timeout=120) as r:
                if r.status_code != 200:
                    safe_log(f"!!! [STEP_EXEC] /chat HTTP {r.status_code} for agent={agent_id}")
                    return f"Step failed: HTTP {r.status_code}"
                async for line in r.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        content = line[6:]
                        if content == "[DONE]":
                            break
                        try:
                            chunk = json.loads(content)
                            if chunk.get("type") == "text":
                                full_text += chunk.get("content", "")
                            elif chunk.get("type") == "error":
                                return f"Step failed: {chunk.get('content')}"
                        except Exception:
                            pass

        safe_log(f"+++ [STEP_EXEC] step {step_num} complete — response_len={len(full_text)}")
        return full_text

    except Exception as e:
        safe_log(f"!!! [STEP_EXEC] step {step_num} exception: {e}")
        return f"Step failed: {str(e)}"
