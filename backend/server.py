import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import time
import requests
import re
import random
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import sys
import io
import httpx
from dotenv import load_dotenv

load_dotenv()

# Ensure UTF-8 for standard output on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, io.UnsupportedOperation):
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, io.UnsupportedOperation):
        pass

def safe_log(message):
    """Prints a message safely, handling potential Unicode encoding issues on Windows consoles."""
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        try:
            # Fallback to ascii with replacement if utf-8 wrapper failed
            print(message.encode('ascii', 'replace').decode('ascii'), flush=True)
        except:
            pass
    except Exception:
        pass

def background_dir_scanner():
    while True:
        try:
            agents = load_data()
            if agents:
                for agent in agents:
                    wdir = agent.get('workingDir')
                    if wdir and os.path.exists(wdir):
                        dir_map = {}
                        try:
                            file_count = 0
                            for root, dirs, files in os.walk(wdir):
                                if file_count > 1500:
                                    break
                                rel = os.path.relpath(root, wdir)
                                dir_map[rel] = {"files": files, "dirs": dirs}
                                file_count += len(files)
                                
                            out_path = os.path.join(AGENTS_CODE_DIR, agent['id'], "dir_map.json")
                            os.makedirs(os.path.dirname(out_path), exist_ok=True)
                            with open(out_path, "w", encoding="utf-8") as f:
                                json.dump(dir_map, f)
                        except:
                            pass
        except:
            pass
        time.sleep(5)

threading.Thread(target=background_dir_scanner, daemon=True).start()

_thread_pool = ThreadPoolExecutor(max_workers=8)  # allows concurrent agent calls

app = FastAPI()

# Enable CORS for Electron
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data Storage
DATA_FILE = os.path.join(os.path.dirname(__file__), "agents.json")
AGENTS_CODE_DIR = os.path.join(os.path.dirname(__file__), "agents_code")

# Ensure agents code directory exists
if not os.path.exists(AGENTS_CODE_DIR):
    os.makedirs(AGENTS_CODE_DIR)

WORKSPACE_CONTEXT_FILE = os.path.join(AGENTS_CODE_DIR, "workspace_context.json")
BLACKBOARD_FILE = os.path.join(AGENTS_CODE_DIR, "blackboard.json")

# ─── BLACKBOARD KNOWLEDGE GRAPH ─────────────────────────────────────────────

_blackboard_lock = threading.Lock()

