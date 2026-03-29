"""
Full integration test for the HITL system.

Runs the real hitl_loop() with real LLM calls and web search,
printing clean output to terminal. Backend debug logs go to a file.

Usage:
  python HITL/test_integration.py
  python HITL/test_integration.py --effort 7 --expertise 8 --goal "research AI regulation in EU"
  python HITL/test_integration.py --cleanup
"""
import sys
import os
import io
import json
import asyncio
import argparse
import shutil
import time

# Wire up paths
BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND_DIR)

# Load .env from backend
from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

# Now import engine components
from graph.hitl_engine import hitl_loop
from graph.hitl_intervention import InterventionTracker

# -- Colors (ASCII safe for Windows) ------------------------------------------

try:
    from colorama import init, Fore, Style
    init()
    GREEN   = Fore.GREEN
    RED     = Fore.RED
    YELLOW  = Fore.YELLOW
    CYAN    = Fore.CYAN
    MAGENTA = Fore.MAGENTA
    DIM     = Style.DIM
    BOLD    = Style.BRIGHT
    RESET   = Style.RESET_ALL
except ImportError:
    GREEN = RED = YELLOW = CYAN = MAGENTA = DIM = BOLD = RESET = ""

# Test agent ID -- isolated from your real agents
TEST_AGENT_ID = "hitl_test_agent"
AGENTS_CODE_DIR = os.path.join(BACKEND_DIR, "agents_code")
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


