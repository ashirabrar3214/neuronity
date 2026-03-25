"""
Direct SSE generator — bypasses LangGraph astream_events entirely.

Training mode : gemini-2.0-flash  — simple streaming chat
Work mode     : gemini-3.1-pro-preview planner + gemini-2.0-flash executor/compressor
"""
import json
import os
import asyncio

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from graph.llm import get_llm
from graph.tool_definitions import get_tools_for_agent

AGENTS_CODE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents_code")

# Per-agent raw step results — used to pass full research data (with URLs)
# to report_generation instead of compressed summaries that lose citations
_completed_steps_ref: dict = {}


# ---------------------------------------------------------------------------
# Public entry point (called from interpreter.py — graph param ignored)
# ---------------------------------------------------------------------------

async def langgraph_to_sse(graph, input_state: dict, config: dict):
    """Main SSE entry point. Routes to training or work mode."""
    # Padding flush: exceeds HTTP buffer threshold so first real events arrive immediately
    yield ": " + " " * 2048 + "\n\n"
    await asyncio.sleep(0)

    from graph.agent_graph import build_context
    ctx = await build_context(input_state)
    state = {**input_state, **ctx}

    mode = state.get("mode")
    agent_id = state.get("agent_id")
    print(f">>> [SSE] agent={agent_id} mode={mode} goal={state.get('goal','')[:60]!r}", flush=True)
    print(f"    [SSE] routing to {'TRAINING' if mode == 'training' else 'WORK (HITL)'} stream", flush=True)

    try:
        if state.get("mode") == "training":
            async for chunk in _training_stream(state):
                yield chunk
        else:
            from graph.hitl_engine import hitl_loop
            async for chunk in hitl_loop(state):
                yield chunk
    except Exception as e:
        print(f"!!! [SSE] Unhandled error: {e}", flush=True)
        yield _sse({"type": "error", "content": str(e)})

    print(f"--- [SSE] agent={agent_id} stream complete", flush=True)
    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Training mode — gemini-2.0-flash, direct streaming
# ---------------------------------------------------------------------------

async def _training_stream(state: dict):
    """Simple streaming chat for training mode."""
    agent_id = state["agent_id"]
    api_key  = state["api_key"]

    # Load history for multi-turn context
    history_msgs = []
    history_path = os.path.join(AGENTS_CODE_DIR, agent_id, "history.json")
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
            for entry in history[-20:]:
                role = entry.get("role", "")
                content = entry.get("content", "")
                if role == "user":
                    history_msgs.append(HumanMessage(content=content))
                elif role == "assistant":
                    history_msgs.append(AIMessage(content=content))
        except Exception:
            pass

    llm = get_llm("fast", api_key, streaming=True)
    messages = [SystemMessage(content=state["system_prompt"])] + history_msgs + list(state["messages"])

    async for chunk in llm.astream(messages):
        if chunk.content:
            yield _sse({"type": "response", "content": chunk.content})


# ---------------------------------------------------------------------------
# Work mode — ReAct loop
# ---------------------------------------------------------------------------

