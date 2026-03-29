"""
CLI Test Harness for the Smart HITL Intervention Algorithm.

Run:  python HITL/test_hitl.py

Three modes:
  1) Simulation  -- auto-runs a fake 25-step research session, prints a table
  2) Interactive  -- you play the agent, entering confidence per step
  3) Sweep        -- runs many effort/expertise combos, shows summary stats

No API keys, no UI, no network -- pure algorithm testing.
"""
import sys
import os
import random

# Add backend to path so we can import the algorithm
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from graph.hitl_intervention import InterventionTracker, compute_intervention, StepType

# -- Pretty printing helpers --------------------------------------------------

try:
    from colorama import init, Fore, Style
    init()
    GREEN  = Fore.GREEN
    RED    = Fore.RED
    YELLOW = Fore.YELLOW
    CYAN   = Fore.CYAN
    DIM    = Style.DIM
    BOLD   = Style.BRIGHT
    RESET  = Style.RESET_ALL
except ImportError:
    GREEN = RED = YELLOW = CYAN = DIM = BOLD = RESET = ""


def colored_bool(val):
    return f"{RED}ASK{RESET}" if val else f"{GREEN}PASS{RESET}"


def confidence_bar(conf: int, width: int = 20) -> str:
    filled = int(conf / 100 * width)
    bar = "#" * filled + "-" * (width - filled)
    if conf < 40:
        return f"{RED}{bar}{RESET}"
    elif conf < 70:
        return f"{YELLOW}{bar}{RESET}"
    return f"{GREEN}{bar}{RESET}"


