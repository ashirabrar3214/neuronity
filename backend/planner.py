import httpx
import json
import os
import re
import time
import asyncio

BACKEND_URL = "http://127.0.0.1:8000"
AGENTS_CODE_DIR = os.path.join(os.path.dirname(__file__), "agents_code")


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
            model = "gemini-3-flash-preview"
            # Enable deep reasoning ONLY for plan generation
            generation_config = {
                "temperature": 0.2,
                "thinkingConfig": {"includeThoughts": True, "thinkingBudget": -1}
            }
        else:
            model = "gemini-2.0-flash"
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


async def is_task_request(text, api_key, provider):
    """
    Asks the LLM if the message is a complex task/command or just casual conversation.
    Returns True if it's a task, False if it's chat.
    """
    if not text or len(text.strip()) < 3:
        return False

    prompt = f"""You are an Intent Classifier. Analyze the message below and decide if it is a 'TASK' (requires research, file access, report generation, or multi-step action) or 'CHAT' (simple greeting, thanks, or conversation with no specific objective).

EXAMPLES:
"hello there" -> CHAT
"make a report on the iran war" -> TASK
"research the history of rome" -> TASK
"generate a pdf report on solar energy" -> TASK
"thank you so much" -> CHAT
"what can you do?" -> CHAT
"help me write a plan for a new startup" -> TASK

MESSAGE: "{text}"

Return ONLY the word 'TASK' or 'CHAT'."""

    res = await _call_llm_direct(prompt, api_key, provider, mode="fast")
    return "TASK" in res.upper()