def write_to_blackboard(agent_id, agent_name, query, raw_snippet, url, entities=None):
    """
    Append a rich Data Object to the global blackboard.
    Each entry stores a RAW, un-summarized fact with full provenance.
    """
    import uuid
    entry = {
        "id": str(uuid.uuid4())[:8],
        "agent_id": agent_id,
        "agent_name": agent_name,
        "timestamp": time.time(),
        "query": query,
        "raw_snippet": raw_snippet,
        "url": url,
        "entities": entities or []
    }
    with _blackboard_lock:
        entries = []
        if os.path.exists(BLACKBOARD_FILE):
            try:
                with open(BLACKBOARD_FILE, "r", encoding="utf-8") as f:
                    entries = json.load(f)
            except: pass
        entries.append(entry)
        with open(BLACKBOARD_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
    return entry["id"]

def search_blackboard(query, top_k=15):
    """
    Semantically search the blackboard for the most relevant entries.
    Returns a formatted string of matched entries for injection into context.
    """
    if not os.path.exists(BLACKBOARD_FILE):
        return "Blackboard is empty. No findings have been recorded yet."
    try:
        with open(BLACKBOARD_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except:
        return "Error reading blackboard."

    if not entries:
        return "Blackboard is empty."

    # Score each entry against the query using semantic similarity
    scored = []
    for e in entries:
        text = f"{e.get('query','')} {e.get('raw_snippet','')}"
        score = calculate_semantic_similarity(query, text)
        scored.append((score, e))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    lines = [f"### Blackboard Search: '{query}'\n"]
    for score, e in top:
        lines.append(
            f"**[{e['agent_name']}]** | Query: {e.get('query','?')} | Score: {score:.2f}\n"
            f"Snippet: {e.get('raw_snippet','')}\n"
            f"Source: {e.get('url','No URL')}\n"
        )
    return "\n---\n".join(lines)

def get_full_blackboard():
    """Returns all entries from the blackboard as a formatted research dump."""
    if not os.path.exists(BLACKBOARD_FILE):
        return "Blackboard is empty."
    try:
        with open(BLACKBOARD_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except:
        return "Error reading blackboard."
    if not entries:
        return "Blackboard is empty."
    lines = [f"### Full Blackboard — {len(entries)} entries\n"]
    for e in entries:
        lines.append(
            f"[{e['agent_name']}] {e.get('raw_snippet','')}\nSource: {e.get('url','No URL')}"
        )
    return "\n---\n".join(lines)


def get_workspace_context():
    """Reads the global workspace context (overarching goal)."""
    if not os.path.exists(WORKSPACE_CONTEXT_FILE):
        return {"global_objective": "No specific objective set yet.", "last_update": 0}
    try:
        with open(WORKSPACE_CONTEXT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"global_objective": "Error reading context.", "last_update": 0}

def update_workspace_context(new_goal):
    """Updates the global workspace context with a new objective."""
    try:
        # Don't update for internal system messages or tool results
        if "SYSTEM TOOL RESULT:" in new_goal or "[MESSAGE FROM" in new_goal:
            return
        
        # Simple heuristic: if it's more than 20 chars, it's likely a new or refined goal
        if len(new_goal.strip()) < 20:
            return

        context = {
            "global_objective": new_goal.strip(),
            "last_update": time.time()
        }
        with open(WORKSPACE_CONTEXT_FILE, "w", encoding="utf-8") as f:
            json.dump(context, f, indent=2)
        safe_log(f"--- [BACKEND] Updated Workspace Context: {new_goal[:50]}...")
    except Exception as e:
        safe_log(f"!!! [BACKEND ERROR] Could not update workspace context: {e}")

def sanitize_ruthlessly(text):
    """
    RUTHLESS NON-DISCLOSURE: Redacts extremely large blocks and raw data dumps.
    """
    if not text or not isinstance(text, str):
        return text

    # 1. Truncate markdown blocks if they are too large (> 5000 chars)
    def truncate_code(match):
        code = match.group(0)
        if len(code) > 5000:
            return f"{code[:2500]}\n\n[... TRUNCATED FOR UI PERFORMANCE ...]\n\n{code[-2500:]}"
        return code
    text = re.sub(r"```[\s\S]*?```", truncate_code, text)
    
    # 2. Redact huge [TOOL: ...] signatures (The 'file content' in tool calls)
    def redact_huge_tool(match):
        tool_name = match.group(1)
        tool_input = match.group(2)
        if len(tool_input) > 500:
            return f"[TOOL: {tool_name}({tool_input[:497]}...)]"
        return match.group(0)
    
    text = re.sub(r"\[TOOL:\s*(\w+)\(([\s\S]*?)\)\]", redact_huge_tool, text)

    # 3. Detect raw data dumps (heuristic check for large blocks with CSV/delimited patterns)
    lines = text.splitlines()
    if len(lines) > 50: # Only check if it's a long message
        delim_count = 0
        for l in lines[:10]:
            clean_l = l.strip()
            if clean_l.startswith(('-', '*', '•')):
                continue
            if ',' in l or '\t' in l or '|' in l:
                delim_count += 1
        if delim_count > 8:
            return f"{text[:1000]}\n\n[REDACTED: Large Data/CSV Format Detected for PDF Safety]"

    return text

def calculate_semantic_similarity(text1, text2):
    """
    UNIVERSAL FIX: SEMANTIC STIGMERGY (Topic-Gated Blackboard)
    Calculates word-overlap similarity (Keyword Energy) between two strings.
    """
    if not text1 or not text2: return 0.0
    # Filter out noise words for better 'Energy' matching
    stop_words = {"a", "an", "the", "and", "or", "but", "if", "then", "else", "to", "for", "with", "is", "was", "be", "of", "in", "on", "at"}
    words1 = set(w for w in re.findall(r'\w+', text1.lower()) if w not in stop_words)
    words2 = set(w for w in re.findall(r'\w+', text2.lower()) if w not in stop_words)
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union) if union else 0.0

def process_generational_history(history, max_turns=60):
    """
    CONTEXT RETENTION: Protects tool result messages from decay.
    - SYSTEM TOOL RESULT messages (blackboard writes, search results) are NEVER truncated —
      they contain foundational research data that is still needed later.
    - Normal user/assistant turns follow the generational decay pattern.
    """
    if not history: return []
    raw = history[-max_turns:] if len(history) > max_turns else history
    processed = []

    rev_raw = list(reversed(raw))
    for i, msg in enumerate(rev_raw):
        role = msg.get("role", "user")
        content = str(msg.get("content", "") or "")

        # PERMANENT MESSAGES: SYSTEM TOOL RESULT and post_finding confirmations
        # are NEVER decayed — they are raw knowledge data, not conversation.
        is_tool_result = content.startswith("SYSTEM TOOL RESULT:")
        is_blackboard_confirm = "recorded in the Blackboard" in content
        if is_tool_result or is_blackboard_confirm:
            processed.insert(0, {"role": role, "content": content})
            continue

        # Generation 0 (Last 15 messages): Full detail
        if i < 15:
            processed.insert(0, {"role": role, "content": content})

        # Generation 1 (Messages 16-30): Condensed — keep meaning, cut length
        elif i < 30:
            if content.startswith("[TOOL:"):
                tool_body = content[len("[TOOL:"):].rstrip("]")
                name_part = tool_body.split("(", 1)[0].strip()
                processed.insert(0, {"role": role, "content": f"[Previously used tool: {name_part}]"})
            else:
                preview = content[:300] + "..." if len(content) > 300 else content
                processed.insert(0, {"role": role, "content": preview})

        # Generation 2 (Messages 31-60): Topic-only metadata
        else:
            if content.startswith("[TOOL:"):
                tool_body = content[len("[TOOL:"):].rstrip("]")
                name_part = tool_body.split("(", 1)[0].strip()
                processed.insert(0, {"role": role, "content": f"[Past action: {name_part}]"})
            else:
                processed.insert(0, {"role": role, "content": f"[Past message: {content[:80]}...]"})

    return processed

def refresh_conversation_summary(agent_id, history, api_key, provider, current_summary=""):
    """
    Uses the LLM to condense the conversation history and existing summary into a new, 
    leaner cumulative summary. This preserves long-term memory while saving tokens.
    """
    print(f"[STATUS:{agent_id}] Updating Long-term Memory Summary...", flush=True)
    
    # We only summarize messages that are falling out of the sliding window
    # or the entire history if it's the first summary.
    # To keep it simple: we summarize the provided context as 'History so far'.
    
    formatted_history = ""
    for h in history:
        role = "Agent" if h["role"] == "assistant" else "User"
        # Truncate content for the summarizer itself to be safe
        content = h.get("content", "")
        if content is None: content = "[No Content]"
        content_preview = content[:500] + "..." if len(content) > 500 else content
        formatted_history += f"[{role}]: {content_preview}\n"

    summary_prompt = f"""You are a memory management module for an AI agent. 
Analyze the existing summary and the recent conversation history below. 
Generate a NEW, comprehensive but concise summary that incorporates all key decisions, 
accomplishments, user preferences, and pending tasks.

EXISTING SUMMARY:
{current_summary if current_summary else "No previous summary exists."}

RECENT HISTORY:
{formatted_history}

STRICT RULE: The output must be a clean, bulleted markdown summary. Do not include any conversational preamble.
"""

    response_text = ""
    try:
        model = "gemini-2.0-flash" 
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        data = {
            "contents": [{"role": "user", "parts": [{"text": summary_prompt}]}]
        }
        resp = requests.post(url, json=data, timeout=30)
        if resp.status_code == 200:
            res_json = resp.json()
            candidates = res_json.get("candidates", [])
            if candidates and isinstance(candidates, list) and len(candidates) > 0:
                cand = candidates[0]
                content = cand.get("content", {})
                parts = content.get("parts", [])
                if parts and isinstance(parts, list) and len(parts) > 0:
                    response_text = parts[0].get("text", "")
    except Exception as e:
        print(f"!!! [SUMMARY ERROR] Failed to update summary: {e}")
        return current_summary

    return response_text.strip() if response_text else current_summary
    
# Tool Implementations
def perform_tool_call(agent_id, tool_name, tool_input, agent_dir, api_key=""):
    # --- Resolve workingDir for file-saving tools ---
    agents = load_data()
    sender_data = next((a for a in agents if a["id"] == agent_id), None)
    working_dir = sender_data.get("workingDir", "") if sender_data else ""

    if sender_data:
        permissions = sender_data.get("permissions", [])
        
        # Tool Permission Mapping
        tool_to_perm = {
            "web_search": "web search",
            "deep_search": "web search",
            "thinking": "thinking",
            "generate_report": "report generation",
            "report_generation": "report generation",
            "list_workspace": "file access",
            "scout_file": "file access",
            "read_file": "file access",
            "write_file": "file access",
            "message_agent": None # Usually allowed if connected
        }
        
        required_perm = tool_to_perm.get(tool_name)
        if required_perm and required_perm not in permissions:
            safe_log(f"!!! [PERMISSION DENIED] Agent '{sender_data.get('name')}' tried to use '{tool_name}' without '{required_perm}' permission.")
            return f"Error: My '{required_perm}' capability is currently disabled. I cannot use the tool '{tool_name}'. Please enable it in my settings if you want me to proceed with this action."

    if tool_name == "post_finding":
        # ── BLACKBOARD UPGRADE ──────────────────────────────────
        # Parse the tool input to extract structured fields.
        # Expected format (flexible): "Snippet | Source: URL | Entities: ..."
        # Fallback: treat the whole input as the raw snippet.
        raw_snippet = tool_input.strip()
        url = ""
        entities = []
        query_hint = ""

        # Try to extract URL from [Source: ...] or Source: ...
        url_match = re.search(r'(?:Source:|\[Source:)\s*(https?://[^\]\n,]+)', tool_input, re.IGNORECASE)
        if url_match:
            url = url_match.group(1).strip().rstrip(']')
            # Strip the source annotation from the snippet for cleanliness
            raw_snippet = re.sub(r'(?:Source:|\[Source:)[^\]\n]*', '', raw_snippet).strip()

        # Try to extract entities from the snippet (names, years, proper nouns in title case)
        entity_candidates = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', raw_snippet)
        entities = list(set(entity_candidates))[:10]  # cap at 10

        # Use the first portion of the snippet as a query hint
        query_hint = raw_snippet[:80] if raw_snippet else tool_input[:80]

        # Resolve agent name for provenance
        try:
            all_agents = load_data()
            this_agent = next((a for a in all_agents if a["id"] == agent_id), {})
            agent_name_for_blackboard = this_agent.get("name", agent_id)
        except:
            agent_name_for_blackboard = agent_id

        entry_id = write_to_blackboard(
            agent_id=agent_id,
            agent_name=agent_name_for_blackboard,
            query=query_hint,
            raw_snippet=raw_snippet,
            url=url,
            entities=entities
        )
        safe_log(f"[BLACKBOARD:{agent_id}] Entry #{entry_id} added. snippet={raw_snippet[:60]}... url={url[:40]}")
        return f"Success: Finding recorded in the Blackboard (ID: {entry_id})."
    
    elif tool_name == "update_plan":
        return toolkit.update_plan(agent_id, tool_input)

    elif tool_name == "web_search":
        return toolkit.web_search(tool_input, agent_id, api_key=api_key)
    
    elif tool_name == "deep_search":
        return toolkit.deep_search(tool_input, agent_id, api_key=api_key)
    
    elif tool_name == "thinking":
        return toolkit.thinking(agent_id, tool_input)

    elif tool_name == "generate_report":
        return toolkit.generate_report(agent_id, tool_input, working_dir)

    elif tool_name == "report_generation":
        # Pass agent_name from sender_data
        agent_name = sender_data.get("name", "Agent") if sender_data else "Agent"
        return toolkit.report_generation(agent_id, tool_input, working_dir, api_key, agent_name=agent_name)
    
    elif tool_name == "message_agent":
        if "|" in tool_input:
            parts = tool_input.split("|", 1)
            target_id = parts[0].strip()
            message = parts[1].strip()
            
            # Robust parsing: handle named argument hallucinations like AGENT_ID="..." or target="..."
            if "=" in target_id:
                target_id = target_id.split("=")[-1].strip()
            target_id = target_id.strip("'").strip('"').strip("`")

            # Handle message="..." as well
            if "=" in message and (message.lower().startswith("message=") or message.lower().startswith("content=")):
                message = message.split("=", 1)[-1].strip().strip("'").strip('"').strip("`")
            
            agents = load_data()

            # ── 1. Find sender data
            sender_data = next((a for a in agents if a["id"] == agent_id), None)
            if not sender_data:
                return f"Error: Sender agent {agent_id} not found."
            sender_name = sender_data.get("name", "Unknown Agent")

            # ── 3. Find target
            target_data = next((a for a in agents if a["id"] == target_id), None)
            if not target_data:
                return f"Error: Target agent {target_id} not found."

            # ── 2. ENFORCE CONNECTION GRAPH (BIDIRECTIONAL)
            #       A wire on the canvas between two agents means both can message each other,
            #       regardless of which end the user drew the arrow from.
            sender_connections = sender_data.get("connections", [])
            target_connections = target_data.get("connections", []) if target_data else []
            is_connected = (target_id in sender_connections) or (agent_id in target_connections)
            if not is_connected:
                return (f"Error: You are not connected to agent '{target_id}'. "
                        f"There is no canvas wire between you. "
                        f"Draw a connection on the canvas to enable communication.")
            
            target_provider = target_data.get("brain", "").lower()

            # ── 4. PRE-DELEGATION CAPABILITY CHECK
            #       Before sending, verify the target can actually do the work.
            #       An agent with zero permissions and zero connections is a dead end.
            target_perms = target_data.get("permissions", [])
            target_conns = target_data.get("connections", [])  # already fetched above
            if not target_perms and not target_conns:
                target_name = target_data.get("name", target_id)
                return (
                    f"DELEGATION BLOCKED: Agent '{target_name}' has no capabilities enabled "
                    f"(no permissions, no connections). Sending them this task will produce no results. "
                    f"You must either: (1) complete this task yourself if you have the tools, or "
                    f"(2) tell the user that '{target_name}' needs permissions enabled before it can work."
                )

            # ── 5. BUILD COMPACT TASK CONTEXT (not full history — just enough for the agent to orient)
            sender_plan_path = os.path.join(AGENTS_CODE_DIR, agent_id, "plan.json")
            task_context_lines = []
            try:
                if os.path.exists(sender_plan_path):
                    with open(sender_plan_path, "r", encoding="utf-8") as f:
                        plan = json.load(f)
                        obj = plan.get("objective", "")
                        if obj and obj.strip() and obj.strip().lower() not in ("objective", "none", ""):
                            task_context_lines.append(f"Sender's Active Plan: {obj}")
            except Exception:
                pass
            task_context_lines.append(f"Task being delegated: {message[:250]}")
            cap_summary = ", ".join(target_perms) if target_perms else "none"
            task_context_lines.append(f"Your available capabilities: {cap_summary}")
            sender_context_snippet = "\n".join(task_context_lines)
            
            # ── 5. Get API key for target provider
            target_api_key = api_key
            config_path = os.path.join(os.getenv('APPDATA', ''), 'easy-company', 'config.json')
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                        keys = config_data.get("apiKeys", {})
                        if keys.get(target_provider):
                            target_api_key = keys[target_provider]
                except Exception:
                    pass

            # -- 6. Handle Intent Priority (BDI Upgrade)
            intent_priority = "NORMAL"
            if "intent_priority" in tool_input:
                # Simple parsing for intent_priority=USER_MANDATED
                if "USER_MANDATED" in tool_input:
                    intent_priority = "USER_MANDATED"

            # Signal the UI: who is being messaged so its canvas terminal can update
            print(f"[AGENT_MSG:{agent_id}->{target_id}] Contacting {target_data.get('name', target_id)} (Priority: {intent_priority})", flush=True)
            
            return toolkit.message_agent(
                target_id, message.strip(), agent_id, sender_name,
                target_api_key, target_provider,
                context_snippet=sender_context_snippet,
                intent_priority=intent_priority
            )
        return "Error: format must be target_id|message"
            
    elif tool_name in ["read_file", "write_file", "scout_file", "list_workspace"]:
        # working_dir already resolved above
        try:
            if tool_name == "list_workspace":
                print(f"[STATUS:{agent_id}] Listing Workspace Files (Real-time Scan)", flush=True)
                if not working_dir or not os.path.exists(working_dir):
                    return "Error: Working directory is invalid or not set."
                
                lines = []
                file_count = 0
                for root, dirs, files in os.walk(working_dir):
                    if file_count > 1000: # Safety cap
                        break
                    rel = os.path.relpath(root, working_dir)
                    if rel == ".":
                        lines.append("Directory: . (Root)")
                    else:
                        lines.append(f"Directory: {rel}")
                    
                    for d in sorted(dirs):
                        lines.append(f"  [DIR]  {d}")
                    for fname in sorted(files):
                        lines.append(f"  [FILE] {fname}")
                    lines.append("")
                    file_count += len(files)
                
                tree_str = "\n".join(lines)
                return f"Workspace Directory Map:\n{tree_str}"
            elif tool_name == "read_file":
                return toolkit.read_file(agent_id, tool_input, working_dir)
            elif tool_name == "write_file":
                return toolkit.write_file(agent_id, tool_input, working_dir)
            elif tool_name == "scout_file":
                return toolkit.scout_file(agent_id, tool_input, working_dir)
        except Exception as e:
            return f"Error executing {tool_name}: {e}"

    elif tool_name == "read_blackboard":
        # Semantically search the blackboard for relevant entries
        query = tool_input.strip() or "all findings"
        if query.lower() in ["all", "full", ""]:
            return get_full_blackboard()
        return search_blackboard(query)

    elif tool_name == "read_prompt":
        prompt_file = os.path.join(AGENTS_CODE_DIR, agent_id, "prompt.md")
        try:
            if os.path.exists(prompt_file):
                with open(prompt_file, "r", encoding="utf-8") as f:
                    content = f.read()
                return f"### Current prompt.md:\n\n{content}"
            else:
                return "No prompt.md found for this agent yet."
        except Exception as e:
            return f"Error reading prompt: {e}"

    elif tool_name == "update_prompt":
        prompt_file = os.path.join(AGENTS_CODE_DIR, agent_id, "prompt.md")
        try:
            new_content = tool_input.strip()
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(new_content)
            safe_log(f"[TRAINING] Agent {agent_id} updated its own prompt.")
            return f"✅ prompt.md has been successfully updated. The new prompt is now active."
        except Exception as e:
            return f"Error updating prompt: {e}"

    elif tool_name == "read_memory":
        summary_file = os.path.join(AGENTS_CODE_DIR, agent_id, "summary.json")
        try:
            if os.path.exists(summary_file):
                with open(summary_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                summary_text = data.get("summary", "No summary recorded yet.")
                return f"### Long-Term Memory (summary.json):\n\n{summary_text}"
            else:
                return "No long-term memory exists for this agent yet."
        except Exception as e:
            return f"Error reading memory: {e}"

    elif tool_name == "read_workspace":
        try:
            content = get_workspace_context()
            return f"### Global Workspace Context:\n\n{content or 'No workspace context set.'}"
        except Exception as e:
            return f"Error reading workspace context: {e}"

    return "i dont have that ability yet"

import shutil
import toolkit
import response_formatter
import plan_runner

class AgentModel(BaseModel):
    id: str
    name: str
    description: str = ""
    brain: str = ""
    channel: str = "Gmail"
    workingDir: str = ""
    permissions: List[str] = []
    tools: str = "Custom"
    responsibility: str = ""
    agentType: str = "worker"  # "master" | "worker"
    x: float = 0
    y: float = 0
    connections: List[str] = []

class ChatRequest(BaseModel):
    agent_id: str
    message: str
    mode: Optional[str] = "work"  # 'work' or 'training'
    api_key: Optional[str] = ""
    provider: Optional[str] = "Gemini"

def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"!!! [BACKEND ERROR] Could not parse {DATA_FILE}: {e}")
        return None  # Return None to indicate a CORRUPT file, not an empty one
    except Exception as e:
        print(f"!!! [BACKEND ERROR] An unexpected error occurred in load_data: {e}")
        return None

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"!!! [BACKEND ERROR] An unexpected error occurred in save_data: {e}")

def generate_agent_structure(agent_data):
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_data['id'])
    if not os.path.exists(agent_dir):
        os.makedirs(agent_dir)
    
    # 1. Main Agent Python File
    main_py_path = os.path.join(agent_dir, "main.py")
    class_name = agent_data['id'].replace('-', '_')
    if class_name and class_name[0].isdigit():
        class_name = "A_" + class_name
        
    main_py_content = f"""
class {class_name}:
    def __init__(self):
        self.id = "{agent_data['id']}"
        self.name = "{agent_data['name']}"
        self.working_dir = r"{agent_data.get('workingDir', '')}"
        self.permissions = {agent_data.get('permissions', [])}
        self.tools = "{agent_data.get('tools', 'Custom')}"
        
    def get_personality(self):
        import json
        import os
        try:
            with open(os.path.join(os.path.dirname(__file__), 'personality.json'), 'r', encoding="utf-8") as f:
                return json.load(f)
        except:
            return {{}}

if __name__ == "__main__":
    agent = {class_name}()
    print(f"Agent {{agent.name}} initialized.")
"""
    with open(main_py_path, "w", encoding="utf-8") as f:
        f.write(main_py_content)

    # 2. Long term memory (Personality)
    personality_path = os.path.join(agent_dir, "personality.json")
    personality_data = {
        "name": agent_data['name'],
        "description": agent_data['description'],
        "responsibility": agent_data.get('responsibility', ''),
        "tools": agent_data.get('tools', 'Custom')
    }
    with open(personality_path, "w", encoding="utf-8") as f:
        json.dump(personality_data, f, indent=2)

    # 3. prompt.md — identity and behavioral rules ONLY.
    prompt_path = os.path.join(agent_dir, "prompt.md")
    prompt_content = f"""# Agent Instructions: {agent_data['name']}
Identity: You are an agent sitting in a desktop PC at UF working for Ashir.
Description: {agent_data['description']}
Responsibility: {agent_data.get('responsibility', 'General purpose assistance')}

## INTENT GATE
1. If the user asks about your abilities, confirm them in plain text. 
2. Do NOT execute a tool call unless a specific topic or objective is provided.

## STIGMERGY (SHARED LEDGER)
1. **Ledger First**: Before acting, check the Shared Workspace Ledger in your context for existing findings.
2. **Post Findings**: After discovering a fact, use [TOOL: post_finding(Insight | Source URL)] to share it.

## BDI PLANNING & STATE
1. Call [TOOL: update_plan(Objective | Step 1, Step 2, ...)] immediately when you accept a new task.
2. Call [TOOL: update_plan(Task Completed)] before sending any final response.

## SOURCE REQUIREMENT
Every fact from research must include a `[Source: URL]` citation.
"""
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt_content)

    # 4. Phase 2: Plan (BDI) - Initialize if not exists
    plan_path = os.path.join(agent_dir, "plan.json")
    if not os.path.exists(plan_path):
        initial_plan = {
            "objective": agent_data.get('responsibility', 'General assistance'),
            "steps": ["Observe Workspace", "Execute requested task"],
            "completed": []
        }
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(initial_plan, f, indent=2)

    # 5. Short term memory (History) - Initialize if not exists
    history_path = os.path.join(agent_dir, "history.json")
    if not os.path.exists(history_path):
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump([], f)

    # 6. Agent Manifest (Phase 4) — always regenerate so settings changes apply
    agent_type = agent_data.get("agentType", "worker")
    manifest = {
        "agent_id": agent_data.get("id", ""),
        "extraction_logic": "RAW_CHUNKS",
        "verification_required": False,
        "output_format": "STRUCTURED_FINDINGS",
        "knowledge_gate": "READ_WRITE" if agent_type == "master" else "WRITE_ONLY_LEDGER"
    }
    manifest_path = os.path.join(agent_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    safe_log(f"+++ [BACKEND] Generated agent structure in: {agent_dir}")

def delete_agent_structure(agent_id):
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_id)
    if os.path.exists(agent_dir):
        try:
            shutil.rmtree(agent_dir)
            safe_log(f"--- [BACKEND] Deleted agent directory: {agent_dir}")
        except Exception as e:
            safe_log(f"!!! [BACKEND ERROR] Could not delete agent directory: {e}")

