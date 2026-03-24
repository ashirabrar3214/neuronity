"""
ReAct-style iterative agent graph.

Graph structure:
  [START] -> build_context -> plan -> {decision}
                                       DONE/ASK_USER -> respond -> END
                                       CONTINUE      -> execute -> compress -> {cap?}
                                                                                cap hit -> respond -> END
                                                                                continue -> plan (loop)

Models:
  Planner  : gemini-3.1-pro-preview  (structured 3-step JSON planning)
  Executor : gemini-2.0-flash        (tool calls + internal reasoning)
  Compressor: gemini-2.0-flash       (~100-token iteration summaries)
"""
import os
import json
import datetime
import asyncio

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END

from graph.state import AgentState
from graph.llm import get_llm
from graph.tool_definitions import get_tools_for_agent
from graph.checkpointer import get_checkpointer


AGENTS_CODE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents_code")


# ---------------------------------------------------------------------------
# build_context — preserved from original + ReAct state init
# ---------------------------------------------------------------------------

async def build_context(state: AgentState) -> dict:
    """Assemble the system prompt from agent identity, tools, connected agents, and date."""
    agent_id = state["agent_id"]
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_id)
    mode_label = "training" if state.get("mode") == "training" else ("master" if state.get("agent_type") == "master" else "work")
    print(f">>> [BUILD_CTX] agent={agent_id} mode={mode_label} permissions={state.get('permissions')}", flush=True)

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
    has_working_dir = bool(state.get("working_dir", ""))

    tools = get_tools_for_agent(permissions, len(connected_agents) > 0, is_training, is_master, has_working_dir)
    tool_manifest = "\n".join([f"- {t.name}: {t.description}" for t in tools])
    print(f"+++ [BUILD_CTX] agent={state['agent_id']} tools={len(tools)} connected={len(connected_agents)} prompt_will_be_len~{len(tool_manifest)+200}", flush=True)

    connected_str = "\n".join([
        f"- {a['name']} (ID: {a['id']}): {a.get('responsibility', '')}"
        for a in connected_agents
    ]) or "None"

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
                "You are a Master Coordinator. You PLAN and DELEGATE — you never do the work yourself.\n\n"
                "## MANDATORY PHASE 1 — CLARIFY BEFORE ANYTHING ELSE\n"
                "For ANY non-trivial goal (research, reports, analysis, current events, plans):\n"
                "  - Ask 2-3 TARGETED questions about scope, format, depth, time period, audience\n"
                "  - Use decision='ASK_USER' with a numbered list of questions in the 'question' field\n"
                "  - NEVER skip this phase. NEVER assume the user's full intent.\n"
                "  - Example questions: 'What time period?', 'What format/length?', 'Any specific focus?'\n\n"
                "## PHASE 2 — PLAN 6-8 SPECIFIC MICROTASKS (after clarification)\n"
                "  - Each web_search must have a SPECIFIC, distinct query — not generic\n"
                "  - Plan enough searches to cover all dimensions of the topic\n"
                "  - report_generation comes LAST, only after ALL research steps complete\n\n"
                "## ABSOLUTE RULES\n"
                "  - NEVER answer from memory for any current event, news, or fact after 2024\n"
                "  - ALWAYS web_search before any report or analysis on recent/current topics\n"
                "  - NEVER call report_generation more than ONCE per task\n"
                "  - NEVER produce a report with fluff — only include verified, searched facts\n"
                "  - If web_search returns no results, try a DIFFERENT, more specific query\n"
            )

    # Extract goal from last HumanMessage
    goal = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            goal = msg.content
            break

    return {
        "system_prompt": system_prompt,
        "current_prompt_md": current_agent_prompt,
        # Initialize ReAct loop state
        "goal": goal,
        "plan_iterations": 0,
        "max_plan_iterations": 50,
        "current_steps": [],
        "iteration_summaries": [],
        "planner_decision": "",
        "consecutive_clarifications": 0,
        "planner_response": "",
        "planner_question": "",
    }


# ---------------------------------------------------------------------------
# Planner helpers
# ---------------------------------------------------------------------------

