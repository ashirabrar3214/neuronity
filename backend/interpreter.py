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

# -- LLM Models (Abstracting for easy upgrades) --
FAST_MODEL = os.getenv("FAST_MODEL", "gemini-2.0-flash")
REASONING_MODEL = os.getenv("REASONING_MODEL", "gemini-3-flash-preview")

import shutil
import toolkit
import response_formatter
import inspect

import brf
import deliberator

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


def get_beliefs_context():
    """Reads the global identity beliefs (overarching goal)."""
    import brf
    context, _ = brf.get_beliefs()
    return context

def update_beliefs_context(new_goal):
    """Updates the identity beliefs with a new objective."""
    import brf
    return brf.update_belief_context(new_goal)

# â”€â”€â”€ BELIEF BASE SEARCH â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def search_beliefs_base(query, top_k=15):
    """
    Semantically search the belief base (Shared Ledger) for the most relevant entries.
    Returns a formatted string of matched entries for injection into context.
    """
    import brf
    _, entries = brf.get_beliefs()

    if not entries:
        return "Belief Base is empty. No findings have been recorded yet."

    # Score each entry against the query using semantic similarity
    scored = []
    for e in entries:
        text = f"{e.get('fact', '')}"
        score = calculate_belief_relevance(query, text)
        scored.append((score, e))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    lines = [f"### Belief Base Search: '{query}'\n"]
    for score, e in top:
        lines.append(
            f"**[{e.get('agent_id', 'Unknown')}]** | Relevance: {score:.2f}\n"
            f"Fact: {e.get('fact','')}\n"
            f"Source: {e.get('url','No URL')}\n"
        )
    return "\n---\n".join(lines)

def get_beliefs_base_all():
    """Returns all entries from the belief base as a formatted research dump."""
    import brf
    _, entries = brf.get_beliefs()
    
    if not entries:
        return "Belief Base is empty."
    lines = [f"### Full Belief Base â€” {len(entries)} entries\n"]
    for e in entries:
        lines.append(
            f"[{e.get('agent_id', 'Agent')}] {e.get('fact','')}\nSource: {e.get('url','No URL')}"
        )
    return "\n---\n".join(lines)

def calculate_belief_relevance(text1, text2):
    """
    Calculates word-overlap similarity (Keyword Energy) between two belief strings.
    """
    if not text1 or not text2: return 0.0
    stop_words = {"a", "an", "the", "and", "or", "but", "if", "then", "else", "to", "for", "with", "is", "was", "be", "of", "in", "on", "at"}
    words1 = set(w for w in re.findall(r'\w+', text1.lower()) if w not in stop_words)
    words2 = set(w for w in re.findall(r'\w+', text2.lower()) if w not in stop_words)
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union) if union else 0.0

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
            if clean_l.startswith(('-', '*', 'â€¢')):
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

def process_generational_history(history, max_turns=80):
    """
    CONTEXT RETENTION: Protects tool result messages from decay.
    - SYSTEM TOOL RESULT messages (blackboard writes, search results) are NEVER truncated.
    - Normal user/assistant turns follow the generational decay pattern.
    """
    if not history: return []
    raw = history[-max_turns:] if len(history) > max_turns else history
    processed = []

    rev_raw = list(reversed(raw))
    for i, msg in enumerate(rev_raw):
        role = msg.get("role", "user")
        content = str(msg.get("content", "") or "")

        # PERMANENT MESSAGES: Research data and belief updates are NEVER decayed.
        is_tool_result = content.startswith("SYSTEM TOOL RESULT:")
        is_beliefs_confirm = "recorded in the Belief Base" in content
        is_search_result = "### Belief Base Search:" in content
        if is_tool_result or is_beliefs_confirm or is_search_result:
            processed.insert(0, {"role": role, "content": content})
            continue

        # Generation 0 (Last 40 messages): Full detail (Fixes 'Dory' effect)
        if i < 40:
            processed.insert(0, {"role": role, "content": content})

        # Generation 1 (Messages 41-60): Condensed
        elif i < 60:
            if content.startswith("[TOOL:"):
                tool_body = content[len("[TOOL:"):].rstrip("]")
                name_part = tool_body.split("(", 1)[0].strip()
                processed.insert(0, {"role": role, "content": f"[Previously used tool: {name_part}]"})
            else:
                preview = content[:400] + "..." if len(content) > 400 else content
                processed.insert(0, {"role": role, "content": preview})

        # Generation 2 (Messages 61-80): Topic-only metadata
        else:
            if content.startswith("[TOOL:"):
                tool_body = content[len("[TOOL:"):].rstrip("]")
                name_part = tool_body.split("(", 1)[0].strip()
                processed.insert(0, {"role": role, "content": f"[Past action: {name_part}]"})
            else:
                processed.insert(0, {"role": role, "content": f"[Past message: {content[:100]}...]"})

    return processed