@app.get("/agents")
def get_agents():
    agents = load_data()
    
    # If load_data returned None, it means the file exists but is corrupted.
    # We should NOT return a default MasterBot here because that would 
    # likely cause the frontend to eventually overwrite the corrupted file.
    if agents is None:
        raise HTTPException(status_code=500, detail="Agent data file is corrupted or unreadable.")

    if not agents:
        master = {
            "id": "agent-MasterBot-001",
            "name": "MasterBot",
            "description": "Main orchestrator agent.",
            "agentType": "master",
            "x": 100,
            "y": 150,
            "brain": "Gemini",
            "tools": "Gmail",
            "responsibility": "Coordinate all agents",
            "permissions": ["web search", "thinking"]
        }
        agents.append(master)
        save_data(agents)
        generate_agent_structure(master)
        safe_log(f"+++ [BACKEND] No agents found. Created default 'MasterBot'.")
    return agents

@app.post("/agents")
def create_agent(agent: AgentModel):
    agents = load_data()
    # Check if ID exists
    for a in agents:
        if a["id"] == agent.id:
            safe_log(f"--- [BACKEND] Agent with ID '{agent.id}' already exists. No action taken.")
            return a
    agents.append(agent.model_dump())
    save_data(agents)
    generate_agent_structure(agent.model_dump())
    safe_log(f"+++ [BACKEND] Created new agent: '{agent.name}' (ID: {agent.id})")
    return agent