def _normalize_steps(steps: list) -> list:
    """Normalize 1-7 steps with all required fields. No filler padding."""
    normalized = []
    for i, s in enumerate(steps[:7]):
        normalized.append({
            "id": i + 1,
            "description": s.get("description", f"Step {i + 1}"),
            "type": s.get("type", "think"),
            "tool_name": s.get("tool_name"),
            "tool_args": s.get("tool_args") or {},
            "confidence": int(s.get("confidence", 100)),
            "clarification_question": s.get("clarification_question", ""),
            "result": None,
        })
    if not normalized:
        normalized.append({
            "id": 1,
            "description": "No steps returned by planner",
            "type": "think",
            "tool_name": None,
            "tool_args": {},
            "confidence": 100,
            "clarification_question": "",
            "result": None,
        })
    return normalized


def _build_initial_planner_prompt(state: AgentState, tool_names: list) -> str:
    goal = state["goal"]
    permissions = state["permissions"]
    capabilities_str = ", ".join(permissions) if permissions else "none"

    return f"""You are a planning module for an AI agent.

GOAL: {goal}

AGENT CAPABILITIES: {capabilities_str}
AVAILABLE TOOLS: {", ".join(tool_names)}

Plan the first 3 steps to work toward the goal. Consider:
- What context or information is missing?
- Should you search the web, read files, or reason internally first?
- Only use "ask" type if user input is absolutely essential right now.

Return ONLY a valid JSON object:
{{
  "steps": [
    {{"id": 1, "description": "...", "type": "tool", "tool_name": "web_search", "tool_args": {{"query": "..."}}}},
    {{"id": 2, "description": "...", "type": "think"}},
    {{"id": 3, "description": "...", "type": "think"}}
  ],
  "decision": "CONTINUE",
  "response": "",
  "question": ""
}}

RULES:
- Always output EXACTLY 3 steps.
- "type" must be "tool", "think", or "ask".
- For "tool" steps include "tool_name" and "tool_args".
- "decision" = "DONE" only if goal is fully achievable from what you already know — include full "response".
- "decision" = "ASK_USER" only if critical user input is required — include "question".
- Otherwise "decision" = "CONTINUE".
- Return ONLY the JSON. No markdown fences, no explanation.
"""


def _build_refeed_planner_prompt(state: AgentState, tool_names: list) -> str:
    goal = state["goal"]
    iteration_summaries = state["iteration_summaries"]
    current_steps = state["current_steps"]

    last_summaries = iteration_summaries[-3:]
    summaries_str = "\n".join(last_summaries) if last_summaries else "No context gathered yet."

    step_lines = []
    for s in current_steps:
        result_preview = str(s.get("result") or "no result")[:120]
        step_lines.append(f"- Step {s['id']} ({s['type']}): {s['description']} → {result_preview}")
    steps_str = "\n".join(step_lines) if step_lines else "No steps executed yet."

    return f"""You are a planning module for an AI agent continuing toward a goal.

GOAL: {goal}

CONTEXT GATHERED SO FAR:
{summaries_str}

LAST 3 STEPS TAKEN:
{steps_str}

AVAILABLE TOOLS: {", ".join(tool_names)}

Plan the next 3 steps, OR decide DONE/ASK_USER.

Return ONLY a valid JSON object:
{{
  "steps": [
    {{"id": 1, "description": "...", "type": "tool"|"think"|"ask", "tool_name": "...", "tool_args": {{...}}}},
    {{"id": 2, "description": "...", "type": "think"}},
    {{"id": 3, "description": "...", "type": "think"}}
  ],
  "decision": "CONTINUE"|"ASK_USER"|"DONE",
  "response": "Full answer here if DONE",
  "question": "Question for user if ASK_USER"
}}

RULES:
- Always output EXACTLY 3 steps.
- "decision" = "DONE" when goal is fully achieved — write complete answer in "response".
- "decision" = "ASK_USER" only when user input is strictly required — write question in "question".
- Otherwise "CONTINUE".
- Return ONLY the JSON. No markdown fences, no explanation.
"""


# ---------------------------------------------------------------------------
# Graph Nodes
# ---------------------------------------------------------------------------