def setup_test_agent():
    """Create a minimal agent directory for the test agent."""
    agent_dir = os.path.join(AGENTS_CODE_DIR, TEST_AGENT_ID)
    os.makedirs(agent_dir, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    personality = {
        "name": "HITL Test Agent",
        "description": "A research agent used for testing the HITL intervention system.",
        "responsibility": "Deep web research with human steering.",
        "provider": "gemini",
    }
    with open(os.path.join(agent_dir, "personality.json"), "w") as f:
        json.dump(personality, f, indent=2)

    with open(os.path.join(agent_dir, "prompt.md"), "w") as f:
        f.write(
            "You are a research agent. Search the web thoroughly, "
            "extract facts, and produce analytical output. "
            "Use web_search and scrape_website tools."
        )

    with open(os.path.join(agent_dir, "history.json"), "w") as f:
        json.dump([], f)

    # Clear any stale knowledge store (KnowledgeStore saves to knowledge/ subdir)
    knowledge_dir = os.path.join(agent_dir, "knowledge")
    if os.path.exists(knowledge_dir):
        shutil.rmtree(knowledge_dir, ignore_errors=True)

    # Also clear legacy locations (root-level files from older runs)
    for fname in ("graph.json", "ledger.json", "scratchpad.json"):
        fpath = os.path.join(agent_dir, fname)
        if os.path.exists(fpath):
            os.remove(fpath)

    return agent_dir


def cleanup_test_agent():
    """Remove test agent data."""
    agent_dir = os.path.join(AGENTS_CODE_DIR, TEST_AGENT_ID)
    if os.path.exists(agent_dir):
        shutil.rmtree(agent_dir, ignore_errors=True)
    print("Test agent cleaned up.")


def build_test_state(goal, effort, expertise):
    """Build the state dict that hitl_loop expects."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        print(f"{RED}ERROR: No GEMINI_API_KEY in backend/.env{RESET}")
        sys.exit(1)

    return {
        "agent_id": TEST_AGENT_ID,
        "agent_name": "HITL Test Agent",
        "agent_type": "worker",
        "permissions": ["web_search", "scrape_website"],
        "connected_agents": [],
        "working_dir": os.path.join(AGENTS_CODE_DIR, TEST_AGENT_ID),
        "system_prompt": "",
        "mode": "work",
        "is_auto_step": False,
        "iteration": 0,
        "max_iterations": 10,
        "api_key": api_key,
        "session_id": "",
        "goal": goal,
        "user_effort": effort,
        "human_expertise": expertise,
        "project_size": "small",
        "messages": [],
        "plan_iterations": 0,
        "max_plan_iterations": 50,
        "current_steps": [],
        "iteration_summaries": [],
        "planner_decision": "",
        "consecutive_clarifications": 0,
        "planner_response": "",
        "planner_question": "",
        "hitl_phase": "",
        "hitl_session_id": "",
        "current_prompt_md": "",
        "workflow_agents": {},
    }


# -- SSE event display --------------------------------------------------------

def display_event(event):
    """Pretty-print an SSE event to the terminal."""
    etype = event.get("type", "")
    content = str(event.get("content", ""))

    if etype == "phase":
        print(f"\n  {BOLD}{MAGENTA}--- {content} ---{RESET}")

    elif etype == "thought":
        print(f"  {DIM}  {content[:120]}{RESET}")

    elif etype == "action":
        print(f"  {CYAN}  >> {content}{RESET}")

    elif etype == "action_result":
        preview = content[:120] + ("..." if len(content) > 120 else "")
        print(f"  {DIM}     {preview}{RESET}")

    elif etype == "response":
        print(f"\n{GREEN}  {'=' * 56}")
        print(f"  AGENT RESPONSE")
        print(f"  {'=' * 56}{RESET}")
        # Indent each line
        for line in content.split("\n"):
            print(f"  {line}")
        print(f"{GREEN}  {'=' * 56}{RESET}\n")

    elif etype == "hitl_question":
        conf = event.get("confidence", "?")
        score = event.get("intervention_score", "?")
        reason = event.get("intervention_reason", "")
        print(f"\n{YELLOW}  {'=' * 56}")
        print(f"  INTERVENTION  conf={conf}  score={score}")
        if reason:
            print(f"  Why: {reason}")
        print(f"  {'=' * 56}{RESET}")
        for line in content.split("\n"):
            print(f"  {line}")
        print(f"{YELLOW}  {'=' * 56}{RESET}\n")

    elif etype == "hitl_decision":
        try:
            d = json.loads(content)
            intervene = d.get("should_intervene", False)
            marker = f"{RED}>> ASK USER{RESET}" if intervene else f"{GREEN}PASS{RESET}"
            print(f"  {DIM}  [HITL] conf={d.get('confidence')}  "
                  f"score={d.get('score'):.2f}  thr={d.get('threshold'):.2f}  "
                  f"type={d.get('step_type')}  {marker}{RESET}")
            if intervene:
                print(f"  {DIM}         reason: {d.get('reason', '')}{RESET}")
        except Exception:
            pass

    elif etype == "error":
        print(f"  {RED}  ERROR: {content}{RESET}")

    elif etype == "thought_token":
        # Thinking tokens from planner model — show inline
        print(f"{DIM}{content}{RESET}", end="", flush=True)

    # Silently skip: iteration_start, done, padding


def parse_sse_line(line):
    """Parse a single SSE 'data: {...}' line into a dict."""
    line = line.strip()
    if not line.startswith("data: "):
        return None
    payload = line[6:]
    if payload == "[DONE]":
        return {"type": "done"}
    try:
        return json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return None


# -- Stdout redirect to suppress backend noise --------------------------------

class StdoutSplitter:
    """Redirects stdout so backend print() goes to a log file,
    while our display_event/print calls go to the real terminal."""
    def __init__(self, real_stdout, log_file):
        self.real = real_stdout
        self.log = log_file
        self._allow_real = False

    def write(self, text):
        if self._allow_real:
            self.real.write(text)
        else:
            # Backend noise -> log file only
            self.log.write(text)

    def flush(self):
        self.real.flush()
        self.log.flush()

    def real_print(self, *args, **kwargs):
        """Print to the actual terminal."""
        self._allow_real = True
        print(*args, **kwargs)
        self._allow_real = False


# -- Main loop ----------------------------------------------------------------

async def run_session(goal, effort, expertise):
    """Run a full HITL session, handling checkpoints interactively."""

    setup_test_agent()

    log_path = os.path.join(LOG_DIR, "integration_debug.log")
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = open(log_path, "w", encoding="utf-8")
    splitter = StdoutSplitter(sys.stdout, log_file)

    # Helper to print to real terminal
    def out(*args, **kwargs):
        splitter.real_print(*args, **kwargs)

    def show_event(event):
        splitter._allow_real = True
        display_event(event)
        splitter._allow_real = False

    out(f"\n{BOLD}+----------------------------------------------------------+")
    out(f"|  HITL Integration Test                                    |")
    out(f"+----------------------------------------------------------+{RESET}")
    out(f"  Goal:      {goal}")
    out(f"  Effort:    {effort}/10")
    out(f"  Expertise: {expertise}/10")
    out(f"  Debug log: {log_path}")
    out("")
    current_goal = goal
    turn = 0

    # Redirect stdout so backend print() goes to log
    old_stdout = sys.stdout
    sys.stdout = splitter

    try:
        while True:
            turn += 1
            out(f"{BOLD}  >> Turn {turn}{RESET}\n")

            state = build_test_state(current_goal, effort, expertise)
            got_checkpoint = False
            t_start = time.time()

            try:
                async for sse_line in hitl_loop(state):
                    event = parse_sse_line(sse_line)
                    if not event:
                        continue

                    show_event(event)

                    if event.get("type") in ("response", "hitl_question"):
                        got_checkpoint = True

                    if event.get("type") == "done":
                        break
            except asyncio.CancelledError:
                out(f"\n  {DIM}  (Request cancelled){RESET}")
                break
            except Exception as e:
                out(f"\n  {RED}  Engine error: {str(e)[:120]}{RESET}")
                break

            elapsed = time.time() - t_start
            out(f"\n  {DIM}  (Turn {turn} took {elapsed:.1f}s){RESET}")

            if not got_checkpoint:
                out(f"\n  {DIM}  (Engine finished without output){RESET}")
                break

            # Ask user what to do next
            out(f"\n{YELLOW}  What next?{RESET}")
            out(f"    Type direction to steer  |  Enter = continue  |  q = quit")
            out("")

            # Restore stdout for input()
            sys.stdout = old_stdout
            try:
                user_input = input(f"  {BOLD}You> {RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n  Session ended.")
                break
            finally:
                sys.stdout = splitter

            if user_input.lower() in ("q", "quit", "exit"):
                out(f"\n  Session ended by user.")
                break

            # User direction becomes the next "goal" which hitl_loop receives.
            # The engine detects the active CHECKPOINT session and resumes from there.
            if user_input:
                current_goal = user_input
            else:
                # Empty = keep going with whatever the agent thinks is best
                current_goal = "continue with all directions, use your best judgment"

    except KeyboardInterrupt:
        pass  # clean exit
    finally:
        sys.stdout = old_stdout
        log_file.close()
        print(f"\n{BOLD}  Done ({turn} turns). Debug log: {log_path}{RESET}")
        print(f"  Cleanup: python HITL/test_integration.py --cleanup\n")


def main():
    parser = argparse.ArgumentParser(description="HITL Integration Test")
    parser.add_argument("--goal", "-g", type=str, default=None,
                        help="Research goal/question")
    parser.add_argument("--effort", "-e", type=int, default=None,
                        help="Human effort slider (1-10)")
    parser.add_argument("--expertise", "-x", type=int, default=None,
                        help="Human expertise slider (1-10)")
    parser.add_argument("--cleanup", action="store_true",
                        help="Remove test agent data and exit")
    args = parser.parse_args()

    if args.cleanup:
        cleanup_test_agent()
        return

    # Interactive prompts for missing args
    goal = args.goal
    if not goal:
        print(f"\n{BOLD}HITL Integration Test{RESET}")
        print(f"{DIM}Runs the real HITL engine with LLM + web search.{RESET}\n")
        goal = input(f"  Research goal: ").strip()
        if not goal:
            print("No goal provided.")
            return

    effort = args.effort
    if effort is None:
        effort = int(input(f"  Human effort   (1-10): ") or "5")

    expertise = args.expertise
    if expertise is None:
        expertise = int(input(f"  Human expertise (1-10): ") or "5")

    effort = max(1, min(10, effort))
    expertise = max(1, min(10, expertise))

    try:
        asyncio.run(run_session(goal, effort, expertise))
    except KeyboardInterrupt:
        print(f"\n  Session interrupted.")


if __name__ == "__main__":
    main()