@app.put("/agents/{agent_id}")
def update_agent(agent_id: str, agent: AgentModel):
    agents = load_data()
    for i, a in enumerate(agents):
        if a["id"] == agent_id:
            # Enforce consistency: ensure the ID in the record stays the same as the URL ID
            updated_data = agent.model_dump()
            if updated_data.get("id") != agent_id:
                safe_log(f"!!! [BACKEND WARNING] ID mismatch in PUT request. Body: {updated_data.get('id')} vs URL: {agent_id}. Enforcing URL ID.")
                updated_data["id"] = agent_id

            agents[i] = updated_data
            save_data(agents)
            generate_agent_structure(updated_data)
            safe_log(f"*** [BACKEND] Updated agent: '{agent.name}' (ID: {agent_id})")
            return agents[i]
    safe_log(f"!!! [BACKEND ERROR] Attempted to update non-existent agent with ID: {agent_id}")
    raise HTTPException(status_code=404, detail="Agent not found")

@app.delete("/agents/{agent_id}")
def delete_agent(agent_id: str):
    agents = load_data()
    agent_to_delete = next((agent for agent in agents if agent["id"] == agent_id), None)

    if agent_to_delete:
        agents.remove(agent_to_delete)
        save_data(agents)
        delete_agent_structure(agent_id)
        safe_log(f"--- [BACKEND] Deleted agent: '{agent_to_delete.get('name')}' (ID: {agent_id})")
        return {"status": "success", "message": "Agent deleted"}
    else:
        safe_log(f"!!! [BACKEND ERROR] Attempted to delete non-existent agent with ID: {agent_id}")
        raise HTTPException(status_code=404, detail="Agent not found")