async def refresh_conversation_summary(agent_id, history, api_key, provider, current_summary=""):
    """
    Uses the LLM to condense the conversation history and existing summary into a new, 
    leaner cumulative summary. This preserves long-term memory while saving tokens.
    """
    print(f"[STATUS:{agent_id}] Updating Long-term Memory Summary...", flush=True)
    
    formatted_history = ""
    for h in history:
        role = "Agent" if h["role"] == "assistant" else "User"
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
        model = FAST_MODEL
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"role": "user", "parts": [{"text": summary_prompt}]}]
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=payload, timeout=60)
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
async def perform_tool_call(agent_id, tool_name, tool_input, agent_dir, api_key="", session_id=None):
    # --- FIX: Normalize Native Tool Dicts to Legacy Strings ---
    try:
        parsed_args = json.loads(tool_input)
    except:
        parsed_args = tool_input

    extracted_arg = ""
    if isinstance(parsed_args, dict):
        if tool_name == "message_agent" and "target_id" in parsed_args and "message" in parsed_args:
            extracted_arg = f"{parsed_args['target_id']}|{parsed_args['message']}"
        elif tool_name in ["report_generation", "generate_report"]:
             if "topic" in parsed_args and "context" in parsed_args:
                 extracted_arg = f"{parsed_args['topic']}|{parsed_args['context']}"
             elif "title" in parsed_args and "content" in parsed_args:
                 extracted_arg = f"{parsed_args['title']}|{parsed_args['content']}"
             else:
                 extracted_arg = list(parsed_args.values())[0] if parsed_args else ""
        elif tool_name == "write_file" and "filename" in parsed_args and "content" in parsed_args:
             extracted_arg = f"{parsed_args['filename']}|{parsed_args['content']}"
        else:
            if len(parsed_args) >= 1:
                extracted_arg = list(parsed_args.values())[0]
    elif isinstance(parsed_args, str):
        extracted_arg = parsed_args
    else:
        extracted_arg = str(parsed_args)

    tool_input = str(extracted_arg).strip()
    
    # --- Proceed with resolved workingDir ---
    agents = load_data()
    sender_data = next((a for a in agents if a["id"] == agent_id), None)
    working_dir = sender_data.get("workingDir") or sender_data.get("working_dir", "") if sender_data else ""

    if sender_data:
        permissions = sender_data.get("permissions", [])
        
        # Tool Permission Mapping
        tool_to_perm = {
            "web_search": "web search",
            "deep_search": "web search",
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
        # â”€â”€ BELIEF REVISION (BRF) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        import brf
        raw_snippet = tool_input.strip()
        url = ""
        
        url_match = re.search(r'(?:Source:|\[Source:)\s*(https?://[^\]\n,]+)', tool_input, re.IGNORECASE)
        if url_match:
            url = url_match.group(1).strip().rstrip(']')
            raw_snippet = re.sub(r'(?:Source:|\[Source:)[^\]\n]*', '', raw_snippet).strip()

        brf.update_belief_base(agent_id, raw_snippet, url, session_id=session_id)
        safe_log(f"[BRF:{agent_id}] New Belief Added: {raw_snippet[:60]}...")
        return f"Success: Fact recorded in Belief Base."
    
    elif tool_name == "update_plan":
        return await toolkit.update_plan(agent_id, tool_input)

    elif tool_name == "ask_user":
        return await toolkit.ask_user(agent_id, tool_input)

    elif tool_name == "web_search":
        return await toolkit.web_search(tool_input, agent_id, api_key=api_key)
    
    elif tool_name == "deep_search":
        return await toolkit.deep_search(tool_input, agent_id, api_key=api_key)
    
    elif tool_name == "report_generation":
        # Pass agent_name from sender_data
        agent_name = sender_data.get("name", "Agent") if sender_data else "Agent"
        # report_generation is now async in toolkit.py
        return await toolkit.report_generation(agent_id, tool_input, working_dir, api_key, agent_name=agent_name)
    
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

            # â”€â”€ 1. Find sender data
            sender_data = next((a for a in agents if a["id"] == agent_id), None)
            if not sender_data:
                return f"Error: Sender agent {agent_id} not found."
            sender_name = sender_data.get("name", "Unknown Agent")

            # â”€â”€ 3. Find target
            target_data = next((a for a in agents if a["id"] == target_id), None)
            if not target_data:
                return f"Error: Target agent {target_id} not found."

            # â”€â”€ 2. ENFORCE CONNECTION GRAPH (BIDIRECTIONAL)
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

            # â”€â”€ 4. PRE-DELEGATION CAPABILITY CHECK
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

            # â”€â”€ 5. BUILD COMPACT TASK CONTEXT (not full history â€” just enough for the agent to orient)
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
            
            # â”€â”€ 5. Get API key for target provider
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
            
            return await toolkit.message_agent(
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

    elif tool_name == "read_blackboard" or tool_name == "read_beliefs":
        # Semantically search the belief base for relevant entries
        query = tool_input.strip() or "all findings"
        if query.lower() in ["all", "full", ""]:
            return get_beliefs_base_all()
        return search_beliefs_base(query)

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
            return f"âœ… prompt.md has been successfully updated. The new prompt is now active."
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

    elif tool_name == "read_workspace" or tool_name == "read_beliefs_context":
        try:
            content = get_beliefs_context()
            return f"### Global Beliefs Context:\n\n{content or 'No context set.'}"
        except Exception as e:
            return f"Error reading beliefs context: {e}"

    return "i dont have that ability yet"

import shutil
import toolkit
import response_formatter

import brf
import deliberator

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

def update_agent_directory_md(agents_data):
    """
    Synchronizes the 'agent_directory.md' file with the latest agent list.
    This provides agents with a global view of all potential collaborators.
    """
    try:
        dir_path = os.path.join(AGENTS_CODE_DIR, "agent_directory.md")
        os.makedirs(os.path.dirname(dir_path), exist_ok=True)
        
        content = "## PROJECT AGENT DIRECTORY\n"
        content += "Below are all agents currently in this project. Use this to identify who to delegate tasks to.\n\n"
        
        if not agents_data:
            content += "*No agents currently configured.*"
        else:
            for a in agents_data:
                name = a.get("name", "Unknown Agent")
                aid = a.get("id", "Unknown ID")
                resp = a.get("responsibility", "No responsibility set.")
                content += f"- **{name}** (ID: `{aid}`): {resp}\n"
                perms = ", ".join(a.get("permissions", []))
                if perms:
                    content += f"  Capabilities: {perms}\n"
                content += "\n"
        
        with open(dir_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        safe_log(f"!!! [BACKEND ERROR] Failed to update agent_directory.md: {e}")

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        # Synchronize the markdown directory file whenever data changes
        update_agent_directory_md(data)
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

    # 3. prompt.md â€” identity and behavioral rules ONLY.
    prompt_path = os.path.join(agent_dir, "prompt.md")
    prompt_content = f"""# Agent Instructions: {agent_data['name']}
Identity: You are an agent sitting in a desktop PC at UF working for Ashir.
Description: {agent_data['description']}
Responsibility: {agent_data.get('responsibility', 'General purpose assistance')}

## OPERATION RULES
1. **Tool Use**: Use your available tools to complete tasks. Do not explain that you are using a tool; just execute the tool call.
2. **Intent Gate**: Do NOT execute tool calls for casual greetings. Only act if a specific research topic or objective is provided.
3. **Intentions (BDI)**: If you are NOT in autonomous extraction mode, use `update_plan` to record your objective and steps. If you ARE in autonomous mode, just execute the provided step. Use `update_plan` to mark steps as 'Completed' once you finish them.
4. **Knowledge Sharing (BRF)**: Use the `post_finding` tool to record important facts to the Shared Belief Base so other agents can see them.
5. **Citations**: Every fact discovered via research MUST include a `[Source: URL]` citation.
"""
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt_content)

    # 4. Phase 2: BDI Plan - Initialize if not exists
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

    # 6. Agent Manifest (Phase 4) â€” always regenerate so settings changes apply
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

        if os.path.exists(BELIEFS_BASE_FILE):
            os.remove(BELIEFS_BASE_FILE)
            
        volatile_path = os.path.join(AGENTS_CODE_DIR, "volatile_findings.json")
        if os.path.exists(volatile_path):
            os.remove(volatile_path)

        print(f"--- [BACKEND] Cleared history, belief base and volatile ledger for agent: {agent_id}")
        return {"status": "success", "message": "History, logs, and beliefs cleared"}
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
        "name": "ask_user",
        "description": "Stops your current work and asks the user a question to get direction, clarification, or approval to proceed.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "tool_input": {"type": "STRING", "description": "The specific question or summary of findings to present to the user."}
            },
            "required": ["tool_input"]
        }
    })
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
        "description": "Updates your internal BDI intentions. Mandated before messaging the user.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "tool_input": {"type": "STRING", "description": "Format: 'Objective | Step 1, Step 2' OR 'Task Completed'"}
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
    FastAPI endpoint for chat. Wraps the core execute_agent_turn logic.
    """
    return StreamingResponse(
        execute_agent_turn(
            request.agent_id,
            request.message,
            request.api_key,
            request.provider,
            request.mode
        ),
        media_type="text/event-stream"
    )

async def execute_agent_turn(agent_id, message, api_key_input, provider="gemini", mode="work"):
    """
    Core BDI Reasoning Cycle (The Executive).
    Yields SSE-formatted data strings.
    """
    agents = load_data()
    agent_data = next((a for a in agents if a["id"] == agent_id), None)
    if not agent_data:
        yield f"data: {json.dumps({'type': 'error', 'content': 'Agent not found'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    is_training_mode = (mode == "training")
    is_master = agent_data.get("agentType", "worker") == "master"
    agent_dir = os.path.join(AGENTS_CODE_DIR, agent_id)
    history_path = os.path.join(agent_dir, "history.json")
    internal_history_path = os.path.join(agent_dir, "internal_history.json")
    
    # 1. Identity & Context Initialization
    history = []
    if os.path.exists(internal_history_path):
        try:
            with open(internal_history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except: pass
    
    if not history and os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except: pass

    # Extract session_id from tagged message if present
    session_id = None
    session_match = re.search(r'\[SESSION_ID:\s*(\w+)\]', message)
    if session_match:
        session_id = session_match.group(1)
        # Clean the message for the agent's actual turn
        message = message.replace(session_match.group(0), "").strip()

    history.append({"role": "user", "content": message})
    
    # Observe: Update global context with new user message
    update_beliefs_context(message)
    beliefs_context = get_beliefs_context()
    global_obj = beliefs_context.get("global_objective", "Initial exploration.")

    iteration = 0
    final_response_collected = ""
    
    # Build Context Layers (Consolidated for streaming)
    current_agent_prompt = ""
    prompt_file = os.path.join(agent_dir, "prompt.md")
    if os.path.exists(prompt_file):
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                current_agent_prompt = f.read()
        except: pass

    training_tools_block = ""
    if is_training_mode:
        from toolkit import get_training_context
        training_tools_block = get_training_context()

    reachable_agents = []
    connections_list = agent_data.get("connections", [])
    for a in agents:
        if a["id"] in connections_list or agent_id in a.get("connections", []):
            reachable_agents.append(a)
    
    permissions = agent_data.get("permissions", [])
    
    identity_layer = (
        f"IDENTITY: You are an agent named '{agent_data.get('name')}' working for Ashir.\n"
        f"DESCRIPTION: {agent_data.get('description', 'No description.')}\n"
        f"RESPONSIBILITY: {agent_data.get('responsibility', 'No responsibility set.')}\n"
    )
    
    tool_manual_layer = f"## CAPABILITY MANIFEST\n{get_gemini_tools_from_permissions(permissions, len(reachable_agents) > 0, manifest_only=True)}\n"
    
    # Injection: Agent Directory (Project-wide awareness)
    agent_dir_content = ""
    dir_path = os.path.join(AGENTS_CODE_DIR, "agent_directory.md")
    if os.path.exists(dir_path):
        try:
            with open(dir_path, "r", encoding="utf-8") as f:
                agent_dir_content = f.read()
        except: pass

    connected_str = "\n".join([f"- {a['name']} (ID: {a['id']}): {a.get('responsibility', '')}" for a in reachable_agents]) or "None"
    belief_base_context = search_beliefs_base(f"{global_obj} {message}")
    
    transient_task_layer = (
        f"## TRANSIENT TASK CONTEXT\n"
        f"GLOBAL PROJECT OBJECTIVE: {global_obj}\n\n"
        f"{agent_dir_content}\n\n"
        f"IMPORTANT (COLLABORATION RULE): You can ONLY message agents you are DIRECTLY connected to on the canvas.\n"
        f"Reachable Connected Agents:\n{connected_str}\n\n"
        f"### BELIEF BASE FINDINGS (Shared Ledger)\n{belief_base_context}\n"
    )

    system_prompt = f"{identity_layer}\n{tool_manual_layer}\n{transient_task_layer}\n"
    
    if is_master and not is_training_mode:
        system_prompt += (
            "\n## MASTER PROTOCOL\n"
            "You are a MASTER agent. Your priority is task completion. If you are given a task, you MUST proceed immediately to the first execution step.\n"
            "- Do NOT stop to ask for clarification on common topics unless it's truly ambiguous.\n"
            "- For 'Iran War', assume the 1980 conflict OR ask your religion/political agents if they are connected.\n"
            "- Always prioritize calling a tool (web_search, etc.) over providing a conversational text response.\n"
        )
    
    if is_training_mode:
        system_prompt = (
            f"# YOU ARE A CURIOUS AI INTERN: {agent_data.get('name')}\n"
            f"You are currently in **TRAINING MODE**. Focus on learning your role.\n"
            f"## YOUR CURRENT WORK PROMPT (prompt.md):\n```\n{current_agent_prompt}\n```\n"
            f"{training_tools_block}\n"
        )
    
    api_key = api_key_input or os.getenv("GEMINI_API_KEY", "")
    # ROUTING: Classify by explicit mode rather than LLM guessing
    is_task = (mode == "work")
    
    # â”€â”€â”€ BDI REASONING CYCLE: DELIBERATION â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not is_training_mode:
        decision, reason = await deliberator.deliberate(agent_id, message, api_key, "gemini", beliefs_context, history=history)
        yield f"data: {json.dumps({'type': 'thought', 'content': f'BDI Deliberation: {decision} ({reason})'})}\n\n"
        
        if decision == "CLARIFY" and is_task:
            yield f"data: {json.dumps({'type': 'text', 'content': f'I need more information to proceed. {reason}'})}\n\n"
            yield "data: [DONE]\n\n"
            return
        yield f"data: {json.dumps({'type': 'status', 'content': 'Proceeding to executive reasoning...'})}\n\n"
    
    # BDI LIMIT: Reduce max_turns to prevent infinite looping and double-thinking.
    # Master agents handle multi-step tasks via the Planner, so execute_agent_turn
    # should ideally perform one cognitive action (turn) then stop.
    max_turns = 10 if is_task else 1
    if "[AUTO_STEP" in message: max_turns = 5 # Even tighter for autonomous steps

    while iteration < max_turns:
        yield f"data: {json.dumps({'type': 'status', 'content': f'Turn {iteration+1}: Observing context...'})}\n\n"
        llm_context = process_generational_history(history)
        # --- FIX: ALL agents (even Masters) use FAST_MODEL for execution turns ---
        # The Master already did its heavy thinking in planner.py and deliberator.py.
        # Now it just needs to quickly execute the tools and synthesize text.
        model = FAST_MODEL
        gen_config = {"temperature": 0.3, "maxOutputTokens": 8192}

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={api_key}&alt=sse"
        
        gemini_history = []
        for h in llm_context:
            gemini_history.append({
                "role": "user" if h["role"] == "user" else "model",
                "parts": [{"text": h["content"] or "[Empty]"}]
            })
        
        payload = {
            "contents": gemini_history,
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": gen_config,
            "tools": get_gemini_tools_from_permissions(permissions, len(reachable_agents) > 0)
        }
        
        yield f"data: {json.dumps({'type': 'status', 'content': f'Generating response (Turn {iteration+1})...'})}\n\n"

        current_turn_text = ""
        current_turn_thoughts = ""
        tool_call_found = None

        try:
            print(f"[STATUS:{agent_id}] Turn {iteration+1}: Streaming from {model} (SSE Mode)...", flush=True)
            async with httpx.AsyncClient() as client:
                async with client.stream("POST", url, json=payload, timeout=120) as r:
                    if r.status_code != 200:
                        err = await r.aread()
                        yield f"data: {json.dumps({'type': 'error', 'content': f'Gemini Error: {err.decode()}'})}\n\n"
                        break

                    async for line in r.aiter_lines():
                        line = line.strip()
                        if not line: continue
                        if line.startswith("data: "):
                            json_str = line[6:]
                            if json_str == "[DONE]": continue
                            try:
                                chunk = json.loads(json_str)
                                candidate = chunk.get("candidates", [{}])[0]
                                finish_reason = candidate.get("finishReason", "")
                                if finish_reason and finish_reason != "STOP":
                                    yield f"data: {json.dumps({'type': 'error', 'content': f'Model halted early: {finish_reason}'})}\n\n"
                                    break
                                    
                                parts = candidate.get("content", {}).get("parts", [])
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
                            except Exception as e:
                                safe_log(f"!!! Error parsing SSE chunk: {e} | Content: {json_str[:100]}...")
                                continue

            if not tool_call_found and current_turn_text:
                tool_match = re.search(r'\[TOOL:\s*(\w+)\((.*?)\)\]', current_turn_text)
                if tool_match:
                    t_name = tool_match.group(1)
                    t_args_str = tool_match.group(2)
                    current_turn_text = current_turn_text.replace(tool_match.group(0), "").strip()
                    try:
                        t_args = json.loads(t_args_str) if t_args_str.startswith("{") else t_args_str
                    except: t_args = t_args_str
                    tool_call_found = {"name": t_name, "args": t_args}
                    yield f"data: {json.dumps({'type': 'tool_start', 'content': t_name})}\n\n"

            if tool_call_found:
                t_name = tool_call_found["name"]
                t_args = tool_call_found["args"]
                arg_str = json.dumps(t_args)
                status_msg = "Action: " + t_name.replace("_", " ").title()
                yield f"data: {json.dumps({'type': 'status', 'content': status_msg})}\n\n"
                
                # Execute tool call
                result = await perform_tool_call(agent_id, t_name, arg_str, agent_dir, api_key=api_key, session_id=session_id)
                yield f"data: {json.dumps({'type': 'tool_result', 'content': str(result)})}\n\n"
                
                # BDI EARLY EXIT: If the agent committed to a plan or posted a finding,
                # we yield the result and break the turn loop. This prevents the
                # "Thinking about thoughts" stall and deep thinking recursion.
                if t_name in ["update_plan", "post_finding", "report_generation"]:
                    safe_log(f"[BDI:EXIT] Agent called {t_name} — terminating Turn {iteration+1} and yielding.")
                    
                    # Yield as text so the UI accumulates it in responseContent
                    # and processPlanResponse can detect the intention header.
                    display_result = str(result)
                    if t_name == "update_plan":
                        display_result = f"### 🎯 Intentions Updated\n\n{result}"
                    
                    # Yield ONLY the clean display result to the UI, not the raw tool call
                    yield f"data: {json.dumps({'type': 'text', 'content': f'\n\n{display_result}'})}\n\n"
                    
                    history.append({"role": "assistant", "content": f"[TOOL: {t_name}({arg_str})]"})
                    history.append({"role": "user", "content": f"SYSTEM TOOL RESULT: {result}"})
                    final_response_collected = f"Committed action: {t_name}. Result: {result}"
                    break
                
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
        
        content = str(h["content"])
        if h["role"] == "assistant":
            # Sanitize: replace [TOOL: name(args)] with Executed: name to keep UI clean
            content = re.sub(r'\[TOOL:\s*(\w+)\(.*?\)]', r'Executed: \1', content)

        ui_history.append({"role": h["role"], "content": sanitize_ruthlessly(content)})
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(ui_history, f, indent=2)

    yield "data: [DONE]\n\n"

@app.post("/run_autonomous")
async def run_autonomous_agent(request: ChatRequest):
    """
    Autonomous execution endpoint for master agents.
    Generates a step-by-step plan, executes each step via /chat, and returns the final result.
    Falls back to regular /chat for worker agents.
    """
    agents = load_data()
    agent_data = next((a for a in agents if a["id"] == request.agent_id), None)

    # Fall back to regular chat if agent not found or not a master agent
    if not agent_data or agent_data.get("agentType", "worker") != "master":
        return await chat_with_agent(request)

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

    # â”€â”€ ROUTING: Task vs. Conversation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    provider = request.provider or "gemini"
    api_key = request.api_key or os.getenv("GEMINI_API_KEY", "")

    # If we are in training mode, bypass the autonomous planner entirely.
    if request.mode != "work":
        return await chat_with_agent(request)

    # Phase 1: Generate the intentions
    import planner
    steps = await planner.run_autonomous(
        request.agent_id,
        request.message,
        api_key,
        provider,
        agents_info
    )

    if not steps:
        # Fallback to normal chat if planning fails
        return await chat_with_agent(request)

    # Save plan location for the UI
    plan_path = os.path.join(AGENTS_CODE_DIR, request.agent_id, "intentions.json")
    
    # Return plan markdown (without HTML button â€” the frontend handles button display)
    steps_md = "\n".join([f"{i+1}. {s}" for i, s in enumerate(steps)])
    final_response = (
        f"### ðŸŽ¯ Intentions Generated (BDI)\n\n"
        f"I've committed to the following intentions to satisfy your request:\n\n"
        f"{steps_md}\n\n"
        f"---\n"
        f"**Intentions file:** `{plan_path}`\n\n"
        f"Click 'Start Execution' to begin following these intentions."
    )

    return {"response": final_response}

@app.post("/execute_autonomous")
async def execute_autonomous(request: ChatRequest):
    """
    Triggered by the 'Start' button in the UI. 
    Executes the pre-generated plan for an agent.
    """
    provider = request.provider or "gemini"
    api_key = request.api_key or os.getenv("GEMINI_API_KEY", "")
    import planner
    result = await planner.run_execution_loop(
        request.agent_id,
        request.message,
        api_key,
        provider
    )
    return {"response": result}

if __name__ == "__main__":
    # Run on localhost:8000 â€” loop=asyncio lets multiple agents communicate concurrently
    uvicorn.run(app, host="127.0.0.1", port=8000, loop="asyncio")