async def generate_plan(task, agent_id, api_key, provider, agents_info=""):
    """
    Ask the LLM to break the task into numbered execution steps.
    """
    safe_log(f"[STATUS:{agent_id}] Generating execution plan...")

    agents_context = f"\n\nAVAILABLE CONNECTED AGENTS:\n{agents_info}" if agents_info else ""

    prompt = f"""You are a master task planner. Break the following task into a detailed numbered list of clear, specific execution steps.{agents_context}

TASK: {task}

RULES:
- Each step is ONE specific action (e.g., ask a specific agent once, do one web search). One step = one action.
- If the task requires asking the same agent multiple times (e.g., 3 rounds of research), create a separate numbered step for EACH individual call. Do NOT merge them.
- If agents are listed above, name the specific agent and their ID for each step.
- There is NO maximum number of steps. Use as many as the task logically needs. A 30-step plan is perfectly fine.
- Keep each step to one concise line.
- The FINAL step must ALWAYS be exactly: "Use report_generation to create a PDF with all gathered findings"

Return ONLY a numbered list, nothing else. Example of a 6-step multi-agent plan:
1. Ask Religion Agent (agent-xxx) to research the religious origins of the conflict — Round 1
2. Ask Economic Agent (agent-yyy) to analyze the economic sanctions — Round 1
3. Ask Religion Agent (agent-xxx) to deep-dive on sectarian violence — Round 2
4. Ask Economic Agent (agent-yyy) to analyze oil revenue impacts — Round 2
5. Ask Political Agent (agent-zzz) to summarize geopolitical alliances
6. Use report_generation to create a PDF with all gathered findings

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


def save_intentions_md(steps, task, agent_id):
    """Save the committed intentions as JSON to unify with the update_plan tool."""
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_id)
    os.makedirs(agent_dir, exist_ok=True)
    intentions_path = os.path.join(agent_dir, "intentions.json")

    # Format it exactly like the toolkit.py update_plan does
    intentions = {
        "objective": task,
        "steps": steps,
        "completed": []
    }
    with open(intentions_path, "w", encoding="utf-8") as f:
        import json
        json.dump(intentions, f, indent=2)

    return intentions_path


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


async def run_autonomous(agent_id, task, api_key, provider, agents_info=""):
    """
    Phase 1: Generate the intentions only.
    """
    safe_log(f"[STATUS:{agent_id}] Autonomous deliberation complete: Intentions generated")
    steps = await generate_plan(task, agent_id, api_key, provider, agents_info)
    if steps:
        save_intentions_md(steps, task, agent_id)
    return steps

async def run_execution_loop(agent_id, task, api_key, provider):
    """
    Phase 2: Actual step-by-step execution loop.
    Clears the Blackboard at start, injects EXTRACTION MODE into each step,
    and pulls from the Blackboard (not accumulated context) for the PDF step.
    """
    safe_log(f"[STATUS:{agent_id}] Autonomous execution loop started")
    
    # CLEAR VOLATILE LEDGER: Start with a fresh slate
    volatile_path = os.path.join(AGENTS_CODE_DIR, "volatile_findings.json")
    if os.path.exists(volatile_path):
        try:
            os.remove(volatile_path)
            safe_log(f"--- [CLEANUP] Volatile ledger cleared for new task.")
        except: pass

    # TIERED BELIEF PERSISTENCE: beliefs_base.json is NOT cleared.
    # Instead, brf.py handles session-based relevance and promotions.
    # We create a unique session ID for this execution run.
    session_id = f"sess_{int(time.time())}"
    safe_log(f"--- [BDI] Session initialized: {session_id}")

    # Load from intentions.json (Unified Source)
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_id)
    intentions_path = os.path.join(agent_dir, "intentions.json")
    
    steps = []
    if os.path.exists(intentions_path):
        try:
            with open(intentions_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                steps = data.get("steps", [])
                task = data.get("objective", task) # Adopt the objective from the file
        except Exception as e:
            safe_log(f"!!! [PLAN_RUNNER] Error reading intentions.json: {e}")

    if not steps:
        return "Failed to locate an execution plan. Please try generating the plan again."

    accumulated_context = ""
    step_results = []

    # Detect if last step is a PDF generation step
    PDF_KEYWORDS = ["report_generation", "pdf", "create a pdf", "generate a pdf"]
    last_step_lower = steps[-1].lower()
    last_is_pdf = any(w in last_step_lower for w in PDF_KEYWORDS)

    for i, step in enumerate(steps, 1):
        # ─── CLOSED-LOOP COMMITMENT (CHECK-IN) ──────────────────────
        # Every 3 steps, ask the deliberator if we should pivot
        if i > 1 and i % 3 == 0:
            import deliberator
            from interpreter import get_beliefs_context
            beliefs_ctx = get_beliefs_context()
            
            # Load history for deliberator context
            history = []
            history_path = os.path.join(agent_dir, "history.json")
            if os.path.exists(history_path):
                try:
                    with open(history_path, "r", encoding="utf-8") as f:
                        history = json.load(f)
                except: pass
                
            decision, reason = await deliberator.deliberate(agent_id, f"Ongoing task: {task}. Next step: {step}", api_key, provider, beliefs_ctx, history=history)
            
            if decision == "RE-PLAN":
                safe_log(f"!!! [PIVOT] Deliberator signals RE-PLAN: {reason}")
                # Archive current intentions and trigger a new cycle
                # (Recursive call to generate new plan based on current beliefs)
                new_steps = await run_autonomous(agent_id, task, api_key, provider)
                if new_steps:
                    return await run_execution_loop(agent_id, task, api_key, provider)
                else:
                    return f"Pivot failed: Could not generate new intentions. Reason: {reason}"

        is_last = (i == len(steps))
        is_pdf = is_last and last_is_pdf

        result = await execute_step(
            i, len(steps), step, agent_id,
            accumulated_context, api_key, provider,
            is_pdf_step=is_pdf, session_id=session_id
        )
        step_results.append((step, result))
        if not is_pdf:
            accumulated_context += f"\n### Step {i}: {step}\n{result}\n"

    # Final PDF compilation logic
    if last_is_pdf:
        final_response = step_results[-1][1]
    else:
        safe_log(f"[STATUS:{agent_id}] No PDF step in plan — adding PDF generation...")
        result = await execute_step(
            len(steps) + 1, len(steps) + 1,
            f"Create a PDF report for: {task}",
            agent_id,
            accumulated_context, api_key, provider,
            is_pdf_step=True, session_id=session_id
        )
        final_response = result

    safe_log(f"[STATUS:{agent_id}] Autonomous task complete")
    
    # FINAL CLEANUP: (Deletion of volatile findings and plans commented out to fix 'Clean Slate' bug)
    # if os.path.exists(volatile_path):
    #     try:
    #         os.remove(volatile_path)
    #         safe_log(f"--- [CLEANUP] Volatile ledger deleted after task completion.")
    #     except: pass

    # if os.path.exists(intentions_path):
    #     try:
    #         os.remove(intentions_path)
    #         safe_log(f"--- [BDI CLEANUP] intentions.md deleted after task completion.")
    #     except: pass

    return final_response