@app.get("/history/{agent_id}")
def get_history(agent_id: str):
    """Returns the saved conversation history for an agent."""
    history_path = os.path.join(AGENTS_CODE_DIR, agent_id, "history.json")
    if not os.path.exists(history_path):
        return []
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"!!! [BACKEND ERROR] Could not read history for {agent_id}: {e}")
        return []

@app.delete("/history/{agent_id}")
def clear_history(agent_id: str):
    """Wipes the conversation history for an agent (fresh start)."""
    history_path = os.path.join(AGENTS_CODE_DIR, agent_id, "history.json")
    try:
        if os.path.exists(history_path):
            os.remove(history_path)
        
        internal_history_path = os.path.join(AGENTS_CODE_DIR, agent_id, "internal_history.json")
        if os.path.exists(internal_history_path):
            os.remove(internal_history_path)
            
        comm_log_path = os.path.join(AGENTS_CODE_DIR, agent_id, "communication.log")
        if os.path.exists(comm_log_path):
            os.remove(comm_log_path)

        # Re-initialize main history as empty
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump([], f)
            
        print(f"--- [BACKEND] Cleared history for agent: {agent_id}")
        return {"status": "success", "message": "History and logs cleared"}
    except Exception as e:
        print(f"!!! [BACKEND ERROR] Could not clear history for {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def get_gemini_tools_from_permissions(permissions, has_messaging=False, manifest_only=False):
    """
    Translates agent permissions into Gemini-native tool declarations.
    If manifest_only is True, returns a human-readable string for system prompts.
    """
    declarations = []
    
    # Tool mapping for Gemini native schema
    if "web search" in permissions:
        declarations.append({
            "name": "web_search",
            "description": "Quickly fetch facts and snippets from the web.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {"type": "STRING", "description": "The search query."}
                },
                "required": ["query"]
            }
        })
        declarations.append({
            "name": "deep_search",
            "description": "Perform an in-depth research exploration.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {"type": "STRING", "description": "The complex research theme."}
                },
                "required": ["query"]
            }
        })

    if "thinking" in permissions:
        declarations.append({
            "name": "thinking",
            "description": "A self-correction and deep analysis pass.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "topic": {"type": "STRING", "description": "What needs analysis."}
                },
                "required": ["topic"]
            }
        })

    if "report generation" in permissions:
        declarations.append({
            "name": "report_generation",
            "description": "Create a formal PDF report.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "topic": {"type": "STRING", "description": "Report title."},
                    "context": {"type": "STRING", "description": "Full research body."}
                },
                "required": ["topic", "context"]
            }
        })
        declarations.append({
            "name": "generate_report",
            "description": "Creates a structured markdown report file in the working directory.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING", "description": "Descriptive title for the report."},
                    "content": {"type": "STRING", "description": "The synthesized findings and data."}
                },
                "required": ["title", "content"]
            }
        })

    if "file access" in permissions:
        declarations.append({
            "name": "list_workspace",
            "description": "List all local files.",
            "parameters": {"type": "OBJECT", "properties": {}}
        })
        declarations.append({
            "name": "scout_file",
            "description": "Checks metadata, size, and line count of a specific file or directory.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "filename": {"type": "STRING", "description": "Path to the file or directory."}
                },
                "required": ["filename"]
            }
        })
        declarations.append({
            "name": "read_file",
            "description": "Reads content from a local file. Use line ranges for files > 1000 lines.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "filename": {"type": "STRING", "description": "Filename and optional range (e.g. data.txt|1-500)."}
                },
                "required": ["filename"]
            }
        })
        declarations.append({
            "name": "write_file",
            "description": "Writes or overwrites a file in the working directory with new content.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "filename": {"type": "STRING", "description": "The name of the file."},
                    "content": {"type": "STRING", "description": "The full text content to write."}
                },
                "required": ["filename", "content"]
            }
        })

    if has_messaging:
        declarations.append({
            "name": "message_agent",
            "description": "Sends a message and delegates a task to a connected specialist agent.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "target_id": {"type": "STRING", "description": "The specific ID of the specialist agent."},
                    "message": {"type": "STRING", "description": "Task description or question."}
                },
                "required": ["target_id", "message"]
            }
        })

    # Global/BDI Tools (Always Available)
    declarations.append({
        "name": "post_finding",
        "description": "Writes a key fact or insight to the Shared Workspace Ledger for all agents to see.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "tool_input": {"type": "STRING", "description": "Format: 'Insight | Source URL'"}
            },
            "required": ["tool_input"]
        }
    })
    declarations.append({
        "name": "update_plan",
        "description": "Updates your internal BDI plan. Mandated before messaging the user.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "tool_input": {"type": "STRING", "description": "Format: 'Objective | Step1, Step2' OR 'Task Completed'"}
            },
            "required": ["tool_input"]
        }
    })

    if manifest_only:
        return "\n".join([f"- [TOOL: {d['name']}()]: {d['description']}" for d in declarations])

    return [{"function_declarations": declarations}] if declarations else []
