"""
HITL Engine — Phase-based state machine replacing the flat ReAct loop.

Phases:
  UNDERSTAND → GATHER → STORE → REFLECT → CHECKPOINT → ACT → PRESENT

Model routing:
  Gemini 3.1 Pro (planner): UNDERSTAND, REFLECT, ACT-synthesis
  Gemini 2.0 Flash (fast):  GATHER planning, STORE extraction, PRESENT formatting

The engine is an async generator yielding SSE events, compatible with the
existing frontend without any UI changes.
"""
import os
import json
import re
import asyncio

from langchain_core.messages import HumanMessage
from graph.llm import get_llm
from graph.knowledge_store import KnowledgeStore
from graph import hitl_prompts as prompts

AGENTS_CODE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents_code")


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


def _log(msg: str):
    try:
        print(msg, flush=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Intervention dial helpers
# ---------------------------------------------------------------------------

def should_checkpoint(dial: int, gather_count: int, phase: str) -> bool:
    """Determine if we should halt for human input.

    Dial 1-2 (autopilot): NEVER checkpoint during REFLECT — only at PRESENT.
    Dial 3-5 (balanced):  Checkpoint every 3-4 REFLECT cycles.
    Dial 6-8 (guided):    Checkpoint every 2-3 REFLECT cycles.
    Dial 9-10 (surgical): Checkpoint EVERY REFLECT cycle.
    """
    if phase == "PRESENT":
        return True
    if phase == "REFLECT":
        if dial <= 2:
            return False  # Autopilot: never halt during research
        interval = max(1, 6 - (dial // 2))  # H=10→1, H=3→4
        return gather_count % interval == 0
    return False


def should_auto_act(dial: int, ready_to_act: bool, gather_count: int) -> bool:
    """Determine if the engine should skip checkpoint and auto-produce output."""
    if dial <= 3:
        # THE FIX: Only auto-act if the Planner confirms we have deeply scraped data
        return ready_to_act and gather_count >= 2 
    if dial <= 7:
        # Balanced (Dial 4-7): Auto-act immediately when REFLECT says we have enough facts!
        return ready_to_act
    return False


def get_gather_batch_size(dial: int) -> int:
    """How many tool calls per GATHER phase."""
    # Hardcoded to 20 tool calls (sources) to match the DDGS output
    return 20


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def hitl_loop(state: dict):
    """
    HITL state machine — replaces _react_loop entirely.
    Async generator yielding SSE event strings.
    """
    agent_id = state["agent_id"]
    api_key = state["api_key"]
    dial = max(1, min(10, state.get("user_effort", 5)))  # Clamp 1-10

    store = KnowledgeStore(agent_id)
    store.load()

    _log(f">>> [HITL] agent={agent_id} dial={dial} active_session={store.get_active_session()}")

    # === RESUME: Active session at CHECKPOINT ===
    if store.get_active_session() and store.ledger.get("current_phase") == "CHECKPOINT":
        _log(f"    [HITL] Resuming from CHECKPOINT")
        async for chunk in _resume_from_checkpoint(state, store, dial):
            yield chunk
        return

    # === FRESH SESSION ===
    store.init_session(state["goal"])
    _log(f"    [HITL] New session: {store.ledger['session_id']}")

    # Phase 1: UNDERSTAND
    async for chunk in _phase_understand(state, store):
        yield chunk

    if store.ledger["current_phase"] == "DONE":
        return
    if store.ledger["current_phase"] == "CHECKPOINT":
        return

    # Phase loop: GATHER → STORE → REFLECT → (checkpoint or auto-act)
    async for chunk in _gather_loop(state, store, dial):
        yield chunk


# ---------------------------------------------------------------------------
# Resume from CHECKPOINT
# ---------------------------------------------------------------------------

async def _resume_from_checkpoint(state: dict, store: KnowledgeStore, dial: int):
    """Parse user's steer and continue from CHECKPOINT."""
    user_msg = state["goal"]
    _log(f">>> [HITL:RESUME] parsing steer: {user_msg[:60]!r}")

    steer_result = await _parse_user_steer(user_msg, store, state["api_key"])
    store.add_steer(steer_result.get("refined_focus", user_msg), "CHECKPOINT")

    # Mark selected option
    selected = steer_result.get("selected_option")
    if selected and store.ledger.get("options_presented"):
        for opt in store.ledger["options_presented"]:
            if opt.get("id") == selected:
                opt["status"] = "selected"
            elif opt.get("status") != "selected":
                opt["status"] = "skipped"

    store.save()

    if steer_result.get("is_new_session"):
        _log(f"    [HITL:RESUME] New session detected, resetting")
        store.clear()
        store.init_session(user_msg)
        async for chunk in _phase_understand(state, store):
            yield chunk
        return

    next_phase = steer_result.get("next_phase", "GATHER")
    _log(f"    [HITL:RESUME] next_phase={next_phase}")

    if next_phase == "GATHER":
        # Run dial-controlled gather loop (same logic as main loop)
        async for chunk in _gather_loop(state, store, dial):
            yield chunk
        return

    elif next_phase == "ACT":
        async for chunk in _phase_act(state, store):
            yield chunk
        # Generate PDF report after writing
        async for chunk in _auto_generate_report(state, store):
            yield chunk

    elif next_phase == "DONE":
        # Generate final PDF report from all accumulated outputs + facts
        outputs = store.ledger.get("outputs_written", [])
        if outputs or store.get_all_topics():
            async for chunk in _phase_act(state, store):
                yield chunk
            async for chunk in _auto_generate_report(state, store):
                yield chunk
        else:
            yield _sse({"type": "response", "content": "Session complete. Knowledge store saved."})
            store.update_phase("DONE", "User ended session")
            store.save()


# ---------------------------------------------------------------------------
# Shared gather loop — used by both fresh sessions and resume
# ---------------------------------------------------------------------------

async def _gather_loop(state: dict, store: KnowledgeStore, dial: int):
    """Run GATHER → STORE → REFLECT cycles, controlled by the dial.

    Low dial (1-2):  Many autonomous cycles, auto-ACT when ready, auto-PDF.
    Mid dial (3-5):  A few cycles then checkpoint.
    High dial (6-10): Checkpoint frequently, user steers each step.
    """
    max_gathers = store.ledger.get("max_gather_cycles", 10)
    gather_count = store.ledger.get("gather_cycles_completed", 0)

    while gather_count < max_gathers:
        async for chunk in _phase_gather(state, store, dial):
            yield chunk

        async for chunk in _phase_store(state, store):
            yield chunk

        gather_count += 1
        store.ledger["gather_cycles_completed"] = gather_count
        store.save()

        async for chunk in _phase_reflect(state, store):
            yield chunk

        # --- Decision: auto-act, checkpoint, or keep gathering? ---
        ready = store.ledger.get("ready_to_act", False)

        if should_auto_act(dial, ready, gather_count):
            # Autopilot: skip checkpoint, produce output automatically
            _log(f"    [HITL] Auto-ACT triggered: dial={dial} ready={ready} cycles={gather_count}")
            async for chunk in _phase_act(state, store):
                yield chunk
            async for chunk in _auto_generate_report(state, store):
                yield chunk
            return

        if should_checkpoint(dial, gather_count, "REFLECT"):
            async for chunk in _phase_checkpoint(state, store):
                yield chunk
            return  # Halt — user resumes via next /chat

    # Exhausted max gathers → produce output
    _log(f"    [HITL] Max gathers reached ({max_gathers}), forcing ACT")
    async for chunk in _phase_act(state, store):
        yield chunk
    async for chunk in _auto_generate_report(state, store):
        yield chunk


async def _auto_generate_report(state: dict, store: KnowledgeStore):
    """Autopilot: compile all written outputs into a PDF report automatically."""
    import toolkit as tk

    agent_id = state["agent_id"]
    api_key = state["api_key"]
    working_dir = state.get("working_dir", "")
    agent_name = state.get("agent_name", "Agent")
    goal = store.ledger.get("goal", state.get("goal", "Report"))

    _log(f">>> [HITL:AUTO_REPORT] Generating PDF for goal={goal[:60]!r}")
    yield _sse({"type": "phase", "content": "REPORT"})
    yield _sse({"type": "thought", "content": "Compiling final report..."})

    # Gather all written outputs + all facts from graph for context
    outputs = store.ledger.get("outputs_written", [])
    output_text = "\n\n".join(o.get("text", "") for o in outputs)

    # Build facts context with source attribution and DEEP EVIDENCE
    all_facts = []
    for topic in store.get_all_topics():
        facts = store.get_facts_by_topic(topic["label"])
        for f in facts:
            src = f["sources"][0]["url"] if f["sources"] else "unknown"
            ev = f.get("context_or_evidence", "")
            
            # Format it so the LLM clearly sees the Claim vs. the Evidence
            fact_text = f"- CLAIM: {f['content']}"
            if ev:
                fact_text += f"\n  EVIDENCE: {ev}"
            fact_text += f"\n  SOURCE: {src}"
            
            all_facts.append(fact_text)
            
    facts_context = "\n\n".join(all_facts)

    # Build an explicit, clean sources list so the PDF generator can cite them
    seen_urls = set()
    sources_list = []
    for nid, attrs in store.graph.nodes(data=True):
        if attrs.get("node_type") == "source":
            url = attrs.get("url", "")
            title = attrs.get("title", "")
            if url and url != "unknown" and url not in seen_urls:
                seen_urls.add(url)
                sources_list.append(f"- Title: {title or 'Untitled'}\n  URL: {url}")
    sources_section = "\n".join(sources_list) if sources_list else "No sources available."

    # Combine everything — sources are clearly separated so the PDF generator finds them
    full_context = (
        f"WRITTEN ANALYSIS:\n{output_text}\n\n"
        f"ALL RESEARCH FACTS:\n{facts_context}\n\n"
        f"SOURCES (use these EXACTLY in the report's sources section):\n{sources_section}"
    )

    if not working_dir:
        # No working dir — fall back to presenting text
        yield _sse({"type": "response", "content": output_text or "No output generated."})
        store.update_phase("DONE", "No working dir for PDF")
        store.save()
        return

    try:
        result = await tk.report_generation(
            agent_id, f"{goal}|{full_context}", working_dir, api_key, agent_name
        )
        _log(f"+++ [HITL:AUTO_REPORT] {result}")

        # Show written analysis + PDF confirmation
        parts = [output_text, "", f"---", f"**{result}**"]
        yield _sse({"type": "response", "content": "\n".join(parts)})
        store.update_phase("DONE", f"Auto-report generated: {result[:60]}")
        store.save()

    except Exception as e:
        _log(f"!!! [HITL:AUTO_REPORT] Error: {e}")
        # Fallback: show text output without PDF
        yield _sse({"type": "response", "content": output_text or f"Report generation failed: {e}"})
        store.update_phase("DONE", f"Report error: {str(e)[:60]}")
        store.save()


# ---------------------------------------------------------------------------
# Phase: UNDERSTAND
# ---------------------------------------------------------------------------

async def _phase_understand(state: dict, store: KnowledgeStore):
    """Classify task and detect ambiguity. Uses planner model (Gemini 3)."""
    _log(f">>> [HITL:UNDERSTAND] goal={state['goal'][:60]!r}")
    yield _sse({"type": "phase", "content": "UNDERSTAND"})
    yield _sse({"type": "thought", "content": "Analyzing your request..."})

    # Load conversation history
    history_context = _load_history_context(state["agent_id"])
    ledger_summary = store.get_ledger_summary() if store.get_active_session() else ""

    prompt = prompts.understand_prompt(state["goal"], history_context, ledger_summary)

    try:
        result = await _call_model("planner", prompt, state["api_key"], streaming=True)

        # Stream thinking tokens
        if isinstance(result, dict) and "raw" in result:
            # Non-streaming fallback
            text = result["raw"]
        else:
            text = result

        parsed = _parse_json(text)
        _log(f"+++ [HITL:UNDERSTAND] task_type={parsed.get('task_type')} needs_clarification={parsed.get('needs_clarification')}")

        task_type = parsed.get("task_type", "multi_phase")

        # Trivial task → respond directly
        if task_type == "trivial":
            response = parsed.get("direct_response", "I'm here to help!")
            yield _sse({"type": "response", "content": response})
            store.update_phase("DONE", f"Trivial: {task_type}")
            store.save()
            return

        # Store understanding
        store.ledger["understanding"] = {
            "intent": parsed.get("intent", "other"),
            "domain": parsed.get("domain", "general"),
            "scope_clarifications": [],
        }

        # Needs clarification → CHECKPOINT
        if parsed.get("needs_clarification") and parsed.get("clarification_question"):
            question = parsed["clarification_question"]
            yield _sse({"type": "response", "content": question})
            store.update_phase("CHECKPOINT", f"Clarification: {question[:60]}")
            store.save()
            return

        # Clear task → proceed to GATHER
        store.update_phase("GATHER", f"Understood: {parsed.get('intent', 'multi_phase')}")
        store.save()

    except Exception as e:
        _log(f"!!! [HITL:UNDERSTAND] Error: {e}")
        # On error, assume multi-phase and proceed
        store.update_phase("GATHER", f"Understand error, proceeding: {str(e)[:60]}")
        store.save()


# ---------------------------------------------------------------------------
# Phase: GATHER
# ---------------------------------------------------------------------------

async def _phase_gather(state: dict, store: KnowledgeStore, dial: int):
    """Execute tool calls in a batch. Uses fast model (Flash)."""
    _log(f">>> [HITL:GATHER] dial={dial}")
    yield _sse({"type": "phase", "content": "GATHER"})
    yield _sse({"type": "thought", "content": "Researching..."})

    batch_size = get_gather_batch_size(dial)

    # Build context for gather planning
    steers = "; ".join(s["steer"] for s in store.ledger.get("user_steers", [])[-3:])
    gaps = "; ".join(store.ledger.get("gaps", [])[:5])
    graph_summary = store.get_graph_summary()

    # Get available tools from state
    from graph.tool_definitions import get_tools_for_agent
    permissions = state.get("permissions", [])
    connected = state.get("connected_agents", [])
    has_working_dir = bool(state.get("working_dir", ""))
    tools = get_tools_for_agent(permissions, len(connected) > 0, False, state.get("agent_type") == "master", has_working_dir)
    tool_names = [t.name for t in tools]

    prompt = prompts.gather_plan_prompt(
        state["goal"], steers, gaps, tool_names, batch_size, graph_summary
    )

    try:
        text = await _call_model("fast", prompt, state["api_key"])
        parsed = _parse_json(text)
        tool_calls = parsed.get("tool_calls", [])
        
        # Prevent web_search spam: strictly allow only 1 web_search per batch!
        web_search_calls = [tc for tc in tool_calls if tc.get("tool_name") == "web_search"]
        if len(web_search_calls) > 1:
            tool_calls = [tc for tc in tool_calls if tc.get("tool_name") != "web_search"] + [web_search_calls[0]]

        # Anti-laziness AND Anti-Spam: Auto-expand scrape_website calls using known URLs
        # Extract URLs directly from the knowledge graph sources
        known_urls = []
        for nid, attrs in store.graph.nodes(data=True):
            if attrs.get("node_type") == "source" and attrs.get("url"):
                url = attrs["url"]
                if url != "unknown" and url not in known_urls:
                    known_urls.append(url)
        
        if known_urls:
            planned_urls = {tc.get("tool_args", {}).get("url") for tc in tool_calls if tc.get("tool_name") == "scrape_website"}
            
            # Prioritize inserting scrapes at the front so they execute first
            for url in known_urls:
                if len(tool_calls) >= batch_size: break
                if url not in planned_urls and not url.endswith(('.jpg', '.png', '.pdf')):
                    tool_calls.insert(0, {"tool_name": "scrape_website", "tool_args": {"url": url}})
                    planned_urls.add(url)
                    
        _log(f"+++ [HITL:GATHER] planned {len(tool_calls)} tool calls")
    except Exception as e:
        _log(f"!!! [HITL:GATHER] Planning error: {e}, falling back to web_search")
        tool_calls = [{"tool_name": "web_search", "tool_args": {"query": state["goal"]}}]

    # Execute each tool call CONCURRENTLY
    raw_results = []
    tasks = []

    # 1. Fire off all tasks at the exact same time
    for tc in tool_calls[:batch_size]:
        tool_name = tc.get("tool_name", "")
        tool_args = tc.get("tool_args", {})

        if not tool_name:
            continue

        # Tell the UI we are starting this action immediately
        arg_preview = str(list(tool_args.values())[0])[:40] if tool_args else ""
        yield _sse({"type": "action", "content": f"{tool_name}: {arg_preview}"})

        # Wrapper function to keep track of which task is which
        async def run_tool(name, args, orig_tc):
            res = await _execute_tool(name, args, state)
            return orig_tc, name, args, res

        tasks.append(asyncio.create_task(run_tool(tool_name, tool_args, tc)))

    # 2. Process them exactly as they finish (no waiting for the slowest one)
    for future in asyncio.as_completed(tasks):
        tc, tool_name, tool_args, result = await future

        preview = str(result)[:150]
        yield _sse({"type": "action_result", "content": preview})
        _log(f"    [HITL:GATHER] {tool_name} -> {len(str(result))} chars")

        raw_results.append({
            "tool_name": tool_name,
            "tool_args": tool_args,
            "raw_result": str(result)[:3000],
            "timestamp": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    # Store raw results in scratchpad
    store.add_raw_results(raw_results)
    store.update_phase("STORE", f"Gathered {len(raw_results)} results")
    store.save()


# ---------------------------------------------------------------------------
# Phase: STORE
# ---------------------------------------------------------------------------

async def _phase_store(state: dict, store: KnowledgeStore):
    """Extract facts from raw results and add to NetworkX graph. Uses fast model (Flash)."""
    pending = store.get_pending_results()
    if not pending:
        _log(f"    [HITL:STORE] No pending results to process")
        return

    _log(f">>> [HITL:STORE] processing {len(pending)} raw results")
    yield _sse({"type": "phase", "content": "STORE"})
    yield _sse({"type": "thought", "content": "Extracting and storing findings..."})

    # Build raw results string for fact extraction
    raw_str_parts = []
    for entry in pending:
        tool_name = entry.get("tool_name", "")
        raw = entry.get("raw_result", "")
        if raw:
            raw_str_parts.append(f"[{tool_name}]\n{raw}")

    raw_str = "\n\n---\n\n".join(raw_str_parts)

    prompt = prompts.extract_facts_prompt(raw_str, state["goal"])

    try:
        text = await _call_model("fast", prompt, state["api_key"])
        parsed = _parse_json(text)
        facts_data = parsed.get("facts", [])
        _log(f"+++ [HITL:STORE] Extracted {len(facts_data)} facts")
    except Exception as e:
        _log(f"!!! [HITL:STORE] Extraction error: {e}")
        facts_data = []

    # Add facts to graph
    for fact in facts_data:
        source_url = fact.get("source_url", "unknown")
        source_title = fact.get("source_title", "")

        # Add or get source node
        source_id = store.add_source(source_url, source_title, "", "")

        # Add fact node with edges
        store.add_fact(
            content=fact.get("content", ""),
            source_id=source_id,
            topic_tags=fact.get("topic_tags", []),
            confidence=fact.get("confidence", 0.7),
            context_or_evidence=fact.get("context_or_evidence", ""),
        )

    # Clear scratchpad
    store.clear_scratchpad()
    store.update_phase("REFLECT", f"Stored {len(facts_data)} facts")
    store.save()

    yield _sse({"type": "thought", "content": f"Stored {len(facts_data)} facts across {len(set(t for f in facts_data for t in f.get('topic_tags', [])))} topics"})


# ---------------------------------------------------------------------------
# Phase: REFLECT
# ---------------------------------------------------------------------------

async def _phase_reflect(state: dict, store: KnowledgeStore):
    """Analyze graph, identify gaps, generate options. Uses planner model (Gemini 3)."""
    _log(f">>> [HITL:REFLECT]")
    yield _sse({"type": "phase", "content": "REFLECT"})
    yield _sse({"type": "thought", "content": "Analyzing findings..."})

    graph_summary = store.get_graph_summary()
    ledger_summary = store.get_ledger_summary()
    steers = "; ".join(s["steer"] for s in store.ledger.get("user_steers", [])[-3:])
    fact_snippets = store.get_fact_snippets_for_reflect()

    prompt = prompts.reflect_prompt(
        state["goal"], graph_summary, ledger_summary, steers, fact_snippets
    )

    try:
        text = await _call_model("planner", prompt, state["api_key"])
        parsed = _parse_json(text)

        gaps = parsed.get("gaps", [])
        options = parsed.get("options", [])
        analysis = parsed.get("analysis", "")

        ready_to_act = parsed.get("ready_to_act", False)
        _log(f"+++ [HITL:REFLECT] gaps={len(gaps)} options={len(options)} ready={ready_to_act}")

        # Update store
        store.set_gaps(gaps)
        store.set_options([
            {"id": o.get("id", i+1), "text": o.get("text", ""), "status": "pending"}
            for i, o in enumerate(options)
        ])
        store.ledger["ready_to_act"] = ready_to_act
        store.update_phase("REFLECT", analysis[:200])
        store.save()

        # Stream the analysis as thought
        if analysis:
            yield _sse({"type": "thought", "content": analysis})

    except Exception as e:
        _log(f"!!! [HITL:REFLECT] Error: {e}")
        store.update_phase("REFLECT", f"Reflect error: {str(e)[:60]}")
        store.save()


# ---------------------------------------------------------------------------
# Phase: CHECKPOINT
# ---------------------------------------------------------------------------

async def _phase_checkpoint(state: dict, store: KnowledgeStore):
    """Format and emit checkpoint output. Calls fast model for conversational message."""
    _log(f">>> [HITL:CHECKPOINT]")
    yield _sse({"type": "phase", "content": "CHECKPOINT"})

    gaps = store.ledger.get("gaps", [])
    options = store.ledger.get("options_presented", [])
    topics = store.get_all_topics()

    # Collect a few recent facts for the LLM to reference naturally
    all_fact_nodes = [
        (nid, attrs) for nid, attrs in store.graph.nodes(data=True)
        if attrs.get("node_type") == "fact"
    ]
    recent_facts = [
        {"content": attrs.get("content", "")}
        for _, attrs in all_fact_nodes[-4:]
    ]

    # Count sources for the prompt
    sources_count = sum(
        1 for _, d in store.graph.nodes(data=True) if d.get("node_type") == "source"
    )
    facts_count = len(all_fact_nodes)

    goal = store.ledger.get("goal", state.get("goal", ""))

    prompt = prompts.checkpoint_prompt(
        goal=goal,
        sources_count=sources_count,
        facts_count=facts_count,
        topics=topics,
        recent_facts=recent_facts,
        options=options,
        gaps=gaps,
    )

    try:
        checkpoint_msg = await _call_model("fast", prompt, state["api_key"])
        checkpoint_msg = checkpoint_msg.strip()
        _log(f"+++ [HITL:CHECKPOINT] generated {len(checkpoint_msg)} char message")
    except Exception as e:
        _log(f"!!! [HITL:CHECKPOINT] LLM error, falling back to simple format: {e}")
        # Fallback: simple plain-English message
        option_lines = "\n".join(
            f"{o.get('id', i+1)}. {o.get('text', '')}" for i, o in enumerate(options)
        )
        checkpoint_msg = f"I've been digging into this and here's where things stand. Where would you like to go next?\n\n{option_lines}"

    yield _sse({"type": "response", "content": checkpoint_msg})
    store.update_phase("CHECKPOINT", f"Presented {len(options)} options")
    store.save()
    _log(f"--- [HITL:CHECKPOINT] Halting. Options={len(options)} Gaps={len(gaps)}")


# ---------------------------------------------------------------------------
# Phase: ACT
# ---------------------------------------------------------------------------

async def _phase_act(state: dict, store: KnowledgeStore):
    """Produce ONE unit of output with citations. Uses planner model (Gemini 3)."""
    _log(f">>> [HITL:ACT]")
    yield _sse({"type": "phase", "content": "ACT"})
    yield _sse({"type": "thought", "content": "Writing..."})

    # Determine focus from latest steer
    steers = store.ledger.get("user_steers", [])
    focus = steers[-1]["steer"] if steers else state["goal"]

    # Get relevant facts
    # Try to match focus to a topic
    topics = store.get_all_topics()
    relevant_facts_str = ""

    # Search all topics for facts related to the focus
    all_facts = []
    for topic in topics:
        facts = store.get_facts_by_topic(topic["label"])
        for f in facts:
            src_str = f["sources"][0]["url"] if f["sources"] else "unknown"
            all_facts.append(f"[{f['id']}] {f['content']} (source: {src_str})")

    relevant_facts_str = "\n".join(all_facts[-20:]) if all_facts else "No facts available."

    # Get already written outputs
    outputs = store.ledger.get("outputs_written", [])
    outputs_str = "\n\n".join(o.get("text", "")[:200] for o in outputs) if outputs else ""

    prompt = prompts.act_synthesis_prompt(state["goal"], focus, relevant_facts_str, outputs_str)

    try:
        text = await _call_model("planner", prompt, state["api_key"])
        # The response IS the written content (not JSON)
        output_text = text.strip()
        _log(f"+++ [HITL:ACT] wrote {len(output_text)} chars")

        # Track output
        fact_ids = re.findall(r'\[fact_\d+\]', output_text)
        store.add_output(focus, output_text, fact_ids)
        store.update_phase("PRESENT", f"Wrote section on: {focus[:40]}")
        store.save()

    except Exception as e:
        _log(f"!!! [HITL:ACT] Error: {e}")
        output_text = f"Error generating content: {str(e)[:200]}"
        store.update_phase("PRESENT", f"Act error")
        store.save()

    # Store output text in state for PRESENT phase
    state["_last_output"] = output_text


# ---------------------------------------------------------------------------
# Phase: PRESENT
# ---------------------------------------------------------------------------

async def _phase_present(state: dict, store: KnowledgeStore):
    """Format output and generate next options. Uses fast model (Flash)."""
    _log(f">>> [HITL:PRESENT]")
    yield _sse({"type": "phase", "content": "PRESENT"})

    output_text = state.get("_last_output", "No output generated.")
    graph_summary = store.get_graph_summary()
    gaps = "; ".join(store.ledger.get("gaps", [])[:5])
    ledger_summary = store.get_ledger_summary()

    prompt = prompts.present_prompt(output_text, graph_summary, gaps, ledger_summary)

    try:
        text = await _call_model("fast", prompt, state["api_key"])
        parsed = _parse_json(text)

        formatted = parsed.get("formatted_output", output_text)
        next_options = parsed.get("next_options", [])

        _log(f"+++ [HITL:PRESENT] options={len(next_options)}")

        # Update store with new options
        store.set_options([
            {"id": o.get("id", i+1), "text": o.get("text", ""), "status": "pending"}
            for i, o in enumerate(next_options)
        ])
        store.update_phase("CHECKPOINT", f"Presented output + {len(next_options)} options")
        store.save()

        # Build response
        parts = [formatted, ""]
        if next_options:
            parts.append("**What's next?**")
            for opt in next_options:
                parts.append(f"{opt.get('id', '?')}. {opt.get('text', '')}")

        yield _sse({"type": "response", "content": "\n".join(parts)})

    except Exception as e:
        _log(f"!!! [HITL:PRESENT] Error: {e}")
        # Fallback: just present the raw output
        yield _sse({"type": "response", "content": output_text})
        store.update_phase("CHECKPOINT", "Present error, showed raw output")
        store.save()


# ---------------------------------------------------------------------------
# Steer parsing
# ---------------------------------------------------------------------------

async def _parse_user_steer(user_msg: str, store: KnowledgeStore, api_key: str) -> dict:
    """Interpret user's checkpoint response. Uses fast model (Flash)."""
    options = store.ledger.get("options_presented", [])
    ledger_summary = store.get_ledger_summary()

    prompt = prompts.parse_steer_prompt(user_msg, options, ledger_summary)

    try:
        text = await _call_model("fast", prompt, api_key)
        parsed = _parse_json(text)
        _log(f"+++ [HITL:STEER] parsed: option={parsed.get('selected_option')} next={parsed.get('next_phase')}")
        return parsed
    except Exception as e:
        _log(f"!!! [HITL:STEER] Error: {e}")
        return {
            "selected_option": None,
            "next_phase": "GATHER",
            "refined_focus": user_msg,
            "is_new_session": False,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _call_model(mode: str, prompt: str, api_key: str, streaming: bool = False) -> str:
    """Call LLM and return response text. Falls back from planner → fast on error."""
    modes = [mode, "fast"] if mode != "fast" else ["fast"]

    for m in modes:
        try:
            llm = get_llm(m, api_key, streaming=False)
            result = await llm.ainvoke([HumanMessage(content=prompt)])
            content = result.content
            if isinstance(content, list):
                text_parts = [p if isinstance(p, str) else p.get("text", "") for p in content]
                text = text_parts[-1].strip() if text_parts else ""
            else:
                text = content.strip()
            if text:
                _log(f"    [HITL:LLM] mode={m} response_len={len(text)}")
                return text
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "resource exhausted" in err_str:
                _log(f"!!! [HITL:LLM] Rate limit on {m}, trying next")
                continue
            raise

    return ""


def _parse_json(text: str) -> dict:
    """Extract and parse JSON from LLM response, handling markdown fences."""
    # Remove thinking tags if present
    if "</thinking>" in text:
        text = text.split("</thinking>", 1)[1].strip()

    # Remove markdown fences
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    # Fix trailing commas
    text = re.sub(r',\s*([}\]])', r'\1', text)

    return json.loads(text)


async def _execute_tool(tool_name: str, tool_args: dict, state: dict) -> str:
    """Execute a single tool call. Delegates to toolkit functions."""
    import toolkit as tk

    agent_id = state["agent_id"]
    api_key = state["api_key"]
    working_dir = state.get("working_dir", "")
    agent_name = state.get("agent_name", "Agent")

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
                if count > 500:
                    break
                rel = os.path.relpath(root, working_dir)
                lines.append(f"Dir: {rel if rel != '.' else '(root)'}")
                for f_ in sorted(files):
                    lines.append(f"  {f_}")
                count += len(files)
            return "\n".join(lines)

        elif tool_name == "scout_file":
            return await asyncio.to_thread(
                tk.scout_file, agent_id, tool_args.get("path", ""), working_dir
            )

        elif tool_name == "read_file":
            path = tool_args.get("path", "")
            rng = tool_args.get("range", "")
            return await asyncio.to_thread(
                tk.read_file, agent_id, f"{path}|{rng}" if rng else path, working_dir
            )

        elif tool_name == "write_file":
            path = tool_args.get("path", "")
            content = tool_args.get("content", "")
            return await asyncio.to_thread(
                tk.write_file, agent_id, f"{path}|{content}", working_dir
            )

        elif tool_name == "generate_report":
            title = tool_args.get("title", "Report")
            content = tool_args.get("content", "")
            return await tk.generate_report(agent_id, f"{title}|{content}", working_dir)

        elif tool_name == "report_generation":
            topic = tool_args.get("topic", "")
            context = tool_args.get("context", "")
            return await tk.report_generation(
                agent_id, f"{topic}|{context}", working_dir, api_key, agent_name
            )

        elif tool_name == "message_agent":
            target_id = tool_args.get("target_agent_id", "")
            message = tool_args.get("message", "")
            connected = state.get("connected_agents", [])
            provider = next(
                (ca.get("provider", "gemini") for ca in connected if ca.get("id") == target_id),
                "gemini"
            )
            return await tk.message_agent(
                target_id, message, agent_id, agent_name, api_key, provider
            )

        else:
            return f"Tool '{tool_name}' not handled."

    except Exception as e:
        _log(f"!!! [HITL:TOOL] {tool_name} error: {e}")
        return f"Error: {str(e)[:200]}"


def _load_history_context(agent_id: str) -> str:
    """Load recent conversation history for context."""
    history_path = os.path.join(AGENTS_CODE_DIR, agent_id, "history.json")
    if not os.path.exists(history_path):
        return ""
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)
        parts = []
        for entry in history[-4:]:
            role = "User" if entry.get("role") == "user" else "Assistant"
            parts.append(f"{role}: {entry.get('content', '')[:300]}")
        return "\n".join(parts)
    except Exception:
        return ""
