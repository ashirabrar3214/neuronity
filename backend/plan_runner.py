import requests
import json
import os
import re
import time

BACKEND_URL = "http://127.0.0.1:8000"
AGENTS_CODE_DIR = os.path.join(os.path.dirname(__file__), "agents_code")


def safe_log(message):
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        print(message.encode('ascii', 'replace').decode('ascii'), flush=True)
    except Exception:
        pass


def _call_llm_direct(prompt, api_key, provider):
    """One-shot LLM call for plan generation (no history, no tools)."""
    if provider == "gemini":
        model = "gemini-2.0-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        data = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2}
        }
        try:
            resp = requests.post(url, json=data, timeout=30)
            if resp.status_code == 200:
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            safe_log(f"!!! [PLAN_RUNNER] LLM error: {e}")

    pass # Anthropic removed
    return ""

    return ""


def is_task_request(text, api_key, provider):
    """
    Asks the LLM if the message is a complex task/command or just casual conversation.
    Returns True if it's a task, False if it's chat.
    """
    if not text or len(text.strip()) < 3:
        return False

    prompt = f"""Determine if the following message is a "TASK" (a request for research, analysis, or multi-step action) or "CHAT" (a greeting, thanks, or casual remark).

MESSAGE: "{text}"

Return ONLY 'TASK' or 'CHAT'."""

    res = _call_llm_direct(prompt, api_key, provider)
    return "TASK" in res.upper()


def generate_plan(task, agent_id, api_key, provider, agents_info=""):
    """
    Ask the LLM to break the task into numbered execution steps.
    Returns a list of step strings. No arbitrary step limit — the plan
    should be as long as the task requires, including loops over agents.
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

    text = _call_llm_direct(prompt, api_key, provider)

    steps = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if re.match(r'^\d+[\.\)]\s', line):
            step = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
            if step:
                steps.append(step)

    return steps


def save_plan_md(steps, task, agent_id):
    """Save the execution plan as a readable markdown file inside the agent's directory."""
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_id)
    os.makedirs(agent_dir, exist_ok=True)
    plan_path = os.path.join(agent_dir, "plan.md")

    with open(plan_path, "w", encoding="utf-8") as f:
        f.write("# Autonomous Execution Plan\n")
        f.write(f"**Task:** {task}\n")
        f.write(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Steps\n")
        for i, step in enumerate(steps, 1):
            f.write(f"{i}. {step}\n")
        f.write("\n---\n*This plan is being executed autonomously.*\n")

    return plan_path


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


def execute_step(step_num, total_steps, step_text, agent_id, accumulated_context, api_key, provider, is_pdf_step=False):
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
        # Hard-code the PDF generation instruction — no ambiguity, no thinking needed
        message = (
            f"[AUTO_STEP {step_num}/{total_steps}] AUTONOMOUS EXECUTION MODE — PDF GENERATION.\n\n"
            f"All research is complete. Your ONLY job now is to call the report_generation tool to create a PDF.\n"
            f"Do NOT use thinking, web_search, or generate_report. Use ONLY report_generation.\n"
            f"Do NOT ask for more information or capabilities. The data below is sufficient.\n\n"
            f"ORIGINAL TASK: {step_text}\n"
            f"{ctx_section}"
        )
    else:
        message = (
            f"[AUTO_STEP {step_num}/{total_steps}] AUTONOMOUS EXECUTION MODE.\n"
            f"Execute ONLY this specific step and return the result. Do not attempt other steps.\n\n"
            f"STEP: {step_text}"
            f"{ctx_section}"
        )

    try:
        resp = requests.post(f"{BACKEND_URL}/chat", json={
            "agent_id": agent_id,
            "message": message,
            "api_key": api_key,
            "provider": provider
        }, timeout=300)

        if resp.status_code == 200:
            result = resp.json().get("response", "")
            safe_log(f"[STATUS:{agent_id}] Step {step_num} complete")
            return result
        else:
            safe_log(f"!!! [PLAN_RUNNER] Step {step_num} HTTP {resp.status_code}")
            return f"Step failed: HTTP {resp.status_code}"

    except requests.exceptions.Timeout:
        safe_log(f"!!! [PLAN_RUNNER] Step {step_num} timed out")
        return "Step timed out."
    except Exception as e:
        safe_log(f"!!! [PLAN_RUNNER] Step {step_num} error: {e}")
        return f"Step failed: {str(e)}"


def run_autonomous(agent_id, task, api_key, provider, agents_info=""):
    """
    Phase 1: Generate the plan only.
    """
    safe_log(f"[STATUS:{agent_id}] Autonomous planning activated")
    steps = generate_plan(task, agent_id, api_key, provider, agents_info)
    if steps:
        save_plan_md(steps, task, agent_id)
    return steps

def run_execution_loop(agent_id, task, api_key, provider):
    """
    Phase 2: Actual step-by-step execution loop.
    """
    safe_log(f"[STATUS:{agent_id}] Autonomous execution loop started")
    
    # CLEAR VOLATILE LEDGER: Start with a fresh slate for the new task
    volatile_path = os.path.join(AGENTS_CODE_DIR, "volatile_findings.json")
    if os.path.exists(volatile_path):
        try:
            os.remove(volatile_path)
            safe_log(f"--- [CLEANUP] Volatile ledger cleared for new task.")
        except: pass

    # Load steps from plan.md to ensure consistency with what the user saw
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_id)
    plan_path = os.path.join(agent_dir, "plan.md")
    
    steps = []
    if os.path.exists(plan_path):
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                for line in f:
                    # Match numbered list items: "1. Step description"
                    match = re.match(r'^\d+\.\s+(.*)$', line.strip())
                    if match:
                        steps.append(match.group(1).strip())
        except Exception as e:
            safe_log(f"!!! [PLAN_RUNNER] Error reading plan.md: {e}")

    if not steps:
        return "Failed to locate an execution plan. Please try generating the plan again."

    accumulated_context = ""
    step_results = []

    # Detect if last step is a PDF generation step
    PDF_KEYWORDS = ["report_generation", "pdf", "create a pdf", "generate a pdf"]
    last_step_lower = steps[-1].lower()
    last_is_pdf = any(w in last_step_lower for w in PDF_KEYWORDS)

    for i, step in enumerate(steps, 1):
        is_last = (i == len(steps))
        is_pdf = is_last and last_is_pdf

        result = execute_step(
            i, len(steps), step, agent_id,
            accumulated_context, api_key, provider,
            is_pdf_step=is_pdf
        )
        step_results.append((step, result))
        if not is_pdf:
            accumulated_context += f"\n### Step {i}: {step}\n{result}\n"

    # Final PDF compilation logic
    if last_is_pdf:
        final_response = step_results[-1][1]
    else:
        safe_log(f"[STATUS:{agent_id}] No PDF step in plan — adding PDF generation...")
        result = execute_step(
            len(steps) + 1, len(steps) + 1,
            f"Create a PDF report for: {task}",
            agent_id,
            accumulated_context, api_key, provider,
            is_pdf_step=True
        )
        final_response = result

    safe_log(f"[STATUS:{agent_id}] Autonomous task complete")
    
    # FINAL CLEANUP: Delete volatile findings as requested by user
    if os.path.exists(volatile_path):
        try:
            os.remove(volatile_path)
            safe_log(f"--- [CLEANUP] Volatile ledger deleted after task completion.")
        except: pass

    return final_response
