"""
Test script for Deep Web Researcher agent.

Sends a research prompt via /chat, auto-steers through clarifications,
tracks tool usage (find_sources + scrape_website vs web_search),
and verifies the final report quality.

Usage:
    cd backend
    python test_deep_researcher.py
"""

import requests
import json
import time
import os
import sys
import io
import re
import glob
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
API_KEY  = os.getenv("GEMINI_API_KEY", "")

# Auto-detect Deep Web Researcher agent ID from agents.json
AGENT_ID = None
_agents_path = os.path.join(os.path.dirname(__file__), "agents.json")
if os.path.exists(_agents_path):
    with open(_agents_path, "r", encoding="utf-8") as _f:
        for _a in json.load(_f):
            if _a.get("specialRole") == "deep-web-researcher":
                AGENT_ID = _a["id"]
                break
if not AGENT_ID:
    AGENT_ID = "agent-bot-1774395688359"  # fallback

INITIAL_PROMPT = (
    "Research the Iran-Israel military conflict in 2025-2026. I need a detailed "
    "intelligence briefing with specific casualty figures, key military operations, "
    "timeline of escalation, international response, and current status."
)

# Steering answers for clarification questions
STEER_ANSWER = (
    "Focus on the military strikes, casualty figures, and international response. "
    "2026 conflict specifically. Cover Iran-Israel tensions, any US involvement, "
    "proxy conflicts, and humanitarian impact. Scrape full articles from multiple "
    "sources. Do NOT ask more questions. Start researching immediately."
)

SEARCH_FAIL_ANSWER = (
    "Try different search terms: 'Iran conflict 2025 2026', 'Iran Israel strikes 2026', "
    "'Middle East escalation 2026'. Scrape whatever sources you can find. "
    "If sites block you, find alternatives. Do not give up."
)

SCRAPE_FAIL_ANSWER = (
    "That site blocked you. Find alternative sources covering the same topic. "
    "Try news agencies like Reuters, AP, Al Jazeera, BBC. Use find_sources with "
    "different search terms, then scrape those instead."
)

MAX_TURNS = 8  # researcher needs more turns for deep research
# -----------------------------------------------------------------------------


def stream_chat(message, turn_num):
    """Send a message and collect all SSE events. Returns dict with results."""
    payload = {
        "agent_id": AGENT_ID,
        "message": message,
        "mode": "work",
        "api_key": API_KEY,
        "provider": "Gemini",
    }

    print(f"\n{'='*70}")
    print(f"  TURN {turn_num}")
    print(f"  Sending: {message[:120]}{'...' if len(message)>120 else ''}")
    print(f"{'='*70}")

    t_start = time.time()
    t_first = None

    try:
        resp = requests.post(
            f"{BASE_URL}/chat",
            json=payload,
            stream=True,
            timeout=600,  # longer timeout for deep research
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
    hitl_question = None  # human-in-the-loop question from ask_user tool

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
            print(f"  [ACTION]  {content[:140]}")
        elif etype == "action_result":
            action_results.append({"content": content, "ts": now})
            preview = content[:180].replace("\n", " ")
            print(f"  [RESULT]  {preview}...")
        elif etype == "response":
            response_text += content
        elif etype == "hitl_question":
            hitl_question = content
            print(f"  [ASK_USER] {content[:200]}")
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
        "hitl_question": hitl_question,
        "errors": errors,
        "total_time": t_end - t_start,
        "ttft": (t_first - t_start) if t_first else None,
        "t_start": t_start,
    }


def classify_response(text):
    """Classify response type for auto-steering."""
    lower = text.lower()

    # Scrape failure - agent reporting blocked sites
    if ("error scraping" in lower or "403" in lower or "blocked" in lower) and "?" in text:
        return "scrape_fail"

    # Search failure
    if "failed" in lower and ("search" in lower or "module" in lower):
        if "?" in text:
            return "search_fail"

    # Clarification question
    indicators = ["could you", "can you", "please clarify", "would you like",
                  "what specific", "what is your", "which", "do you want",
                  "let me know", "before i proceed", "prefer", "should i focus",
                  "military or economic", "which angle", "could you please",
                  "i am unable", "unable to access", "cannot perform"]
    q_marks = text.count("?")
    hits = sum(1 for i in indicators if i in lower)
    if q_marks >= 1 and hits >= 1:
        return "question"
    if hits >= 2:
        return "question"

    return "answer"