@app.post("/chat")
async def chat_with_agent(request: ChatRequest):
    """
    Primary chat endpoint. Now returns a StreamingResponse to support live thinking/text.
    """
    agents = load_data()
    agent_data = next((a for a in agents if a["id"] == request.agent_id), None)
    if not agent_data:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent_id}' not found")

    agent_dir = os.path.join(AGENTS_CODE_DIR, request.agent_id)
    if not os.path.exists(agent_dir):
        os.makedirs(agent_dir, exist_ok=True)
        
    prompt_path = os.path.join(agent_dir, "prompt.md")
    history_path = os.path.join(agent_dir, "history.json")
    internal_history_path = os.path.join(agent_dir, "internal_history.json")
    summary_path = os.path.join(agent_dir, "summary.json")

    # Move context and history initialization above the generator for proper closure binding
    current_agent_prompt = ""
    if os.path.exists(prompt_path):
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                current_agent_prompt = f.read()
        except: pass

    try:
        if os.path.exists(internal_history_path):
            with open(internal_history_path, "r", encoding="utf-8") as f: history = json.load(f)
        else: history = []
    except: history = []
    
    history.append({"role": "user", "content": request.message})

    # Prepare Training Mode logic if needed
    is_training_mode = False
    training_tools_block = ""
    if getattr(request, 'mode', 'work') == 'training':
        training_tools_block = "## TRAINING TOOLS\n- [TOOL: read_prompt()]\n- [TOOL: update_prompt(new_content)]\n"
        if agent_data.get("agentType") == "master": training_tools_block += "- [TOOL: read_workspace()]\n"
        is_training_mode = True

    async def event_generator():
        nonlocal history
        iteration = 0
        final_response_collected = ""
        
        # Build Context Layers (Consolidated for streaming)
        ws_context = get_workspace_context()
        global_obj = ws_context.get("global_objective", "Initial exploration.")
        
        reachable_agents = []
        connections_list = agent_data.get("connections", [])
        for a in agents:
            if a["id"] in connections_list or request.agent_id in a.get("connections", []):
                reachable_agents.append(a)
        
        permissions = agent_data.get("permissions", [])
        
        identity_layer = (
            f"IDENTITY: You are an agent named '{agent_data.get('name')}' working for Ashir.\n"
            f"DESCRIPTION: {agent_data.get('description', 'No description.')}\n"
            f"RESPONSIBILITY: {agent_data.get('responsibility', 'No responsibility set.')}\n"
        )
        
        tool_manual_layer = f"## CAPABILITY MANIFEST\n{get_gemini_tools_from_permissions(permissions, len(reachable_agents) > 0, manifest_only=True)}\n"
        
        connected_str = "\n".join([f"- {a['name']} (ID: {a['id']}): {a.get('responsibility', '')}" for a in reachable_agents]) or "None"
        blackboard_context = search_blackboard(f"{global_obj} {request.message}")
        
        transient_task_layer = (
            f"## TRANSIENT TASK CONTEXT\n"
            f"GLOBAL PROJECT OBJECTIVE: {global_obj}\n"
            f"TEAM (Connected Agents): \n{connected_str}\n\n"
            f"### BLACKBOARD FINDINGS\n{blackboard_context}\n"
        )

        system_prompt = f"{identity_layer}\n{tool_manual_layer}\n{transient_task_layer}\n"
        
        # Apply Training Mode override if prepared
        if is_training_mode:
            system_prompt = (
                f"# YOU ARE A CURIOUS AI INTERN: {agent_data.get('name')}\n"
                f"You are currently in **TRAINING MODE**. Focus on learning your role.\n"
                f"## YOUR CURRENT WORK PROMPT (prompt.md):\n```\n{current_agent_prompt}\n```\n"
                f"{training_tools_block}\n"
            )
        
        # Priority: (1) frontend key via request, (2) backend .env key
        api_key = request.api_key or os.getenv("GEMINI_API_KEY", "")
        is_master = agent_data.get("agentType", "worker") == "master"
        is_task = plan_runner.is_task_request(request.message, api_key, "gemini")
        
        max_turns = 50 if is_task else 1
        if "[AUTO_STEP" in request.message: max_turns = 10

        while iteration < max_turns:
            llm_context = process_generational_history(history)
            model = "gemini-3-flash-preview" if is_master else "gemini-2.0-flash"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={api_key}"
            
            gemini_history = []
            for h in llm_context:
                gemini_history.append({
                    "role": "user" if h["role"] == "user" else "model",
                    "parts": [{"text": h["content"] or "[Empty]"}]
                })
            
            gen_config = {"temperature": 0.3, "maxOutputTokens": 8192}
            if is_master:
                gen_config["thinkingConfig"] = {"includeThoughts": True, "thinkingBudget": -1}
            
            payload = {
                "contents": gemini_history,
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "generationConfig": gen_config,
                "tools": get_gemini_tools_from_permissions(permissions, len(reachable_agents) > 0)
            }

            current_turn_text = ""
            current_turn_thoughts = ""
            tool_call_found = None

            try:
                print(f"[STATUS:{request.agent_id}] Turn {iteration+1}: Streaming from {model}...", flush=True)
                async with httpx.AsyncClient() as client:
                    async with client.stream("POST", url, json=payload, timeout=120) as r:
                        if r.status_code != 200:
                            err = await r.aread()
                            yield f"data: {json.dumps({'type': 'error', 'content': f'Gemini Error: {err.decode()}'})}\n\n"
                            break

                        async for line in r.aiter_lines():
                            if not line: continue
                            if not line: continue
                            # Clean up the streaming array format [{},{},...]
                            line = line.strip()
                            if line.startswith("["): line = line[1:]
                            if line.endswith("]"): line = line[:-1]
                            if line.startswith(","): line = line[1:]
                            line = line.strip()
                            if not line: continue
                            
                            try:
                                chunk = json.loads(line)
                                parts = chunk.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                                
                                for part in parts:
                                    if "thought" in part:
                                        thought = part.get("text", "")
                                        current_turn_thoughts += thought
                                        yield f"data: {json.dumps({'type': 'thought', 'content': thought})}\n\n"
                                    elif "text" in part:
                                        text = part.get("text", "")
                                        current_turn_text += text
                                        yield f"data: {json.dumps({'type': 'text', 'content': text})}\n\n"
                                    elif "functionCall" in part:
                                        fn = part["functionCall"]
                                        tool_call_found = {"name": fn["name"], "args": fn.get("args", {})}
                                        yield f"data: {json.dumps({'type': 'tool_start', 'content': tool_call_found['name']})}\n\n"
                            except Exception: 
                                pass

                if tool_call_found:
                    t_name = tool_call_found["name"]
                    t_args = tool_call_found["args"]
                    arg_str = json.dumps(t_args)
                    
                    status_msg = "Action: " + t_name.replace("_", " ").title()
                    yield f"data: {json.dumps({'type': 'status', 'content': status_msg})}\n\n"
                    
                    # Execute tool call
                    result = perform_tool_call(request.agent_id, t_name, arg_str, agent_dir, api_key=api_key)
                    
                    yield f"data: {json.dumps({'type': 'tool_result', 'content': str(result)})}\n\n"
                    
                    history.append({"role": "assistant", "content": f"[TOOL: {t_name}({arg_str})]"})
                    history.append({"role": "user", "content": f"SYSTEM TOOL RESULT: {result}"})
                    iteration += 1
                else:
                    final_response_collected = current_turn_text
                    break
                    
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
                break
        
        # Finalization
        history.append({"role": "assistant", "content": final_response_collected})
        with open(internal_history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
            
        ui_history = []
        for h in history:
            if h["role"] == "user" and "SYSTEM TOOL" in str(h["content"]): continue
            ui_history.append({"role": h["role"], "content": sanitize_ruthlessly(h["content"])})
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(ui_history, f, indent=2)

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
@app.post("/run_autonomous")
def run_autonomous_agent(request: ChatRequest):
    """
    Autonomous execution endpoint for master agents.
    Generates a step-by-step plan, executes each step via /chat, and returns the final result.
    Falls back to regular /chat for worker agents.
    """
    agents = load_data()
    agent_data = next((a for a in agents if a["id"] == request.agent_id), None)

    # Fall back to regular chat if agent not found or not a master agent
    if not agent_data or agent_data.get("agentType", "worker") != "master":
        return chat_with_agent(request)

    # Build a summary of connected agents to help plan generation
    connections = agent_data.get("connections", [])
    agents_info_lines = []
    for a in agents:
        if a["id"] == request.agent_id:
            continue
        i_have_them = a["id"] in connections
        they_have_me = request.agent_id in a.get("connections", [])
        if i_have_them or they_have_me:
            perms = ", ".join(a.get("permissions", [])) or "none"
            agents_info_lines.append(
                f"- {a['name']} (ID: {a['id']}): {a.get('responsibility', '')} | Tools: {perms}"
            )
    agents_info = "\n".join(agents_info_lines)

    # ── ROUTING: Task vs. Conversation ──────────────────────────
    provider = request.provider or "gemini"
    api_key = request.api_key or os.getenv("GEMINI_API_KEY", "")

    # If it's just a greeting or casual talk, bypass the planner and route to normal chat.
    if not plan_runner.is_task_request(request.message, api_key, provider):
        safe_log(f"[STATUS:{request.agent_id}] Casual conversation detected - routing to standard chat")
        return chat_with_agent(request)

    # Phase 1: Generate the plan
    steps = plan_runner.run_autonomous(
        request.agent_id,
        request.message,
        api_key,
        provider,
        agents_info
    )

    if not steps:
        # Fallback to normal chat if planning fails
        return chat_with_agent(request)

    # Save plan location for the UI
    plan_path = os.path.join(AGENTS_CODE_DIR, request.agent_id, "plan.md")
    
    # Return plan markdown (without HTML button — the frontend handles button display)
    steps_md = "\n".join([f"{i+1}. {s}" for i, s in enumerate(steps)])
    final_response = (
        f"### 📝 Execution Plan Generated\n\n"
        f"I've analyzed your request and created an autonomous execution plan:\n\n"
        f"{steps_md}\n\n"
        f"---\n"
        f"**Plan file saved to:** `{plan_path}`\n\n"
        f"The execution panel will appear in the training sidebar. Click 'Start Execution' to begin."
    )

    return {"response": final_response}

@app.post("/execute_autonomous")
def execute_autonomous(request: ChatRequest):
    """
    Triggered by the 'Start' button in the UI. 
    Executes the pre-generated plan for an agent.
    """
    provider = request.provider or "gemini"
    api_key = request.api_key or os.getenv("GEMINI_API_KEY", "")
    result = plan_runner.run_execution_loop(
        request.agent_id,
        request.message,
        api_key,
        provider
    )
    return {"response": result}

if __name__ == "__main__":
    # Run on localhost:8000 — loop=asyncio lets multiple agents communicate concurrently
    uvicorn.run(app, host="127.0.0.1", port=8000, loop="asyncio")
