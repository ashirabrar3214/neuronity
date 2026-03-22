import httpx
import json
import os
import re
import time
import asyncio

BACKEND_URL = "http://127.0.0.1:8000"
AGENTS_CODE_DIR = os.path.join(os.path.dirname(__file__), "agents_code")

# -- LLM Models (Abstracting for easy upgrades) --
FAST_MODEL = os.getenv("FAST_MODEL", "gemini-2.0-flash")
REASONING_MODEL = os.getenv("REASONING_MODEL", "gemini-3-flash-preview")


def safe_log(message):
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        print(message.encode('ascii', 'replace').decode('ascii'), flush=True)
    except Exception:
        pass


async def _call_llm_direct(prompt, api_key, provider, mode="fast"):
    """One-shot LLM call for plan generation or task classification."""
    if provider == "gemini":
        if mode == "think":
            model = REASONING_MODEL
            # Enable deep reasoning ONLY for plan generation
            generation_config = {
                "temperature": 0.2
            }
            # Only apply thinkingConfig if using Gemini 3/Thinking-compatible models
            if "gemini-3" in REASONING_MODEL or "thinking" in REASONING_MODEL.lower():
                generation_config["thinkingConfig"] = {"includeThoughts": True, "thinkingBudget": -1}
        else:
            model = FAST_MODEL
            # Fast, standard generation for simple routing
            generation_config = {"temperature": 0.2}

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload, timeout=120)
                if resp.status_code == 200:
                    parts = resp.json()["candidates"][0]["content"]["parts"]
                    # Gemini 3 returns multiple parts (thoughts, then text). 
                    # The final text plan is always the last part in the array.
                    return parts[-1]["text"].strip()
                else:
                    safe_log(f"!!! [PLAN_RUNNER] API Error: {resp.text}")
        except Exception as e:
            safe_log(f"!!! [PLAN_RUNNER] LLM error: {e}")

    return ""




async def generate_plan(task, agent_id, api_key, provider, agents_info="", autonomous=False):
    """
    Ask the LLM to break the task into numbered execution steps.
    autonomous=True: master agents skip the ask_user check-in and proceed to completion.
    """
    safe_log(f"[STATUS:{agent_id}] Generating execution plan...")

    agents_context = f"\n\nAVAILABLE CONNECTED AGENTS:\n{agents_info}" if agents_info else ""

    if autonomous:
        rule3 = '3. Plan all the way to task completion. Do NOT add an ask_user or check-in step at the end. Proceed end-to-end and generate the final deliverable.'
        rule4_note = '4. You MAY use report_generation or generate_report when the task naturally calls for a final report or summary.'
    else:
        rule3 = '3. The FINAL step of your plan must ALWAYS be: "Use ask_user to summarize findings so far and ask the user where to focus next."'
        rule4_note = '4. NEVER use the report_generation or generate_report tools unless the user\'s prompt EXPLICITLY says "write the report", "generate the pdf", or "finalize it".'

    prompt = f"""You are a master task planner for an autonomous agent workforce. Break the following task into a numbered list of execution steps.{agents_context}

TASK: {task}

CRITICAL STEERABLE AGENCY RULES:
1. DO NOT plan the entire project from start to finish.
2. Plan ONLY the "Next Logical Phase" (maximum 3 to 4 steps of research or data gathering).
{rule3}
{rule4_note}
5. If agents are listed above, name the specific agent and their ID for each step.

Return ONLY a numbered list. Example of a Phase 1 plan:
1. Ask Military Historian (agent-xxx) to gather timeline data on the conflict.
2. Ask Geopolitics Researcher (agent-yyy) to pull current UN sanctions data.
3. Use ask_user to summarize the gathered intel and ask the user if they want to focus the final report on the military timeline or the economic sanctions.

YOUR PLAN:"""

    text = await _call_llm_direct(prompt, api_key, provider, mode="think")

    steps = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if re.match(r'^\d+[\.\)]\s', line):
            step = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
            if step:
                steps.append(step)

    return steps


