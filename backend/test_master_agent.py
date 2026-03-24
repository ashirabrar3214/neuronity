"""
Test script for MasterAgent - sends a prompt via the /chat endpoint,
auto-answers clarification questions, captures the full SSE stream,
measures timing per turn, and prints an analysis.

Usage:
    cd backend
    python test_master_agent.py
"""

import requests
import json
import time
import os
import sys
import io
from dotenv import load_dotenv

# Fix Windows encoding
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

load_dotenv()

# -- Config -------------------------------------------------------------------
BASE_URL = "http://localhost:8000"
AGENT_ID = "agent-bot-1774318073729"   # MasterAgent
API_KEY  = os.getenv("GEMINI_API_KEY", "")

INITIAL_PROMPT = (
    "Make a report on the Iran war. "
    "Scope: Cover the Iran-Iraq war (1980-1988), recent Iran-Israel tensions (2024-2025), and proxy conflicts. "
    "Format: Detailed text report, approximately 1500 words. "
    "Focus: Key events, casualties, geopolitical impact, and current situation. "
    "Do NOT ask me any clarifying questions - all details are provided above. Proceed directly with research."
)

# Fallback answers for clarification / search failure
CLARIFICATION_ANSWER = (
    "I already provided all details. Scope: Iran-Iraq war + Iran-Israel tensions + proxy conflicts. "
    "Format: 1500 word text report. Focus: events, casualties, geopolitics, current situation. "
    "Do NOT ask more questions. Proceed immediately with web_search and report generation."
)

SEARCH_FAIL_ANSWER = (
    "Yes, proceed with generating the report using your training knowledge. "
    "Do not attempt more web searches. Generate the full 1500 word report now."
)

MAX_TURNS = 5  # safety cap
# -----------------------------------------------------------------------------