async def _react_loop(state: dict):
    """
    Burst-and-halt research loop.

    Architecture:
      Stage 1 — Initial Blast: find first 10-20 sources (parallel searches)
      Stage 2 — Mandatory Initial Steering: always halt after first burst
      Stage 3 — Iterative Bursts: research N sources per burst, then halt

    The burst size N = ceil(total_sources / human_effort).
    High human effort (H=10) → frequent check-ins.
    Low human effort (H=1)  → long autonomous stretches.
    """
    import toolkit as tk

    goal             = state["goal"]
    api_key          = state["api_key"]
    agent_id         = state["agent_id"]
    permissions      = state["permissions"]
    connected_agents = state["connected_agents"]
    is_training      = False
    system_prompt    = state.get("system_prompt", "")

    # Research config from agent settings
    user_effort  = state.get("user_effort", 1)
    project_size = state.get("project_size", "small")
    research_cfg = tk.get_research_config(project_size, user_effort)

    total_sources  = research_cfg["total_sources"]
    burst_size     = research_cfg["burst_size"]
    human_effort   = research_cfg["human_effort"]

    print(f">>> [REACT] agent={agent_id} project_size={project_size} H={human_effort} "
          f"total_sources={total_sources} burst_size={burst_size}", flush=True)

    # Reset raw step storage for this agent session
    _completed_steps_ref[agent_id] = []

    # Load recent conversation history so planner has context
    history_context = ""
    history_path = os.path.join(AGENTS_CODE_DIR, agent_id, "history.json")
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
            parts = []
            for entry in history[-4:]:
                role = "User" if entry.get("role") == "user" else "Assistant"
                parts.append(f"{role}: {entry.get('content', '')[:300]}")
            history_context = "\n".join(parts)
        except Exception:
            pass

    agent_type = state["agent_type"]
    tools      = get_tools_for_agent(permissions, len(connected_agents) > 0, is_training, agent_type == "master")
    tool_names = [t.name for t in tools]

    summaries: list       = []   # compressed summaries of each executed step
    completed_steps: list = []   # all executed step dicts (for refeed context)
    max_steps             = research_cfg["thinking_steps"] + total_sources  # generous cap
    consecutive_fallbacks = 0
    consecutive_failures  = 0    # consecutive tool call failures

    # Burst tracking
    sources_in_current_burst = 0
    total_sources_found      = 0
    burst_number             = 0
    initial_blast_done       = False
    user_steer_history       = ""   # accumulated steering from the human
    INITIAL_BLAST_SIZE       = min(10, total_sources)  # Stage 1: always 10 sources first

    print(f">>> [REACT] agent={agent_id} type={agent_type} goal={goal[:60]!r} max_steps={max_steps}", flush=True)

    for step_num in range(max_steps):
        yield _sse({"type": "iteration_start", "content": str(step_num)})

        # ── BURST HALT CHECK ──────────────────────────────────────────────
        # Determine if we've hit a burst boundary and need to halt for steering
        should_halt = False

        if not initial_blast_done and sources_in_current_burst >= INITIAL_BLAST_SIZE:
            # Stage 2: Mandatory halt after initial blast
            should_halt = True
            initial_blast_done = True
            print(f"    [BURST] Stage 2: Initial blast complete ({sources_in_current_burst} sources). Mandatory halt.", flush=True)

        elif initial_blast_done and sources_in_current_burst >= burst_size:
            # Stage 3: Iterative burst boundary
            should_halt = True
            print(f"    [BURST] Stage 3: Burst {burst_number} complete ({sources_in_current_burst} sources). Halting for steering.", flush=True)

        if should_halt:
            burst_number += 1
            sources_in_current_burst = 0

            # Generate steering check using fast model
            ledger = json.dumps([
                {"desc": s.get("description", ""), "result": str(s.get("result", ""))[:200]}
                for s in completed_steps[-15:]  # last 15 steps for context
            ])

            yield _sse({"type": "thought", "content": "Analyzing findings and preparing checkpoint..."})
            steering_msg = await tk.generate_human_steering_check(
                ledger, user_steer_history, agent_id, api_key
            )

            # Emit the steering checkpoint as a HALT_AND_ASK
            progress_pct = min(100, int((total_sources_found / total_sources) * 100))
            halt_content = (
                f"**Research Progress: {total_sources_found}/{total_sources} sources ({progress_pct}%)**\n\n"
                f"{steering_msg}"
            )

            yield _sse({"type": "response", "content": halt_content})
            print(f"--- [BURST] HALT emitted. burst={burst_number} total_sources={total_sources_found}/{total_sources}", flush=True)
            return

        # ── Check if we've hit total source cap ───────────────────────────
        if total_sources_found >= total_sources:
            print(f"--- [REACT] Total source cap reached ({total_sources_found}/{total_sources}). Finishing.", flush=True)
            # Let the planner wrap up with a DONE decision
            # (fall through to planning with force_knowledge)

        # ── Plan: ask for the single best next step ───────────────────────
        plan = None
        async for ev_type, ev_data in _stream_planner(
            goal, summaries, completed_steps, tool_names, api_key,
            system_prompt=system_prompt,
            force_knowledge=(consecutive_failures >= 3) or (total_sources_found >= total_sources),
            history_context=history_context,
            steps_done=step_num,
        ):
            if ev_type == "token":
                yield _sse({"type": "thought_token", "content": ev_data})
            else:
                plan = ev_data

        steps    = plan["steps"]
        decision = plan["decision"]
        print(f"    [REACT] step {step_num+1} decision={decision} steps_returned={len(steps)}", flush=True)

        # ── Terminal decisions (always before fallback check) ─────────────
        if decision == "DONE":
            print(f"--- [REACT] DONE at step {step_num+1} response_len={len(plan.get('response') or '')}", flush=True)
            yield _sse({"type": "response", "content": plan.get("response") or "Task complete."})
            return

        if decision == "ASK_USER":
            print(f"--- [REACT] ASK_USER at step {step_num+1}", flush=True)
            yield _sse({"type": "response", "content": plan.get("question") or "I have a question."})
            return

        # ── Get the single step ───────────────────────────────────────────
        step = steps[0] if steps else None

        # ── Fallback detection — useless filler steps ─────────────────────
        _FILLER = ("review gathered context", "analyze previous results",
                   "synthesize information", "review findings", "consolidate data",
                   "process gathered information", "no steps returned")
        is_filler = not step or (
            step.get("type") == "think" and
            any(p in step.get("description", "").lower() for p in _FILLER)
        )
        if is_filler:
            consecutive_fallbacks += 1
            print(f"    [REACT] step {step_num+1} FILLER detected (consecutive={consecutive_fallbacks})", flush=True)
        else:
            consecutive_fallbacks = 0

        if consecutive_fallbacks >= 2:
            print(f"--- [REACT] FILLER ABORT after {consecutive_fallbacks} filler steps", flush=True)
            yield _sse({"type": "response", "content": "I wasn't able to gather useful information. Try rephrasing or providing more context."})
            return

        if not step:
            continue

        # ── Show thought label for this step ─────────────────────────────
        desc = step.get("description", "")
        yield _sse({"type": "thought", "content": desc[:80] + ("…" if len(desc) > 80 else "")})
        await asyncio.sleep(0.12)

        # ── Execute this single step ──────────────────────────────────────
        step_type = step.get("type", "think")
        tool_name = step.get("tool_name", "")
        tool_args = step.get("tool_args") or {}

        if step_type == "tool" and tool_name:
            # HITL confidence gate
            confidence = step.get("confidence", 100)
            if confidence < 85:
                question = step.get("clarification_question") or \
                    f"I'm not confident about '{desc}'. Can you clarify?"
                yield _sse({"type": "hitl_question", "content": question, "confidence": confidence})
                return

            arg_str = ""
            if tool_args:
                first = str(list(tool_args.values())[0])
                arg_str = f": {first[:40]}" + ("…" if len(first) > 40 else "")
            yield _sse({"type": "action", "content": f"{tool_name}{arg_str}"})
            await asyncio.sleep(0.05)

            result = await _run_tool(tool_name, tool_args, state, summaries)
            step["result"] = result
            preview = str(result)[:150] + ("…" if len(str(result)) > 150 else "")
            yield _sse({"type": "action_result", "content": preview})

            await asyncio.sleep(0.05)

            if _is_tool_failure(str(result)):
                consecutive_failures += 1
                print(f"    [REACT] step {step_num+1} TOOL FAILURE (consecutive={consecutive_failures}) tool={tool_name}", flush=True)
            else:
                consecutive_failures = 0
                # Track sources found for burst logic
                if tool_name in ("web_search", "scrape_website"):
                    if tool_name == "web_search":
                        # Each web_search returns ~7 results (source snippets)
                        result_str = str(result)
                        source_count = result_str.count("URL:")
                        sources_in_current_burst += max(1, source_count)
                        total_sources_found += max(1, source_count)
                    else:
                        # scrape_website = 1 deep source
                        sources_in_current_burst += 1
                        total_sources_found += 1
                    print(f"    [BURST] sources_in_burst={sources_in_current_burst} total={total_sources_found}/{total_sources}", flush=True)

        elif step_type == "think":
            yield _sse({"type": "action", "content": f"→ {desc[:60]}"})
            await asyncio.sleep(0.05)
            result = await _run_think(desc, goal, summaries, api_key)
            step["result"] = result

        elif step_type == "ask":
            step["result"] = desc

        # ── Compress this step and carry forward ──────────────────────────
        summary = await _compress(goal, [step], api_key, step_num)
        summaries.append(summary)
        completed_steps.append(step)
        _completed_steps_ref[agent_id].append(step)

    # Cap hit — surface what was gathered
    print(f"--- [REACT] CAP HIT at step {max_steps} — summaries={len(summaries)}", flush=True)
    content = (
        "Here is what I gathered:\n\n" + "\n\n".join(summaries[-5:])
        if summaries
        else "I was unable to complete the task within the allowed steps."
    )
    yield _sse({"type": "response", "content": content})