def extract_tool_names(actions):
    """Extract tool names from action strings."""
    tools_used = []
    for a in actions:
        content = a["content"].lower()
        if "find_sources" in content:
            tools_used.append("find_sources")
        elif "scrape_website" in content:
            tools_used.append("scrape_website")
        elif "web_search" in content:
            tools_used.append("web_search")
        elif "deep_search" in content:
            tools_used.append("deep_search")
        elif "reflect_and_plan" in content:
            tools_used.append("reflect_and_plan")
        elif "report_generation" in content:
            tools_used.append("report_generation")
        elif "ask_user" in content:
            tools_used.append("ask_user")
        else:
            tools_used.append(content[:50])
    return tools_used


def analyze_report_quality(text):
    """Analyze the quality of the final report."""
    analysis = {}

    analysis["char_count"] = len(text)
    analysis["word_count"] = len(text.split())

    # Count URLs/citations
    urls = re.findall(r'https?://[^\s\)]+', text)
    analysis["url_count"] = len(urls)
    analysis["urls"] = urls[:10]  # first 10

    # Count specific numbers (casualty figures, dates, percentages)
    numbers = re.findall(r'\b\d[\d,\.]+\b', text)
    analysis["number_count"] = len(numbers)

    percentages = re.findall(r'\d+(?:\.\d+)?%', text)
    analysis["percentage_count"] = len(percentages)

    # Check for date references
    date_patterns = re.findall(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b', text, re.IGNORECASE)
    analysis["date_references"] = len(date_patterns)

    # Check for vague vs specific language
    vague_words = ["many", "several", "some", "significant", "numerous", "various"]
    vague_count = sum(len(re.findall(r'\b' + w + r'\b', text.lower())) for w in vague_words)
    analysis["vague_word_count"] = vague_count

    # Check sections/structure
    headers = re.findall(r'^#+\s+.+$', text, re.MULTILINE)
    analysis["section_count"] = len(headers)
    analysis["sections"] = headers[:15]

    return analysis


def run_test():
    print("=" * 70)
    print("  Deep Web Researcher Test")
    print(f"  Prompt : {INITIAL_PROMPT[:80]}...")
    print(f"  Agent  : {AGENT_ID}")
    print(f"  API Key: {'present' if API_KEY else 'MISSING'}")
    print("=" * 70)

    if not API_KEY:
        print("\n[FATAL] No GEMINI_API_KEY found in .env")
        return

    all_turns = []
    all_tools = []
    t_global_start = time.time()
    current_message = INITIAL_PROMPT
    clarification_sent = False
    search_fail_sent = False
    scrape_fail_sent = False

    for turn in range(1, MAX_TURNS + 1):
        result = stream_chat(current_message, turn)
        if result is None:
            break
        all_turns.append(result)

        # Track tools used this turn
        turn_tools = extract_tool_names(result["actions"])
        all_tools.extend(turn_tools)
        if turn_tools:
            print(f"\n  Tools this turn: {', '.join(turn_tools)}")

        # Check for hitl_question (ask_user tool) first — these need an answer
        hitl = result.get("hitl_question")
        if hitl:
            print(f"\n  >> Agent asked via ask_user: {hitl[:150]}")
            if not clarification_sent:
                print("  >> Auto-steering with research scope...")
                current_message = STEER_ANSWER
                clarification_sent = True
                continue
            else:
                # Already steered once, push harder
                print("  >> Already steered. Telling agent to just proceed...")
                current_message = (
                    "Do not ask more questions. You have enough direction. "
                    "Use find_sources to search, then scrape_website on every result. "
                    "Try multiple search terms. Produce the full report."
                )
                continue

        resp = result["response"]
        print(f"\n  Response preview ({len(resp)} chars):")
        for line in resp[:500].split("\n"):
            print(f"    | {line}")
        if len(resp) > 500:
            print(f"    | ... ({len(resp)-500} more chars)")

        classification = classify_response(resp)
        print(f"  Classification: {classification}")

        if classification == "question" and not clarification_sent:
            print("\n  >> Agent asked for clarification. Auto-steering...")
            current_message = STEER_ANSWER
            clarification_sent = True
            continue
        elif classification == "search_fail" and not search_fail_sent:
            print("\n  >> Search failed. Providing alternative terms...")
            current_message = SEARCH_FAIL_ANSWER
            search_fail_sent = True
            continue
        elif classification == "scrape_fail" and not scrape_fail_sent:
            print("\n  >> Scrape blocked. Steering to alternatives...")
            current_message = SCRAPE_FAIL_ANSWER
            scrape_fail_sent = True
            continue
        else:
            # Got a real answer or exhausted retries
            break

    t_global_end = time.time()

    # -- Final Analysis -------------------------------------------------------
    print("\n\n")
    print("#" * 70)
    print("  DEEP WEB RESEARCHER - FINAL ANALYSIS")
    print("#" * 70)

    total_wall = t_global_end - t_global_start
    total_thinking = sum(len(t["thinking"]) for t in all_turns)
    total_actions = sum(len(t["actions"]) for t in all_turns)
    total_errors = sum(len(t["errors"]) for t in all_turns)
    total_iterations = sum(
        sum(1 for e in t["events"] if e.get("type") == "iteration_start")
        for t in all_turns
    )

    # -- Timing --
    print(f"\n  TIMING")
    print(f"    Total wall time      : {total_wall:.2f}s")
    for i, t in enumerate(all_turns, 1):
        ttft_str = f"{t['ttft']:.2f}s" if t['ttft'] else "N/A"
        print(f"    Turn {i} time           : {t['total_time']:.2f}s  (TTFT: {ttft_str})")

    # -- Activity --
    print(f"\n  ACTIVITY")
    print(f"    Turns                : {len(all_turns)}")
    print(f"    Total iterations     : {total_iterations}")
    print(f"    Total tool calls     : {total_actions}")
    print(f"    Total errors         : {total_errors}")
    print(f"    Thinking chars       : {total_thinking}")

    # -- Tool Usage Analysis (KEY METRIC) --
    print(f"\n  TOOL USAGE (Critical Check)")
    tool_counts = {}
    for t in all_tools:
        tool_counts[t] = tool_counts.get(t, 0) + 1
    for tool, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
        print(f"    {tool:25s}: {count}x")

    find_sources_count = tool_counts.get("find_sources", 0)
    scrape_count = tool_counts.get("scrape_website", 0)
    web_search_count = tool_counts.get("web_search", 0)
    deep_search_count = tool_counts.get("deep_search", 0)
    reflect_count = tool_counts.get("reflect_and_plan", 0)
    report_count = tool_counts.get("report_generation", 0)

    print(f"\n  RESEARCHER BEHAVIOR CHECKS")
    # Check 1: Used find_sources (not web_search)
    if find_sources_count > 0 and web_search_count == 0:
        print(f"    [PASS] Used find_sources ({find_sources_count}x) instead of web_search")
    elif find_sources_count > 0 and web_search_count > 0:
        print(f"    [WARN] Used find_sources ({find_sources_count}x) BUT also web_search ({web_search_count}x)")
    elif web_search_count > 0:
        print(f"    [FAIL] Used web_search ({web_search_count}x) instead of find_sources - snippet reliance!")
    else:
        print(f"    [FAIL] No search tools used at all")

    # Check 2: Actually scraped websites
    if scrape_count >= 3:
        print(f"    [PASS] Scraped {scrape_count} websites (target: 3+)")
    elif scrape_count > 0:
        print(f"    [WARN] Only scraped {scrape_count} website(s) (target: 3+)")
    else:
        print(f"    [FAIL] Never scraped any websites - no deep content!")

    # Check 3: Scrape-to-search ratio
    if find_sources_count > 0:
        ratio = scrape_count / find_sources_count
        print(f"    [INFO] Scrape/Search ratio: {ratio:.1f} (ideal: 2.0+)")

    # Check 4: Used reflect_and_plan
    if reflect_count > 0:
        print(f"    [PASS] Used reflect_and_plan ({reflect_count}x) - verified findings")
    else:
        print(f"    [WARN] Never used reflect_and_plan - no self-verification")

    # Check 5: Generated a report
    if report_count > 0:
        print(f"    [PASS] Generated {report_count} report(s)")
    else:
        print(f"    [INFO] No report_generation call (may have reported inline)")

    # -- Tool Call Timeline --
    if any(t["actions"] for t in all_turns):
        print(f"\n  TOOL CALL TIMELINE")
        for ti, turn in enumerate(all_turns, 1):
            for j, a in enumerate(turn["actions"], 1):
                elapsed = a["ts"] - all_turns[0]["t_start"]
                print(f"    T{ti}.{j} [{elapsed:6.1f}s] {a['content'][:120]}")

    # -- Scrape Results Analysis --
    scrape_successes = 0
    scrape_failures = 0
    for t in all_turns:
        for ar in t["action_results"]:
            content = ar["content"].lower()
            if "error scraping" in content or "failed to" in content or "403" in content:
                scrape_failures += 1
            elif len(ar["content"]) > 200:  # substantial content = likely success
                scrape_successes += 1

    if scrape_count > 0:
        print(f"\n  SCRAPE SUCCESS RATE")
        print(f"    Successful scrapes   : ~{scrape_successes}")
        print(f"    Failed scrapes       : ~{scrape_failures}")

    # -- Event Breakdown --
    type_counts = {}
    for t in all_turns:
        for e in t["events"]:
            k = e.get("type", "unknown")
            type_counts[k] = type_counts.get(k, 0) + 1
    print(f"\n  EVENT BREAKDOWN")
    for k, v in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"    {k:25s}: {v}")

    if not all_turns:
        print("\n  [FATAL] No turns completed. Is the backend running?")
        print("#" * 70)
        return

    # -- Check for generated PDF report --
    pdf_text = ""
    pdf_path = ""
    working_dir = "D:\\New folder"
    # Find the most recently created PDF matching this test
    try:
        pdfs = glob.glob(os.path.join(working_dir, "Report_*.pdf"))
        if pdfs:
            # Get the newest PDF
            newest_pdf = max(pdfs, key=os.path.getmtime)
            pdf_age = time.time() - os.path.getmtime(newest_pdf)
            if pdf_age < total_wall + 60:  # created during this test
                pdf_path = newest_pdf
                # Extract text from PDF
                try:
                    from PyPDF2 import PdfReader
                    reader = PdfReader(pdf_path)
                    for page in reader.pages:
                        pdf_text += page.extract_text() or ""
                    print(f"\n  PDF REPORT FOUND: {os.path.basename(pdf_path)}")
                    print(f"    Pages: {len(reader.pages)}, Text length: {len(pdf_text)} chars")
                except ImportError:
                    print(f"\n  PDF REPORT FOUND: {os.path.basename(pdf_path)}")
                    print(f"    (Install PyPDF2 to extract text for quality analysis)")
                except Exception as e:
                    print(f"\n  PDF REPORT FOUND but couldn't read: {e}")
    except Exception as e:
        print(f"\n  Could not check for PDFs: {e}")

    # -- Report Quality Analysis --
    # Prefer PDF content over inline response for quality analysis
    final_resp = all_turns[-1]["response"]
    analysis_text = pdf_text if pdf_text else final_resp
    analysis_source = "PDF REPORT" if pdf_text else "INLINE RESPONSE"

    print(f"\n  REPORT QUALITY ANALYSIS (from {analysis_source})")
    quality = analyze_report_quality(analysis_text)
    print(f"    Word count           : {quality['word_count']}")
    print(f"    Character count      : {quality['char_count']}")
    print(f"    Source URLs cited     : {quality['url_count']}")
    print(f"    Specific numbers     : {quality['number_count']}")
    print(f"    Percentages          : {quality['percentage_count']}")
    print(f"    Date references      : {quality['date_references']}")
    print(f"    Vague words          : {quality['vague_word_count']}")
    print(f"    Sections/headers     : {quality['section_count']}")

    if quality['sections']:
        print(f"\n  REPORT SECTIONS")
        for s in quality['sections']:
            print(f"    {s}")

    if quality['urls']:
        print(f"\n  CITED SOURCES (first 10)")
        for u in quality['urls']:
            print(f"    {u}")

    # -- Quality Verdict --
    print(f"\n  QUALITY VERDICT")
    score = 0
    checks = []

    if quality['word_count'] >= 500:
        score += 1
        checks.append(f"    [PASS] Report length: {quality['word_count']} words (min 500)")
    else:
        checks.append(f"    [FAIL] Report too short: {quality['word_count']} words (min 500)")

    if quality['url_count'] >= 3:
        score += 1
        checks.append(f"    [PASS] Citations: {quality['url_count']} URLs (min 3)")
    else:
        checks.append(f"    [FAIL] Insufficient citations: {quality['url_count']} URLs (min 3)")

    if quality['number_count'] >= 5:
        score += 1
        checks.append(f"    [PASS] Specific data: {quality['number_count']} numbers (min 5)")
    else:
        checks.append(f"    [FAIL] Lacks specifics: {quality['number_count']} numbers (min 5)")

    if quality['vague_word_count'] <= 5:
        score += 1
        checks.append(f"    [PASS] Precision: only {quality['vague_word_count']} vague words")
    else:
        checks.append(f"    [WARN] Vague language: {quality['vague_word_count']} vague words")

    if quality['section_count'] >= 3:
        score += 1
        checks.append(f"    [PASS] Structure: {quality['section_count']} sections")
    else:
        checks.append(f"    [WARN] Minimal structure: {quality['section_count']} sections")

    for c in checks:
        print(c)

    print(f"\n    OVERALL SCORE: {score}/5")
    if score >= 4:
        print("    VERDICT: EXCELLENT - Deep research with verified facts")
    elif score >= 3:
        print("    VERDICT: GOOD - Solid research but could go deeper")
    elif score >= 2:
        print("    VERDICT: FAIR - Some research done but lacks depth")
    else:
        print("    VERDICT: POOR - Superficial, likely relied on snippets")

    # -- Full Response --
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