async def plan(state: AgentState) -> dict:
    """PLANNER NODE: gemini-3.1-pro-preview decides next 3 steps."""
    plan_iterations = state["plan_iterations"]
    print(f">>> [PLAN_NODE] agent={state['agent_id']} plan_iter={plan_iterations} goal={state['goal'][:60]!r}", flush=True)
    permissions = state["permissions"]
    connected_agents = state["connected_agents"]
    is_master = state["agent_type"] == "master"
    is_training = state["mode"] == "training"
    has_working_dir = bool(state.get("working_dir", ""))

    tools = get_tools_for_agent(permissions, len(connected_agents) > 0, is_training, is_master, has_working_dir)
    tool_names = [t.name for t in tools]

    prompt = (
        _build_initial_planner_prompt(state, tool_names)
        if plan_iterations == 0
        else _build_refeed_planner_prompt(state, tool_names)
    )

    try:
        # --- THE BEST SOLUTION: CONCURRENT STATUS STREAMING ---
        async def generate_plan_with_loading():
            agent_id = state["agent_id"]

            # Task 1: The "Claude-like" changing loading messages
            async def loading_sequence():
                messages = [
                    "Thinking...",
                    "Hold on...",
                    "Lemme think...",
                    "Interesting...",
                    "Almost there...",
                    "Cooking...",
                    "Rizzing...",
                    "This is a good one...",
                ]
                try:
                    for msg in messages:
                        print(f"[STATUS:{agent_id}] {msg}", flush=True)
                        await asyncio.sleep(2.5)
                except asyncio.CancelledError:
                    pass

            # Task 2: The actual heavy LLM call
            llm = get_llm("planner", state["api_key"])

            # Run both concurrently
            loading_task = asyncio.create_task(loading_sequence())
            result = await llm.ainvoke([HumanMessage(content=prompt)])

            # Kill the loading sequence the exact millisecond the LLM finishes
            loading_task.cancel()
            print(f"[STATUS:{agent_id}] Strategy finalized.", flush=True)

            return result.content.strip()

        # Execute the concurrent wrapper
        text = await generate_plan_with_loading()
        # ------------------------------------------------------

        # Continue with existing parsing logic...
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].strip()

        parsed = json.loads(text)
        steps = _normalize_steps(parsed.get("steps", []))
        decision = parsed.get("decision", "CONTINUE")
        planner_response = parsed.get("response") or ""
        planner_question = parsed.get("question") or ""
        print(f"+++ [PLAN_NODE] decision={decision} steps={len(steps)}", flush=True)

        new_consecutive = (
            state["consecutive_clarifications"] + 1
            if decision == "ASK_USER"
            else 0
        )

        return {
            "current_steps": steps,
            "planner_decision": decision,
            "planner_response": planner_response,
            "planner_question": planner_question,
            "plan_iterations": plan_iterations + 1,
            "consecutive_clarifications": new_consecutive,
        }

    except Exception as e:
        print(f"!!! [PLAN_NODE] Error: {e} — falling back to think steps", flush=True)
        fallback = _normalize_steps([
            {"id": 1, "description": f"Review the goal: {state['goal'][:60]}", "type": "think"},
            {"id": 2, "description": "Check what context is already available", "type": "think"},
            {"id": 3, "description": "Summarize what is known so far", "type": "think"},
        ])
        return {
            "current_steps": fallback,
            "planner_decision": "CONTINUE",
            "planner_response": "",
            "planner_question": "",
            "plan_iterations": plan_iterations + 1,
            "consecutive_clarifications": state["consecutive_clarifications"],
        }