# ---------------------------------------------------------------------------
# Planner — gemini-3.1-pro-preview
# ---------------------------------------------------------------------------

_CLOSE_TAG = "</thinking>"

def _safe_thinking_len(inner: str) -> int:
    """Return how many chars of inner are safe to stream (exclude partial closing tag)."""
    if _CLOSE_TAG in inner:
        return inner.index(_CLOSE_TAG)
    for n in range(len(_CLOSE_TAG), 0, -1):
        if inner.endswith(_CLOSE_TAG[:n]):
            return len(inner) - n
    return len(inner)


async def _stream_planner(
    goal, summaries, prev_steps, tool_names, api_key,
    system_prompt: str = "",
    force_knowledge: bool = False,
    history_context: str = "",
    steps_done: int = 0,
):
    """
    Async generator. Streams <thinking>...</thinking> tokens to the caller,
    then yields ("result", dict) once the full response is parsed.
    Falls back from gemini-3.1-pro-preview to gemini-2.0-flash on error.
    """
    import re
    from graph.agent_graph import _normalize_steps

    prompt = (
        _initial_prompt(goal, tool_names, system_prompt, history_context, steps_done=steps_done) if not summaries
        else _refeed_prompt(goal, summaries, prev_steps, tool_names, system_prompt, force_knowledge, history_context, steps_done=steps_done)
    )

    for mode in ("planner", "fast"):
        full_text = ""
        thinking_shown = 0
        print(f">>> [PLANNER] trying mode={mode} summaries={len(summaries)} steps_done={steps_done}", flush=True)
        try:
            llm = get_llm(mode, api_key, streaming=True)
            async for chunk in llm.astream([HumanMessage(content=prompt)]):
                raw = chunk.content
                if isinstance(raw, list):
                    token = "".join(
                        p.get("text", "") if isinstance(p, dict) else str(p)
                        for p in raw
                    )
                else:
                    token = str(raw) if raw else ""
                if not token:
                    continue
                full_text += token

                # Stream only what's safely inside <thinking>...</thinking>
                # _safe_thinking_len guards against partial closing tags leaking through
                if _CLOSE_TAG not in full_text and "<thinking>" in full_text:
                    inner = full_text.split("<thinking>", 1)[1]
                    safe = _safe_thinking_len(inner)
                    if safe > thinking_shown:
                        yield ("token", inner[thinking_shown:safe])
                        thinking_shown = safe

            # Extract JSON from after </thinking>
            if "</thinking>" in full_text:
                json_str = full_text.split("</thinking>", 1)[1].strip()
            else:
                json_str = full_text.strip()

            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].strip()

            json_str = re.sub(r",\s*([}\]])", r"\1", json_str)

            parsed   = json.loads(json_str)
            steps    = _normalize_steps(parsed.get("steps", []))
            decision = parsed.get("decision", "CONTINUE")
            print(f"+++ [PLANNER:{mode}] decision={decision} steps={len(steps)}", flush=True)
            yield ("result", {
                "steps"   : steps,
                "decision": decision,
                "response": parsed.get("response") or "",
                "question": parsed.get("question") or "",
            })
            return

        except Exception as e:
            snippet = json_str[:80] if 'json_str' in locals() else "N/A"
            print(f"!!! [PLANNER:{mode}] Error: {e} - raw_snippet={snippet!r}", flush=True)
            full_text = ""
            thinking_shown = 0

    print(f"--- [PLANNER] all modes exhausted — returning hardcoded DONE", flush=True)
    yield ("result", {
        "steps"   : _normalize_steps([]),
        "decision": "DONE",
        "response": "Planning failed (API error or invalid model). Please check your API key and model access.",
        "question": "",
    })