def print_header(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {BOLD}{title}{RESET}")
    print(f"{'=' * 60}")


def print_decision_row(d: dict, show_reason: bool = True):
    step = d.get("step_number", "?")
    conf = d["confidence"]
    stype = d["step_type"]
    score = d["score"]
    thresh = d["threshold"]
    intervene = d["should_intervene"]

    marker = colored_bool(intervene)
    bar = confidence_bar(conf)

    line = (
        f"  Step {step:>2}  {bar} {conf:>3}%  "
        f"{CYAN}{stype:<14}{RESET}  "
        f"score={score:.2f}  thr={thresh:.2f}  {marker}"
    )
    print(line)
    if show_reason and intervene:
        print(f"           {DIM}-> {d['reason']}{RESET}")


# -- Simulation scenarios ----------------------------------------------------─

# Each scenario is a list of (confidence, step_type) tuples representing
# what a real agent session might look like.

SCENARIOS = {
    "smooth_research": {
        "description": "Agent finds good sources, stays confident throughout",
        "steps": [
            (85, "direction"),
            (90, "tool_choice"),
            (88, "analysis"),
            (92, "analysis"),
            (87, "synthesis"),
            (90, "tool_choice"),
            (85, "analysis"),
            (91, "analysis"),
            (88, "fact_check"),
            (95, "synthesis"),
        ],
    },
    "rocky_start": {
        "description": "Agent struggles early, finds footing mid-way",
        "steps": [
            (40, "direction"),
            (35, "tool_choice"),
            (30, "analysis"),
            (45, "direction"),
            (55, "tool_choice"),
            (65, "analysis"),
            (72, "analysis"),
            (80, "fact_check"),
            (85, "synthesis"),
            (90, "synthesis"),
        ],
    },
    "contradiction_found": {
        "description": "Agent finds conflicting sources mid-research",
        "steps": [
            (80, "direction"),
            (85, "tool_choice"),
            (78, "analysis"),
            (82, "analysis"),
            (45, "contradiction"),    # <- sources conflict
            (38, "fact_check"),
            (42, "direction"),        # which path to trust?
            (70, "tool_choice"),
            (75, "analysis"),
            (85, "synthesis"),
        ],
    },
    "deep_unknown": {
        "description": "Niche topic, agent is uncertain the whole way",
        "steps": [
            (30, "direction"),
            (25, "tool_choice"),
            (35, "analysis"),
            (20, "analysis"),
            (28, "direction"),
            (15, "fact_check"),
            (30, "tool_choice"),
            (40, "analysis"),
            (35, "prioritize"),
            (45, "synthesis"),
        ],
    },
    "user_redirect": {
        "description": "Agent is confident but hits a point where direction matters",
        "steps": [
            (85, "tool_choice"),
            (88, "analysis"),
            (82, "analysis"),
            (90, "synthesis"),
            (50, "direction"),        # <- could go multiple ways
            (55, "prioritize"),       # <- what does user care about?
            (75, "tool_choice"),
            (80, "analysis"),
            (88, "analysis"),
            (92, "synthesis"),
        ],
    },
}


# -- Mode 1: Simulation ------------------------------------------------------

def run_simulation(effort: int, expertise: int, scenario_name: str | None = None):
    print_header(f"SIMULATION  |  effort={effort}  expertise={expertise}")

    scenarios = [scenario_name] if scenario_name else list(SCENARIOS.keys())

    for name in scenarios:
        scenario = SCENARIOS[name]
        print(f"\n  {BOLD}Scenario: {name}{RESET}")
        print(f"  {DIM}{scenario['description']}{RESET}\n")

        tracker = InterventionTracker(human_effort=effort, human_expertise=expertise)

        for conf, stype in scenario["steps"]:
            decision = tracker.record_step(conf, stype)
            print_decision_row(decision)

        asks = sum(1 for d in tracker.history if d["should_intervene"])
        total = len(tracker.history)
        print(f"\n  {BOLD}Result: {asks}/{total} interventions{RESET}")
        print(f"  {DIM}(Agent asked the user {asks} times in {total} steps){RESET}")


# -- Mode 2: Interactive ------------------------------------------------------

def run_interactive(effort: int, expertise: int):
    print_header(f"INTERACTIVE  |  effort={effort}  expertise={expertise}")
    print(f"  Enter confidence (0-100) and step type for each step.")
    print(f"  Step types: direction, contradiction, fact_check, prioritize,")
    print(f"              tool_choice, analysis, synthesis")
    print(f"  Format: <confidence> [type]   (type defaults to 'analysis')")
    print(f"  Type 'q' to quit.\n")

    tracker = InterventionTracker(human_effort=effort, human_expertise=expertise)

    while True:
        try:
            raw = input(f"  {CYAN}Step {tracker.total_steps + 1}>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if raw.lower() in ("q", "quit", "exit"):
            break

        parts = raw.split()
        if not parts:
            continue

        try:
            conf = int(parts[0])
        except ValueError:
            print(f"  {RED}Enter a number 0-100{RESET}")
            continue

        stype = parts[1] if len(parts) > 1 else "analysis"

        decision = tracker.record_step(conf, stype)
        print_decision_row(decision)

        if decision["should_intervene"]:
            print(f"  {YELLOW}>>> AGENT WOULD ASK THE USER HERE <<<{RESET}")
            response = input(f"  {YELLOW}Your direction (or Enter to continue): {RESET}").strip()
            if response:
                print(f"  {DIM}(User said: {response} -- agent continues with new direction){RESET}")

    # Summary
    asks = sum(1 for d in tracker.history if d["should_intervene"])
    print(f"\n  {BOLD}Session: {asks}/{tracker.total_steps} interventions{RESET}")


# -- Mode 3: Sweep ------------------------------------------------------------

def run_sweep():
    print_header("PARAMETER SWEEP -- intervention count per scenario")
    print(f"  Shows how many times the agent asks across different effort/expertise combos.\n")

    efforts    = [1, 3, 5, 7, 10]
    expertises = [1, 3, 5, 7, 10]

    for name, scenario in SCENARIOS.items():
        print(f"  {BOLD}{name}{RESET}: {scenario['description']}")
        print(f"  {'':>14}", end="")
        for exp in expertises:
            print(f"  exp={exp}", end="")
        print()

        for eff in efforts:
            print(f"  effort={eff:>2}   ", end="")
            for exp in expertises:
                tracker = InterventionTracker(human_effort=eff, human_expertise=exp)
                for conf, stype in scenario["steps"]:
                    tracker.record_step(conf, stype)
                asks = sum(1 for d in tracker.history if d["should_intervene"])
                total = len(scenario["steps"])

                # Color code
                if asks == 0:
                    print(f"  {GREEN}{asks:>2}/{total}{RESET} ", end="")
                elif asks <= 2:
                    print(f"  {YELLOW}{asks:>2}/{total}{RESET} ", end="")
                else:
                    print(f"  {RED}{asks:>2}/{total}{RESET} ", end="")
            print()
        print()


# -- Mode 4: Quick unit-test sanity checks ------------------------------------

def run_tests():
    print_header("SANITY CHECKS")
    passed = 0
    failed = 0

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            print(f"  {GREEN}OK{RESET} {name}")
            passed += 1
        else:
            print(f"  {RED}FAIL{RESET} {name}")
            failed += 1

    # 1. Autopilot (effort=1) should never ask when confidence > 35
    r = compute_intervention(confidence=60, human_effort=1, human_expertise=8, step_type="direction")
    check("Autopilot (effort=1, conf=60) -> no intervention", not r["should_intervene"])

    # 2. Autopilot still asks when critically uncertain
    r = compute_intervention(confidence=15, human_effort=1, human_expertise=8, step_type="direction")
    check("Autopilot (effort=1, conf=15) -> DOES intervene", r["should_intervene"])

    # 3. Surgical (effort=10) should ask even with moderate uncertainty
    r = compute_intervention(confidence=55, human_effort=10, human_expertise=7, step_type="direction")
    check("Surgical (effort=10, conf=55, direction) -> intervenes", r["should_intervene"])

    # 4. High confidence + high effort -> no intervention (nothing to ask about)
    r = compute_intervention(confidence=95, human_effort=10, human_expertise=10, step_type="analysis")
    check("High conf (95) + surgical -> no intervention", not r["should_intervene"])

    # 5. Contradiction with expert -> should ask
    r = compute_intervention(confidence=45, human_effort=5, human_expertise=8, step_type="contradiction")
    check("Contradiction (conf=45, expert=8) -> intervenes", r["should_intervene"])

    # 6. Tool choice (agent knows best) -> less likely to ask
    r = compute_intervention(confidence=55, human_effort=5, human_expertise=5, step_type="tool_choice")
    check("Tool choice (conf=55, balanced) -> no intervention", not r["should_intervene"])

    # 7. Novice user + moderate confidence -> don't bother asking
    r = compute_intervention(confidence=50, human_effort=5, human_expertise=2, step_type="analysis")
    check("Novice (expertise=2, conf=50) -> no intervention", not r["should_intervene"])

    # 8. Expert + low conf on fact_check -> ask
    r = compute_intervention(confidence=30, human_effort=5, human_expertise=9, step_type="fact_check")
    check("Expert (exp=9) + low conf fact_check -> intervenes", r["should_intervene"])

    # 9. Fatigue: after many interventions, threshold rises
    r1 = compute_intervention(confidence=45, human_effort=7, human_expertise=7,
                              step_type="direction", interventions_so_far=0)
    r2 = compute_intervention(confidence=45, human_effort=7, human_expertise=7,
                              step_type="direction", interventions_so_far=6)
    check("Fatigue: threshold rises after 6 interventions", r2["threshold"] > r1["threshold"])

    # 10. Staleness: long gap since last ask -> threshold drops
    r1 = compute_intervention(confidence=55, human_effort=5, human_expertise=5,
                              step_type="direction", steps_since_last=1)
    r2 = compute_intervention(confidence=55, human_effort=5, human_expertise=5,
                              step_type="direction", steps_since_last=8)
    check("Staleness: threshold drops after 8 steps without asking", r2["threshold"] < r1["threshold"])

    # 11. Confidence trend: tracker detects sustained low confidence
    tracker = InterventionTracker(human_effort=5, human_expertise=7)
    # Feed 3 low-confidence steps
    tracker.record_step(30, "analysis")
    tracker.record_step(35, "analysis")
    d3 = tracker.record_step(40, "direction")
    # The trend boost should make this more likely to trigger
    check("Trend: 3 low-conf steps boosts score", d3["score"] > 0.3)

    print(f"\n  {BOLD}Results: {passed} passed, {failed} failed{RESET}")
    if failed:
        # Print details for failed checks
        pass
    return failed == 0


# -- CLI entry point ----------------------------------------------------------

def main():
    print(f"""
{BOLD}+----------------------------------------------------------+
|          HITL Intervention Algorithm Tester               |
+----------------------------------------------------------+{RESET}

  Modes:
    1) {CYAN}simulate{RESET}    -- Run pre-built scenarios with your slider settings
    2) {CYAN}interactive{RESET} -- Step-by-step: you enter confidence, see decisions
    3) {CYAN}sweep{RESET}       -- Run all effort/expertise combos, see the matrix
    4) {CYAN}test{RESET}        -- Run sanity checks on the algorithm
    """)

    mode = input(f"  {BOLD}Choose mode (1-4): {RESET}").strip()

    if mode in ("1", "simulate"):
        effort    = int(input(f"  Human effort   (1-10): ") or "5")
        expertise = int(input(f"  Human expertise (1-10): ") or "5")
        print(f"\n  Available scenarios: {', '.join(SCENARIOS.keys())}")
        scenario = input(f"  Scenario (or Enter for all): ").strip() or None
        run_simulation(effort, expertise, scenario)

    elif mode in ("2", "interactive"):
        effort    = int(input(f"  Human effort   (1-10): ") or "5")
        expertise = int(input(f"  Human expertise (1-10): ") or "5")
        run_interactive(effort, expertise)

    elif mode in ("3", "sweep"):
        run_sweep()

    elif mode in ("4", "test"):
        run_tests()

    else:
        print(f"  {RED}Unknown mode. Run again.{RESET}")


if __name__ == "__main__":
    # Allow quick CLI args:  python test_hitl.py test
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "test":
            success = run_tests()
            sys.exit(0 if success else 1)
        elif cmd == "sweep":
            run_sweep()
            sys.exit(0)
        elif cmd == "simulate":
            effort = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            expertise = int(sys.argv[3]) if len(sys.argv) > 3 else 5
            scenario = sys.argv[4] if len(sys.argv) > 4 else None
            run_simulation(effort, expertise, scenario)
            sys.exit(0)
    else:
        main()