async def execute(state: AgentState) -> dict:
    """EXECUTOR NODE: gemini-2.0-flash runs each of the 3 planned steps."""
    import toolkit as tk

    agent_id = state["agent_id"]
    print(f">>> [EXEC_NODE] agent={agent_id} steps_to_run={len(state.get('current_steps', []))}", flush=True)
    api_key = state["api_key"]
    working_dir = state["working_dir"]
    agent_name = state["agent_name"]
    connected_agents = state["connected_agents"]

    permissions = state["permissions"]
    is_master = state["agent_type"] == "master"
    is_training = state["mode"] == "training"
    has_working_dir = bool(working_dir)
    tools_list = get_tools_for_agent(permissions, len(connected_agents) > 0, is_training, is_master, has_working_dir)
    allowed_tool_names = {t.name for t in tools_list}

    executor_llm = get_llm("fast", api_key, streaming=False)
    steps = [dict(s) for s in state["current_steps"]]

    for step in steps:
        step_type = step.get("type", "think")
        print(f"    [EXEC_NODE] step {step['id']} type={step_type} tool={step.get('tool_name','none')}", flush=True)

        # ── TOOL step ──────────────────────────────────────────────────
        if step_type == "tool":
            tool_name = step.get("tool_name")
            tool_args = step.get("tool_args") or {}

            if not tool_name or tool_name not in allowed_tool_names:
                print(f"!!! [EXEC_NODE] step {step['id']} tool={tool_name!r} NOT in permissions={list(allowed_tool_names)}", flush=True)
                step["result"] = f"Tool '{tool_name}' not available with current permissions."
                continue

            try:
                if tool_name == "web_search":
                    step["result"] = await tk.web_search(
                        tool_args.get("query", ""), agent_id, api_key
                    )

                elif tool_name == "deep_search":
                    step["result"] = await tk.deep_search(
                        tool_args.get("query", ""), agent_id, api_key
                    )

                elif tool_name == "list_workspace":
                    # Inline implementation (same logic as tool_definitions.py)
                    if not working_dir or not os.path.exists(working_dir):
                        step["result"] = "Error: Working directory is invalid or not set."
                    else:
                        lines = []
                        count = 0
                        for root, dirs, files in os.walk(working_dir):
                            if count > 1000:
                                break
                            rel = os.path.relpath(root, working_dir)
                            lines.append(f"Directory: {rel if rel != '.' else '(Root)'}")
                            for d in sorted(dirs):
                                lines.append(f"  [DIR]  {d}")
                            for fname in sorted(files):
                                lines.append(f"  [FILE] {fname}")
                            lines.append("")
                            count += len(files)
                        step["result"] = "Workspace Directory Map:\n" + "\n".join(lines)

                elif tool_name == "scout_file":
                    step["result"] = await asyncio.to_thread(
                        tk.scout_file, agent_id, tool_args.get("path", ""), working_dir
                    )

                elif tool_name == "read_file":
                    path = tool_args.get("path", "")
                    line_range = tool_args.get("range", "")
                    input_str = f"{path}|{line_range}" if line_range else path
                    step["result"] = await asyncio.to_thread(
                        tk.read_file, agent_id, input_str, working_dir
                    )

                elif tool_name == "write_file":
                    path = tool_args.get("path", "")
                    content = tool_args.get("content", "")
                    input_str = f"{path}|{content}"
                    step["result"] = await asyncio.to_thread(
                        tk.write_file, agent_id, input_str, working_dir
                    )

                elif tool_name == "update_plan":
                    objective = tool_args.get("objective", "")
                    steps_list = tool_args.get("steps", [])
                    if isinstance(steps_list, list):
                        steps_str = ", ".join(steps_list)
                    else:
                        steps_str = str(steps_list)
                    input_str = f"{objective}|{steps_str}"
                    step["result"] = await tk.update_plan(agent_id, input_str)

                elif tool_name == "ask_user":
                    question = tool_args.get("question", "I have a question.")
                    step["result"] = await tk.ask_user(agent_id, question)

                elif tool_name == "generate_report":
                    title = tool_args.get("title", "Report")
                    content = tool_args.get("content", "")
                    input_str = f"{title}|{content}"
                    step["result"] = await tk.generate_report(agent_id, input_str, working_dir)

                elif tool_name == "report_generation":
                    topic = tool_args.get("topic", "")
                    context = tool_args.get("context", "")
                    input_str = f"{topic}|{context}"
                    step["result"] = await tk.report_generation(
                        agent_id, input_str, working_dir, api_key, agent_name
                    )

                elif tool_name == "message_agent":
                    target_id = tool_args.get("target_agent_id", "")
                    message = tool_args.get("message", "")
                    # Look up provider from connected agents
                    target_provider = "gemini"
                    for ca in connected_agents:
                        if ca.get("id") == target_id:
                            target_provider = ca.get("provider", "gemini")
                            break
                    step["result"] = await tk.message_agent(
                        target_id, message, agent_id, agent_name, api_key, target_provider
                    )

                else:
                    step["result"] = f"Tool '{tool_name}' not handled in executor."

                # Truncate long results for storage
                if isinstance(step["result"], str) and len(step["result"]) > 800:
                    step["result"] = step["result"][:800] + "...[truncated]"
                print(f"+++ [EXEC_NODE] step {step['id']} result_len={len(str(step['result']))}", flush=True)

            except Exception as e:
                print(f"!!! [EXEC_NODE] step {step['id']} tool={tool_name!r} error: {e}", flush=True)
                step["result"] = f"Error running {tool_name}: {str(e)[:200]}"

        # ── THINK step ─────────────────────────────────────────────────
        elif step_type == "think":
            summaries = state["iteration_summaries"]
            context_str = "\n".join(summaries[-2:]) if summaries else "No prior context."
            think_prompt = (
                f"Goal: {state['goal']}\n\n"
                f"Prior context:\n{context_str}\n\n"
                f"Think briefly about: {step['description']}\n\n"
                f"Respond in 1-2 sentences. Be specific and factual."
            )
            try:
                r = await executor_llm.ainvoke([HumanMessage(content=think_prompt)])
                step["result"] = r.content.strip()[:400]
            except Exception as e:
                step["result"] = f"Think error: {str(e)[:100]}"

        # ── ASK step ───────────────────────────────────────────────────
        elif step_type == "ask":
            step["result"] = step["description"]

    return {"current_steps": steps}