def _initial_prompt(goal: str, tool_names: list, system_prompt: str = "", history_context: str = "", steps_done: int = 0) -> str:
    agent_ctx = f"AGENT CONTEXT (follow these instructions closely):\n{system_prompt[:800]}\n\n" if system_prompt else ""
    history_block = f"RECENT CONVERSATION:\n{history_context[:600]}\n\n" if history_context else ""

    return f"""{agent_ctx}{history_block}You are a planning module for an AI agent.
CURRENT EXECUTION STEP: {steps_done + 1}
AVAILABLE TOOLS: {", ".join(tool_names) if tool_names else "none"}

GOAL: {goal}

RULES:
- Read the AGENT CONTEXT above carefully — it defines how this agent should behave, what tools to prefer, and how to interact with the user. Follow it.
- Read the RECENT CONVERSATION above — if the user already provided details (scope, format, focus, etc.), do NOT ask again. Proceed with the task.
- If the goal is vague AND no prior conversation clarifies it, you may set decision="ASK_USER" with targeted questions. But if the user gave enough detail, skip straight to planning tool steps.
- If web_search is available and the goal involves current events or facts you're unsure about, plan web_search steps. But it is NOT mandatory for every task — use your judgment.
- decision="DONE" for simple replies (greetings, quick answers, conversational).
- decision="ASK_USER" ONLY if you genuinely cannot proceed without more information.
- decision="CONTINUE" to execute planned steps.
- For report_generation: set tool_args to {{"topic":"exact topic name"}}. Research context is auto-injected — do NOT put placeholder text in context.

For EACH step include:
- "confidence": 0-100
- "clarification_question": if confidence < 85, ONE precise question; otherwise ""

Respond in this EXACT format — thinking sentence first, then JSON:
<thinking>ONE sentence explaining your approach</thinking>
{{"steps":[{{"id":1,"description":"...","type":"tool","tool_name":"...","tool_args":{{...}},"confidence":90,"clarification_question":""}}],"decision":"CONTINUE","response":"","question":""}}
"""