def save_plan_json(steps, task, agent_id):
    """Save the committed plan as JSON for the BDI state."""
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_id)
    os.makedirs(agent_dir, exist_ok=True)
    plan_path = os.path.join(agent_dir, "plan.json")

    # Format it exactly like the toolkit.py update_plan does
    plan = {
        "objective": task,
        "steps": steps,
        "completed": []
    }
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    return plan_path


async def generate_workmap(task, agent_id, api_key, provider, agents_info=""):
    """
    Generate a DAG workmap for master agents.
    Calls the LLM with a structured prompt that returns a JSON array of nodes.
    Includes robust regex pre-processing before json.loads() to strip reasoning
    preamble and markdown code fences that LLMs commonly include.
    Falls back to a sequential node list derived from generate_plan() if parsing fails.
    """
    safe_log(f"[STATUS:{agent_id}] Generating DAG workmap...")

    agents_context = f"\n\nAVAILABLE CONNECTED AGENTS:\n{agents_info}" if agents_info else ""

    prompt = f"""You are a task planner for an autonomous multi-agent system.
Your job is to decompose the following task into a Directed Acyclic Graph (DAG) of work nodes.{agents_context}

TASK: {task}

OUTPUT RULES (STRICT):
1. Return ONLY a valid JSON array. No markdown, no explanation, no preamble.
2. Each node must have: "id" (string, use "task_1", "task_2" etc.), "label" (short 2-4 word title for this step, e.g. "Oil Price Analysis"), "agent" (agent ID string or "self"), "task" (clear instruction string), "dependencies" (array of node IDs that must complete first, empty [] for root nodes).
3. Maximum 6 nodes. Keep each task focused on a single research or execution action.
4. The FINAL node should always generate the report/deliverable.
5. Parallel nodes (no shared dependencies) will be dispatched concurrently — use this for independent research tasks.

EXAMPLE OUTPUT:
[
  {{"id": "task_1", "label": "Military Analysis", "agent": "agent-geopolitics-001", "task": "Search for current military positions and recent engagements.", "dependencies": []}},
  {{"id": "task_2", "label": "Economic Impact", "agent": "agent-economics-002", "task": "Research economic sanctions and trade disruptions.", "dependencies": []}},
  {{"id": "task_3", "label": "Final Report", "agent": "self", "task": "Generate final PDF report synthesizing all research.", "dependencies": ["task_1", "task_2"]}}
]

YOUR DAG (JSON array only):"""

    text = await _call_llm_direct(prompt, api_key, provider, mode="think")

    nodes = None
    if text:
        try:
            # Step 1: Extract the JSON array, stripping any preamble or postamble
            raw = re.sub(r"^[\s\S]*?(\[[\s\S]*\])[\s\S]*$", r"\1", text, flags=re.DOTALL)
            # Step 2: Remove markdown code fences if present
            raw = re.sub(r"```(?:json)?|```", "", raw).strip()
            nodes = json.loads(raw)
        except Exception as e:
            safe_log(f"!!! [WORKMAP] JSON parse failed ({e}), falling back to generate_plan()")

    # Fallback: convert flat steps to sequential single-dep nodes
    if not nodes:
        fallback_steps = await generate_plan(task, agent_id, api_key, provider, agents_info, autonomous=True)
        nodes = []
        for i, step in enumerate(fallback_steps):
            nodes.append({
                "id": f"task_{i+1}",
                "label": f"Step {i+1}",
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
                "id": n.get("id", f"task_{i+1}"),
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


def save_workmap_json(workmap, agent_id):
    """Persist the DAG workmap to agents_code/{agent_id}/workmap.json."""
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_id)
    os.makedirs(agent_dir, exist_ok=True)
    workmap_path = os.path.join(agent_dir, "workmap.json")
    with open(workmap_path, "w", encoding="utf-8") as f:
        json.dump(workmap, f, indent=2)
    return workmap_path


def provision_workmap_agents(workmap, master_agent_id):
    """
    Auto-create any agents referenced in the workmap that don't yet exist.
    Registers them in agents.json, generates their directory structure,
    connects them to the master, and positions them on the canvas.
    """
    from interpreter import load_data, save_data, generate_agent_structure

    agents = load_data()
    if agents is None:
        agents = []
    existing_ids = {a["id"] for a in agents}

    # Find the master agent for positioning and connection
    master = next((a for a in agents if a["id"] == master_agent_id), None)
    master_x = master.get("x", 0) if master else 0
    master_y = master.get("y", 0) if master else 0

    nodes = workmap.get("nodes", [])
    referenced_agents = set()
    for node in nodes:
        agent = node.get("agent", "")
        if agent and agent not in ("self", "", master_agent_id):
            referenced_agents.add(agent)

    created = []
    offset = 0
    for agent_id in referenced_agents:
        if agent_id in existing_ids:
            continue

        # Derive a human-readable name from the ID (e.g. "agent-energy-001" → "Energy")
        parts = agent_id.replace("agent-", "").split("-")
        name_part = parts[0] if parts else agent_id
        display_name = name_part.replace("_", " ").title()

        # Find the task description from the first node using this agent
        task_hint = ""
        for node in nodes:
            if node.get("agent") == agent_id:
                task_hint = node.get("task", "")[:120]
                break

        # Position in a fan below the master
        offset += 1
        new_x = master_x + (offset * 320) - 320
        new_y = master_y + 280

        # Create a subfolder inside the master's workingDir for this agent
        master_work_dir = (master.get("workingDir", "") if master else "") or ""
        if master_work_dir:
            agent_work_dir = os.path.join(master_work_dir, agent_id)
            os.makedirs(agent_work_dir, exist_ok=True)
            safe_log(f"    [PROVISION] Created work directory: {agent_work_dir}")
        else:
            agent_work_dir = ""

        new_agent = {
            "id": agent_id,
            "name": display_name,
            "description": task_hint or f"Worker agent for {display_name} tasks",
            "brain": master.get("brain", "") if master else "",
            "channel": "Gmail",
            "workingDir": agent_work_dir,
            "permissions": ["web search", "file access"],
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
        safe_log(f"+++ [PROVISION] Auto-created agent '{display_name}' (ID: {agent_id})")

    if created:
        # Connect master → new agents
        if master:
            existing_conns = master.get("connections", [])
            master["connections"] = existing_conns + created
        save_data(agents)
        safe_log(f"[PROVISION] {len(created)} agents provisioned and connected to {master_agent_id}")

    return created


async def execute_next_node(agent_id, api_key, provider):
    """
    Tick engine entry point: reads workmap.json, finds the next eligible PENDING node
    (all dependencies COMPLETED), marks it IN_PROGRESS, runs it, and saves the result.

    Returns: "done" | "in_progress" | "blocked" | "paused" | "no_workmap"

    IMPORTANT: IN_PROGRESS is written to disk before any await so the tick thread's
    double-dispatch guard (which reads the file) works correctly.
    """
    workmap_path = os.path.join(AGENTS_CODE_DIR, agent_id, "workmap.json")
    if not os.path.exists(workmap_path):
        return "no_workmap"

    with open(workmap_path, "r", encoding="utf-8") as f:
        workmap = json.load(f)

    if workmap.get("status") != "RUNNING":
        return "paused"

    nodes = workmap.get("nodes", [])
    completed_ids = {n["id"] for n in nodes if n["status"] == "COMPLETED"}

    # Find first PENDING node whose dependencies are all COMPLETED
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

    # Mark IN_PROGRESS synchronously (before any await) so the tick guard sees it
    next_node["status"] = "IN_PROGRESS"
    with open(workmap_path, "w", encoding="utf-8") as f:
        json.dump(workmap, f, indent=2)

    # Reconstruct accumulated context from completed nodes' summaries
    accumulated_context = "\n".join(
        f"### {n['task'][:60]}\n{n['result_summary']}"
        for n in nodes
        if n["status"] == "COMPLETED" and n.get("result_summary")
    )

    step_num = next((i + 1 for i, n in enumerate(nodes) if n["id"] == next_node["id"]), 1)
    total = len(nodes)
    target_agent = next_node.get("agent", agent_id)
    # If agent is "self" or the master itself, use agent_id
    if target_agent in ("self", "", None):
        target_agent = agent_id

    PDF_KEYWORDS = ["report_generation", "pdf", "create a pdf", "generate a pdf", "final report"]
    is_pdf = any(w in next_node["task"].lower() for w in PDF_KEYWORDS)
    session_id = workmap.get("project_id", f"wm_{int(time.time())}")

    safe_log(f"[TICK] {agent_id}: Executing node {next_node['id']} — {next_node['task'][:60]}")

    result = await execute_step(
        step_num, total,
        next_node["task"],
        target_agent,
        accumulated_context,
        api_key, provider,
        is_pdf_step=is_pdf,
        session_id=session_id
    )

    # Reload workmap to avoid overwriting concurrent changes
    with open(workmap_path, "r", encoding="utf-8") as f:
        workmap = json.load(f)

    # Find and update the node
    for node in workmap.get("nodes", []):
        if node["id"] == next_node["id"]:
            node["status"] = "ERROR" if str(result).startswith("Step failed") else "COMPLETED"
            node["result_summary"] = str(result)[:300]
            break

    # Check if all nodes are now done
    all_done = all(n["status"] in ("COMPLETED", "ERROR") for n in workmap.get("nodes", []))
    if all_done:
        workmap["status"] = "COMPLETED"

    with open(workmap_path, "w", encoding="utf-8") as f:
        json.dump(workmap, f, indent=2)

    return "in_progress"


def _clear_internal_history(agent_id):
    """
    Wipe the agent's internal history before each autonomous step.
    This prevents accumulated tool calls and partial results from confusing
    the LLM mid-plan and triggering unnecessary capability checks.
    """
    internal_path = os.path.join(AGENTS_CODE_DIR, agent_id, "internal_history.json")
    try:
        with open(internal_path, "w", encoding="utf-8") as f:
            import json
            json.dump([], f)
    except Exception:
        pass


async def execute_step(step_num, total_steps, step_text, agent_id, accumulated_context, api_key, provider, is_pdf_step=False, session_id=None):
    """
    Execute a single plan step by calling /chat.
    The [AUTO_STEP] prefix tells server.py to filter this from the user-facing UI history.

    is_pdf_step=True: gives explicit PDF generation instructions (no thinking/searching needed).
    """
    safe_log(f"[STATUS:{agent_id}] Step {step_num}/{total_steps}: {step_text[:60]}")

    # Clear accumulated internal history so each step starts with a clean context.
    # Without this, by step 3 the LLM sees a huge history of previous tool calls
    # and starts asking for capabilities it "thinks" it needs to process it all.
    _clear_internal_history(agent_id)

    # Truncate accumulated context so we don't blow up the LLM context window
    ctx = accumulated_context.strip()
    if len(ctx) > 12000:
        ctx = ctx[:12000] + "\n\n[... earlier context truncated for length ...]"

    ctx_section = f"\n\nGATHERED RESEARCH SO FAR:\n{ctx}" if ctx else ""

    if is_pdf_step:
        # Hard-code the PDF generation instruction.
        # The PDF step MUST read from the Blackboard first to get full structured data.
        message = (
            f"[AUTO_STEP {step_num}/{total_steps}] AUTONOMOUS EXECUTION MODE — PDF GENERATION.\n\n"
            f"All research is complete and stored in the Belief Base. Your ONLY job now is:\n"
            f"1. First: call [TOOL: read_beliefs({step_text})] to retrieve ALL gathered research.\n"
            f"2. Then: call [TOOL: report_generation(topic|context)] using that belief data as the context.\n"
            f"Do NOT use thinking, web_search, or generate_report. Use ONLY read_beliefs then report_generation.\n"
            f"Do NOT skip step 1. The belief base contains raw verified data you MUST use.\n\n"
            f"ORIGINAL TASK: {step_text}\n"
        )
    else:
        message = (
            f"[AUTO_STEP {step_num}/{total_steps}] AUTONOMOUS EXECUTION MODE — EXTRACTION PHASE.\n"
            f"Execute ONLY this specific research step. Return the result to the plan runner.\n\n"
            f"STEP: {step_text}\n"
            f"{ctx_section}\n\n"
            f"## EXTRACTION MODE RULES (MANDATORY):\n"
            f"1. Do NOT summarize findings. Store the VERBATIM text from each source.\n"
            f"2. For EVERY fact found, make a SEPARATE [TOOL: post_finding(verbatim text. Source: URL)] call.\n"
            f"3. Include the EXACT source URL in every post_finding call.\n"
            f"4. After storing all facts, write a brief 2-3 line summary for the plan runner to track progress.\n"
            f"5. You are FORBIDDEN from synthesizing or drawing conclusions. Just extract and store raw facts."
        )

    try:
        from interpreter import execute_agent_turn
        
        full_text = ""
        # The agent_turn generator yields SSE-formatted strings. We parse them live.
        # We append session_id to the message for brf to pick up if needed, 
        # or pass it as a separate context if we update execute_agent_turn signature.
        # For now, let's keep it simple: pass session_id in the message metadata tag.
        tagged_message = f"{message}\n[SESSION_ID: {session_id}]"
        
        async for line in execute_agent_turn(agent_id, tagged_message, api_key, provider):
            line = line.strip()
            if not line: continue
            if line.startswith("data: "):
                content = line[6:]
                if content == "[DONE]": break
                try:
                    data = json.loads(content)
                    if data.get("type") == "text":
                        full_text += data.get("content", "")
                    elif data.get("type") == "error":
                        safe_log(f"!!! [PLAN_RUNNER] Internal Error: {data.get('content')}")
                        return f"Step failed: {data.get('content')}"
                except: pass
        
        safe_log(f"[STATUS:{agent_id}] Step {step_num} complete")
        return full_text

    except Exception as e:
        safe_log(f"!!! [PLAN_RUNNER] Step {step_num} error: {e}")
        return f"Step failed: {str(e)}"


async def run_autonomous(agent_id, task, api_key, provider, agents_info="", autonomous=False):
    """
    Phase 1: Generate the intentions (plan.json) AND the DAG workmap (workmap.json).
    autonomous=True: skips the ask_user check-in step (used for master agents).
    Returns the step list for backward-compatible UI rendering.
    """
    safe_log(f"[STATUS:{agent_id}] Autonomous deliberation complete: Plan generated")

    # Generate flat step list for plan.json (used by worker agents and UI display)
    steps = await generate_plan(task, agent_id, api_key, provider, agents_info, autonomous=autonomous)
    if steps:
        save_plan_json(steps, task, agent_id)

    # Generate DAG workmap for master tick engine (runs in parallel with plan generation)
    try:
        workmap = await generate_workmap(task, agent_id, api_key, provider, agents_info)
        # Auto-create any agents referenced in the workmap that don't exist yet
        provision_workmap_agents(workmap, agent_id)
        save_workmap_json(workmap, agent_id)
        safe_log(f"[STATUS:{agent_id}] Workmap saved — {len(workmap['nodes'])} nodes, status: PAUSED")
    except Exception as e:
        safe_log(f"!!! [WORKMAP] Failed to generate workmap: {e}")

    return steps


async def run_execution_loop(agent_id, task, api_key, provider):
    """
    Phase 2: Trigger execution.

    If a workmap.json exists for this agent, set its status to RUNNING and return
    immediately — the background tick engine (execution_engine_tick in interpreter.py)
    will process nodes one at a time via execute_next_node().

    Falls back to the legacy linear loop (_run_linear_execution_loop) for agents
    that don't have a workmap (worker agents receiving ad-hoc tasks via message_agent).
    """
    workmap_path = os.path.join(AGENTS_CODE_DIR, agent_id, "workmap.json")

    if os.path.exists(workmap_path):
        # DAG path: hand off to tick engine
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
            # Fall through to linear loop on error

    # Legacy linear path (no workmap, or workmap activation failed)
    return await _run_linear_execution_loop(agent_id, task, api_key, provider)


async def _run_linear_execution_loop(agent_id, task, api_key, provider):
    """
    Original blocking step-by-step execution loop.
    Used for worker agents and as a fallback when no workmap.json exists.
    """
    safe_log(f"[STATUS:{agent_id}] Autonomous execution loop started (linear mode)")

    # CLEAR VOLATILE LEDGER: Start with a fresh slate
    import brf
    brf.clear_volatile_beliefs()
    safe_log(f"--- [CLEANUP] Volatile ledger (base_facts) cleared for new task.")

    session_id = f"sess_{int(time.time())}"
    safe_log(f"--- [BDI] Session initialized: {session_id}")

    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_id)
    plan_path = os.path.join(agent_dir, "plan.json")

    steps = []
    if os.path.exists(plan_path):
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                steps = data.get("steps", [])
                task = data.get("objective", task)
        except Exception as e:
            safe_log(f"!!! [PLAN_RUNNER] Error reading plan.json: {e}")

    if not steps:
        return "Failed to locate an execution plan. Please try generating the plan again."

    accumulated_context = ""
    step_results = []

    PDF_KEYWORDS = ["report_generation", "pdf", "create a pdf", "generate a pdf"]
    last_step_lower = steps[-1].lower()
    last_is_pdf = any(w in last_step_lower for w in PDF_KEYWORDS)

    for i, step in enumerate(steps, 1):
        # Closed-loop commitment check every 3 steps
        if i > 1 and i % 3 == 0:
            import deliberator
            from interpreter import get_beliefs_context
            beliefs_ctx = get_beliefs_context()

            history = []
            history_path = os.path.join(agent_dir, "history.json")
            if os.path.exists(history_path):
                try:
                    with open(history_path, "r", encoding="utf-8") as f:
                        history = json.load(f)
                except: pass

            decision, reason = await deliberator.deliberate(
                agent_id, f"Ongoing task: {task}. Next step: {step}",
                api_key, provider, beliefs_ctx, history=history
            )

            if decision == "RE-PLAN":
                safe_log(f"!!! [PIVOT] Deliberator signals RE-PLAN: {reason}")
                new_steps = await run_autonomous(agent_id, task, api_key, provider)
                if new_steps:
                    return await _run_linear_execution_loop(agent_id, task, api_key, provider)
                else:
                    return f"Pivot failed: Could not generate new intentions. Reason: {reason}"

        is_last = (i == len(steps))
        is_pdf = is_last and last_is_pdf

        result = await execute_step(
            i, len(steps), step, agent_id,
            accumulated_context, api_key, provider,
            is_pdf_step=is_pdf, session_id=session_id
        )

        if "HALT_AND_ASK|" in str(result):
            question = result.split("HALT_AND_ASK|")[-1].strip()
            safe_log(f"[STATUS:{agent_id}] Autonomous loop paused by agent. Waiting for user.")
            if os.path.exists(plan_path):
                try: os.remove(plan_path)
                except: pass
            return (
                f"### Pausing for Your Direction\n\n**Agent asks:** {question}\n\n"
                f"*(Reply to this message to steer the agent and it will generate a new plan based on your feedback.)*"
            )

        step_results.append((step, result))
        if not is_pdf:
            accumulated_context += f"\n### Step {i}: {step}\n{result}\n"

    if last_is_pdf:
        final_response = step_results[-1][1]
    else:
        safe_log(f"[STATUS:{agent_id}] No PDF step in plan — adding PDF generation...")
        result = await execute_step(
            len(steps) + 1, len(steps) + 1,
            f"Create a PDF report for: {task}",
            agent_id, accumulated_context, api_key, provider,
            is_pdf_step=True, session_id=session_id
        )
        final_response = result

    safe_log(f"[STATUS:{agent_id}] Autonomous task complete")
    return final_response