async def compress(state: AgentState) -> dict:
    """COMPRESSOR NODE: gemini-2.0-flash summarizes iteration results to ~100 tokens."""
    steps = state["current_steps"]
    goal = state["goal"]
    iteration_num = state["plan_iterations"]
    print(f">>> [COMPRESS_NODE] iteration={iteration_num} steps={len(steps)}", flush=True)

    step_details = "\n".join([
        f"Step {s['id']} ({s['type']}): {s['description']} → {str(s.get('result') or 'no result')[:200]}"
        for s in steps
    ])

    compress_prompt = (
        f"Summarize the following 3 steps and results in at most 100 tokens.\n"
        f"Be specific about what was found or concluded. Focus on facts, not process.\n\n"
        f"GOAL CONTEXT: {goal[:100]}\n\n"
        f"STEPS:\n{step_details}\n\n"
        f"Return ONLY the summary string. No headers, no JSON."
    )

    try:
        llm = get_llm("fast", state["api_key"], streaming=False)
        result = await llm.ainvoke([HumanMessage(content=compress_prompt)])
        summary = result.content.strip()[:600]
        print(f"+++ [COMPRESS_NODE] summary_len={len(summary)} preview={summary[:60]!r}", flush=True)
    except Exception as e:
        print(f"!!! [COMPRESS_NODE] error: {e}", flush=True)
        summary = (
            f"Iteration {iteration_num}: "
            + "; ".join([
                f"{s['description'][:40]}={str(s.get('result', ''))[:60]}"
                for s in steps
            ])
        )

    new_summaries = list(state["iteration_summaries"]) + [summary]
    return {"iteration_summaries": new_summaries}


async def respond(state: AgentState) -> dict:
    """Terminal node — formats the final AIMessage."""
    decision = state["planner_decision"]
    print(f">>> [RESPOND_NODE] decision={decision}", flush=True)

    if decision == "DONE":
        content = state["planner_response"] or "Task complete."
        print(f"+++ [RESPOND_NODE] DONE response_len={len(content)}", flush=True)
        return {"messages": [AIMessage(content=content)]}

    elif decision == "ASK_USER":
        question = state["planner_question"] or "I have a question for you."
        print(f"+++ [RESPOND_NODE] ASK_USER question_len={len(question)}", flush=True)
        return {"messages": [AIMessage(content=question)]}

    else:
        # Force-terminated: max iterations or consecutive clarifications
        summaries = state["iteration_summaries"]
        if summaries:
            content = "Here is what I gathered:\n\n" + "\n\n".join(summaries[-3:])
        else:
            content = "I was unable to complete the task within the allowed iterations."
        print(f"+++ [RESPOND_NODE] FORCE_TERMINATE response_len={len(content)}", flush=True)
        return {"messages": [AIMessage(content=content)]}


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------

def after_plan(state: AgentState) -> str:
    if state["planner_decision"] in ("DONE", "ASK_USER"):
        return "respond"
    return "execute"


def after_compress(state: AgentState) -> str:
    if state["plan_iterations"] >= state["max_plan_iterations"]:
        return "respond"
    if state["consecutive_clarifications"] >= 3:
        return "respond"
    return "plan"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_agent_graph():
    """Compile the ReAct-style iterative agent graph."""
    graph = StateGraph(AgentState)

    graph.add_node("build_context", build_context)
    graph.add_node("plan", plan)
    graph.add_node("execute", execute)
    graph.add_node("compress", compress)
    graph.add_node("respond", respond)

    graph.add_edge(START, "build_context")
    graph.add_edge("build_context", "plan")
    graph.add_conditional_edges("plan", after_plan, ["execute", "respond"])
    graph.add_edge("execute", "compress")
    graph.add_conditional_edges("compress", after_compress, ["plan", "respond"])
    graph.add_edge("respond", END)

    return graph.compile(checkpointer=get_checkpointer())