def _refeed_prompt(
    goal: str, summaries: list, prev_steps: list, tool_names: list,
    system_prompt: str = "", force_knowledge: bool = False, history_context: str = "",
    steps_done: int = 0,
) -> str:
    agent_ctx = f"AGENT CONTEXT: {system_prompt[:800]}\n\n" if system_prompt else ""
    history_block = f"RECENT CONVERSATION:\n{history_context}\n\n" if history_context else ""
    summaries_str = "\n".join(summaries[-3:]) if summaries else "None yet."
    steps_str = "\n".join([
        f"- Step {s['id']} ({s['type']}): {s['description']} → {str(s.get('result') or 'no result')[:200]}"
        for s in prev_steps
    ]) if prev_steps else "None yet."

    # Detect if a tool already completed successfully (e.g. report_generation)
    # to prevent duplicate calls
    completed_tools = set()
    for s in (prev_steps or []):
        tn = s.get("tool_name", "")
        res = str(s.get("result", ""))
        if tn and res and "error" not in res.lower() and "failed" not in res.lower():
            completed_tools.add(tn)

    completed_note = ""
    if completed_tools:
        completed_note = f"\nALREADY COMPLETED TOOLS (do NOT call again): {', '.join(completed_tools)}\n"

    # Search failure fallback: tell planner to proceed with what it has
    failure_note = ""
    if force_knowledge:
        failure_note = (
            "\nIMPORTANT: Multiple tool calls have failed consecutively (search returned no results or errors).\n"
            "Do NOT retry the same failing tools. Instead:\n"
            "- If you have gathered ANY useful data from earlier steps, proceed to the next phase (e.g. generate report/output with what you have).\n"
            "- If you have NO data at all, use your training knowledge to complete the task as best you can.\n"
            "- Do NOT ask the user to confirm — just proceed. The user wants results, not more questions.\n"
        )

    return f"""{agent_ctx}{history_block}You are a planning module continuing toward a goal.
CURRENT EXECUTION STEP: {steps_done + 1}

GOAL: {goal}

CONTEXT SO FAR:
{summaries_str}

LAST STEPS TAKEN:
{steps_str}

AVAILABLE TOOLS: {", ".join(tool_names) if tool_names else "none"}
{completed_note}{failure_note}
RULES:
- Read the AGENT CONTEXT above — it defines this agent's behavior. Follow it.
- Do NOT repeat tool calls that already succeeded — check LAST STEPS TAKEN.
- Do NOT plan filler think steps like "Review", "Analyze", "Synthesize", "Consolidate" — use real tool steps or finish.
- If a tool returned no results, try a DIFFERENT query or a different tool — do not repeat the same call.
- decision="DONE" when the goal is complete. Put the final answer in "response".
- decision="ASK_USER" ONLY if genuinely blocked and you cannot proceed.
- decision="CONTINUE" to execute more steps.
- For report_generation: set tool_args to {{"topic":"exact topic name"}}. Research context is auto-injected from prior steps — do NOT put placeholder text in context.

For EACH step include:
- "confidence": 0-100
- "clarification_question": if confidence < 85, ONE precise question; otherwise ""

Respond in this EXACT format — thinking sentence first, then JSON on a new line:
<thinking>ONE sentence explaining your next move</thinking>
{{"steps":[{{"id":1,"description":"...","type":"tool","tool_name":"...","tool_args":{{...}},"confidence":90,"clarification_question":""}}],"decision":"CONTINUE","response":"","question":""}}
"""