def stream_chat(message, turn_num):
    """Send a message to the agent and collect all SSE events. Returns dict with results."""
    payload = {
        "agent_id": AGENT_ID,
        "message": message,
        "mode": "work",
        "api_key": API_KEY,
        "provider": "Gemini",
    }

    print(f"\n{'='*70}")
    print(f"  TURN {turn_num}")
    print(f"  Sending: {message[:100]}{'...' if len(message)>100 else ''}")
    print(f"{'='*70}")

    t_start = time.time()
    t_first = None

    try:
        resp = requests.post(
            f"{BASE_URL}/chat",
            json=payload,
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("\n[ERROR] Cannot connect to backend. Start it with:")
        print("        cd backend && uvicorn interpreter:app --port 8000")
        return None
    except Exception as e:
        print(f"\n[ERROR] Request failed: {e}")
        return None

    events = []
    thinking_tokens = []
    actions = []
    action_results = []
    response_text = ""
    errors = []

    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        raw = line[6:].strip()
        if raw == "[DONE]":
            break

        now = time.time()
        if t_first is None:
            t_first = now

        try:
            evt = json.loads(raw)
        except json.JSONDecodeError:
            continue

        evt["_ts"] = now
        events.append(evt)
        etype = evt.get("type", "")
        content = evt.get("content", "")

        if etype == "thought_token":
            thinking_tokens.append(content)
        elif etype == "action":
            actions.append({"content": content, "ts": now})
            print(f"  [ACTION]  {content[:120]}")
        elif etype == "action_result":
            action_results.append({"content": content, "ts": now})
            preview = content[:150].replace("\n", " ")
            print(f"  [RESULT]  {preview}...")
        elif etype == "response":
            response_text += content
        elif etype == "error":
            errors.append(content)
            print(f"  [ERROR]   {content}")
        elif etype == "iteration_start":
            print(f"\n  -- Iteration {content} --")

    t_end = time.time()

    return {
        "events": events,
        "thinking": "".join(thinking_tokens),
        "actions": actions,
        "action_results": action_results,
        "response": response_text,
        "errors": errors,
        "total_time": t_end - t_start,
        "ttft": (t_first - t_start) if t_first else None,
        "t_start": t_start,
    }


def classify_response(text):
    """Classify: 'question' (clarification), 'search_fail' (tool error), or 'answer' (real response)."""
    lower = text.lower()
    # Search failure
    if "failed" in lower and ("search" in lower or "module" in lower):
        if "?" in text:
            return "search_fail"
    # Clarification question
    indicators = ["could you", "can you", "please clarify", "would you like",
                  "what specific", "what is your", "which", "do you want",
                  "let me know", "before i proceed", "prefer"]
    q_marks = text.count("?")
    hits = sum(1 for i in indicators if i in lower)
    if q_marks >= 2 or hits >= 2:
        return "question"
    return "answer"


def run_test():
    print("=" * 70)
    print("  MasterAgent Multi-Turn Test")
    print(f"  Prompt : {INITIAL_PROMPT}")
    print(f"  Agent  : {AGENT_ID}")
    print(f"  API Key: {'present' if API_KEY else 'MISSING'}")
    print("=" * 70)

    all_turns = []
    t_global_start = time.time()
    current_message = INITIAL_PROMPT
    clarification_sent = False
    search_fail_sent = False

    for turn in range(1, MAX_TURNS + 1):
        result = stream_chat(current_message, turn)
        if result is None:
            break
        all_turns.append(result)

        resp = result["response"]
        print(f"\n  Response preview ({len(resp)} chars):")
        for line in resp[:400].split("\n"):
            print(f"    | {line}")
        if len(resp) > 400:
            print(f"    | ... ({len(resp)-400} more chars)")

        classification = classify_response(resp)

        if classification == "question" and not clarification_sent:
            print("\n  >> Agent asked for clarification. Auto-answering...")
            current_message = CLARIFICATION_ANSWER
            clarification_sent = True
            continue
        elif classification == "search_fail" and not search_fail_sent:
            print("\n  >> Search failed. Telling agent to use training knowledge...")
            current_message = SEARCH_FAIL_ANSWER
            search_fail_sent = True
            continue
        else:
            break

    t_global_end = time.time()

    # -- Final Analysis -------------------------------------------------------
    print("\n\n")
    print("#" * 70)
    print("  FINAL ANALYSIS")
    print("#" * 70)

    total_wall = t_global_end - t_global_start
    total_thinking = sum(len(t["thinking"]) for t in all_turns)
    total_actions = sum(len(t["actions"]) for t in all_turns)
    total_errors = sum(len(t["errors"]) for t in all_turns)
    total_iterations = sum(
        sum(1 for e in t["events"] if e.get("type") == "iteration_start")
        for t in all_turns
    )

    print(f"\n  TIMING")
    print(f"    Total wall time      : {total_wall:.2f}s")
    for i, t in enumerate(all_turns, 1):
        ttft_str = f"{t['ttft']:.2f}s" if t['ttft'] else "N/A"
        print(f"    Turn {i} time           : {t['total_time']:.2f}s  (TTFT: {ttft_str})")

    print(f"\n  ACTIVITY")
    print(f"    Turns                : {len(all_turns)}")
    print(f"    Total iterations     : {total_iterations}")
    print(f"    Total tool calls     : {total_actions}")
    print(f"    Total errors         : {total_errors}")
    print(f"    Thinking chars       : {total_thinking}")

    # Tool call timeline
    if any(t["actions"] for t in all_turns):
        print(f"\n  TOOL CALL TIMELINE")
        for ti, turn in enumerate(all_turns, 1):
            for j, a in enumerate(turn["actions"], 1):
                elapsed = a["ts"] - all_turns[0]["t_start"]
                print(f"    T{ti}.{j} [{elapsed:.1f}s] {a['content'][:100]}")

    # Event breakdown across all turns
    type_counts = {}
    for t in all_turns:
        for e in t["events"]:
            k = e.get("type", "unknown")
            type_counts[k] = type_counts.get(k, 0) + 1
    print(f"\n  EVENT BREAKDOWN")
    for k, v in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {k:25s}: {v}")

    # Final response
    final_resp = all_turns[-1]["response"]
    print(f"\n  FINAL RESPONSE ({len(final_resp)} chars)")
    print("-" * 70)
    print(final_resp)
    print("-" * 70)

    if total_errors:
        print(f"\n  ALL ERRORS:")
        for t in all_turns:
            for err in t["errors"]:
                print(f"    - {err}")

    print("\n" + "#" * 70)
    print("  TEST COMPLETE")
    print("#" * 70)


if __name__ == "__main__":
    run_test()