# ---------------------------------------------------------------------------
# Executor helpers — gemini-2.0-flash
# ---------------------------------------------------------------------------

def _is_tool_failure(result_str: str) -> bool:
    """Return True if a tool result indicates failure."""
    return any(x in result_str for x in (
        "No results", "Error:", "not available", "not handled", "failed", "No search results"
    ))


async def _run_tool(tool_name: str, tool_args: dict, state: dict, summaries: list) -> str:
    """Dispatch a tool call to the appropriate toolkit function."""
    import toolkit as tk

    agent_id    = state["agent_id"]
    api_key     = state["api_key"]
    working_dir = state["working_dir"]
    agent_name  = state["agent_name"]
    connected   = state["connected_agents"]
    permissions = state["permissions"]

    tools_list       = get_tools_for_agent(permissions, len(connected) > 0, False, state["agent_type"] == "master", bool(working_dir))
    allowed          = {t.name for t in tools_list}

    if tool_name not in allowed:
        print(f"!!! [TOOL] {tool_name} PERMISSION DENIED for agent={agent_id}", flush=True)
        return f"Tool '{tool_name}' not available with current permissions."

    print(f">>> [TOOL] {tool_name} agent={agent_id} args={str(tool_args)[:80]}", flush=True)
    try:
        if tool_name == "web_search":
            return await tk.web_search(tool_args.get("query", ""), agent_id, api_key)

        elif tool_name == "scrape_website":
            return await tk.scrape_website(tool_args.get("url", ""), agent_id)

        elif tool_name == "list_workspace":
            if not working_dir or not os.path.exists(working_dir):
                return "Error: working directory not set."
            lines, count = [], 0
            for root, dirs, files in os.walk(working_dir):
                if count > 500: break
                rel = os.path.relpath(root, working_dir)
                lines.append(f"Dir: {rel if rel != '.' else '(root)'}")
                for f_ in sorted(files): lines.append(f"  {f_}")
                count += len(files)
            return "\n".join(lines)

        elif tool_name == "scout_file":
            return await asyncio.to_thread(tk.scout_file, agent_id, tool_args.get("path", ""), working_dir)

        elif tool_name == "read_file":
            path  = tool_args.get("path", "")
            rng   = tool_args.get("range", "")
            return await asyncio.to_thread(tk.read_file, agent_id, f"{path}|{rng}" if rng else path, working_dir)

        elif tool_name == "write_file":
            path    = tool_args.get("path", "")
            content = tool_args.get("content", "")
            return await asyncio.to_thread(tk.write_file, agent_id, f"{path}|{content}", working_dir)

        elif tool_name == "update_plan":
            obj   = tool_args.get("objective", "")
            steps = tool_args.get("steps", [])
            s_str = ", ".join(steps) if isinstance(steps, list) else str(steps)
            return await tk.update_plan(agent_id, f"{obj}|{s_str}")

        elif tool_name == "ask_user":
            return await tk.ask_user(agent_id, tool_args.get("question", "I have a question."))

        elif tool_name == "generate_report":
            title   = tool_args.get("title", "Report")
            content = tool_args.get("content", "")
            return await tk.generate_report(agent_id, f"{title}|{content}", working_dir)

        if tool_name == "report_generation":
            topic   = tool_args.get("topic", "")
            context = tool_args.get("context", "")
            # If the planner used a placeholder or empty context, inject
            # real research data so the report has actual content and citations
            placeholder_hints = ["paste", "gathered", "all results", "search results", "insert", "context here"]
            if not context or len(context) < 50 or any(h in context.lower() for h in placeholder_hints):
                # Build context from raw step results (full data with URLs),
                # NOT from compressed summaries which lose citations
                raw_parts = []
                for s in _completed_steps_ref.get(agent_id, []):
                    raw = str(s.get("result", ""))
                    if raw and len(raw) > 30:
                        # Cap each step's result to ~1500 chars to control token usage
                        raw_parts.append(raw[:1500])
                # Fallback to summaries if no raw data available
                if not raw_parts:
                    raw_parts = summaries if summaries else []
                if raw_parts:
                    # Cap total context to ~6000 chars (~1500 tokens)
                    joined = "\n\n---\n\n".join(raw_parts)
                    if len(joined) > 6000:
                        joined = joined[:6000]
                    context = "RESEARCH DATA (use URLs for citations):\n\n" + joined
            return await tk.report_generation(agent_id, f"{topic}|{context}", working_dir, api_key, agent_name)

        elif tool_name == "message_agent":
            target_id = tool_args.get("target_agent_id", "")
            message   = tool_args.get("message", "")
            provider  = next((ca.get("provider", "gemini") for ca in connected if ca.get("id") == target_id), "gemini")
            return await tk.message_agent(target_id, message, agent_id, agent_name, api_key, provider)

        else:
            return f"Tool '{tool_name}' not handled."

        print(f"+++ [TOOL] {tool_name} result_len={len(str(result))} preview={str(result)[:80]!r}", flush=True)
        return result

    except Exception as e:
        print(f"!!! [TOOL] {tool_name} exception: {e}", flush=True)
        return f"Error: {str(e)[:200]}"


async def _run_think(description: str, goal: str, summaries: list, api_key: str) -> str:
    """Brief internal reasoning step using gemini-2.0-flash."""
    print(f">>> [THINK] desc={description[:60]!r}", flush=True)
    context = "\n".join(summaries[-2:]) if summaries else "No prior context."
    prompt  = (
        f"Goal: {goal}\n\n"
        f"Prior context:\n{context}\n\n"
        f"Think briefly: {description}\n\n"
        f"Reply in 1-2 sentences. Be specific."
    )
    try:
        llm    = get_llm("fast", api_key, streaming=False)
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        text = result.content.strip()[:400]
        print(f"+++ [THINK] result={text[:60]!r}", flush=True)
        return text
    except Exception as e:
        print(f"!!! [THINK] error: {e}", flush=True)
        return f"Think error: {str(e)[:100]}"


async def _compress(goal: str, steps: list, api_key: str, iteration: int) -> str:
    """Compress step results into ~100-token summary."""
    print(f">>> [COMPRESS] iteration={iteration} steps={len(steps)}", flush=True)
    details = "\n".join([
        f"Step {s['id']} ({s['type']}): {s['description']} → {str(s.get('result') or 'no result')[:200]}"
        for s in steps
    ])
    prompt = (
        f"Summarize these 3 steps and results in at most 80 tokens.\n"
        f"Focus on facts found, not process.\n\n"
        f"Goal context: {goal[:80]}\n\nSteps:\n{details}\n\n"
        f"Return ONLY the summary string."
    )
    try:
        llm    = get_llm("fast", api_key, streaming=False)
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        summary = result.content.strip()[:500]
        print(f"+++ [COMPRESS] summary ({len(summary)} chars): {summary[:60]!r}", flush=True)
        return summary
    except Exception as e:
        print(f"!!! [COMPRESS] error: {e}", flush=True)
        return f"Iter {iteration}: " + "; ".join(
            f"{s['description'][:30]}={str(s.get('result',''))[:50]}" for s in steps
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"
