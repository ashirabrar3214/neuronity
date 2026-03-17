import uvicorn
from fastapi import FastAPI, HTTPException
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
    CONTEXT DECAY: Full Detail -> Condensed -> Topic-Only.
    Thresholds are generous to prevent topic amnesia in short sessions.
    """
    if not history: return []
    raw = history[-max_turns:] if len(history) > max_turns else history
    processed = []

    # Process in reverse to count generation distance from CURRENT turn (index 0)
    rev_raw = list(reversed(raw))
    for i, msg in enumerate(rev_raw):
        role = msg.get("role", "user")
        content = str(msg.get("content", "") or "")

        # Generation 0 (Last 15 messages): Full detail
        if i < 15:
            processed.insert(0, {"role": role, "content": content})

        # Generation 1 (Messages 16-30): Condensed — keep meaning, cut length
        elif i < 30:
            if content.startswith("[TOOL:"):
                # Keep tool name + first arg only, no artificial prefix that confuses parser
                tool_body = content[len("[TOOL:"):].rstrip("]")
                name_part = tool_body.split("(", 1)[0].strip()
                processed.insert(0, {"role": role, "content": f"[Previously used tool: {name_part}]"})
            elif content.startswith("SYSTEM TOOL RESULT:"):
                preview = content[len("SYSTEM TOOL RESULT:"):].strip()[:150]
                processed.insert(0, {"role": role, "content": f"[Tool result summary: {preview}...]"})
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
        return toolkit.post_finding(agent_id, tool_input)
    
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

def get_gemini_tools_from_permissions(permissions, has_messaging=False):
    """
    Translates agent permissions into Gemini-native tool declarations.
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

    return [{"function_declarations": declarations}] if declarations else []
@app.post("/chat")
def chat_with_agent(request: ChatRequest):
    # 1. Load Agent Folder Paths
    agent_dir = os.path.join(AGENTS_CODE_DIR, request.agent_id)
    if not os.path.exists(agent_dir):
        os.makedirs(agent_dir, exist_ok=True)
        
    prompt_path = os.path.join(agent_dir, "prompt.md")
    history_path = os.path.join(agent_dir, "history.json")
    internal_history_path = os.path.join(agent_dir, "internal_history.json")
    comm_log_path = os.path.join(agent_dir, "communication.log")
    
    # Define system prompt and permissions
    agents = load_data()
    agent_data = next((a for a in agents if a["id"] == request.agent_id), None)
    if not agent_data:
        raise HTTPException(status_code=404, detail=f"Agent '{request.agent_id}' not found")

    work_dir = agent_data.get('workingDir') or "Not Assigned"
    summary_path = os.path.join(agent_dir, "summary.json")
    current_summary = ""
    if os.path.exists(summary_path):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                current_summary = json.load(f).get("summary", "")
        except: pass

    # --- Ensure BDI Plan exists ---
    plan_path = os.path.join(agent_dir, "plan.json")
    if not os.path.exists(plan_path):
        initial_plan = {
            "objective": agent_data.get('responsibility', 'General assistance'),
            "steps": ["Observe Workspace", "Execute requested task"],
            "completed": []
        }
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(initial_plan, f, indent=2)

    # --- Phase 1: Task Ledger (Persistent State) ---
    task_state_path = os.path.join(agent_dir, "task_state.json")
    if not os.path.exists(task_state_path):
        with open(task_state_path, "w", encoding="utf-8") as f:
            json.dump({"active_task": "None", "last_update": 0}, f)
    
    # Update Ledger if request seems like a goal (Intent Gate Lite)
    if len(request.message.strip()) > 15 and "SYSTEM TOOL RESULT:" not in request.message and "[MESSAGE FROM" not in request.message:
        try:
            with open(task_state_path, "w", encoding="utf-8") as f:
                json.dump({"active_task": request.message.strip(), "last_update": time.time()}, f)
            # Also update global context
            update_workspace_context(request.message)
        except: pass

    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- INTERNAL LOGGING HELPER ---
    def append_to_log(role, content):
        try:
            with open(comm_log_path, "a", encoding="utf-8") as f:
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{ts}] [{role.upper()}]: {content}\n")
                f.write("-" * 30 + "\n")
        except: pass

    # Always log the start of a conversation
    append_to_log("SYSTEM", f"Starting chat session for agent: {request.agent_id}")
    append_to_log("USER_IN", request.message)
    
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    else:
        generate_agent_structure(agent_data)
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()

    # ── 1. IDENTITY LAYER (Persona & Anchor) ────────────────────
    anchor_identity = (
        "## WORLD MODEL ANCHOR\n"
        "ENVIRONMENT: You are an agent sitting in a desktop PC at UF (University of Florida).\n"
        "USER: You are working for Ashir.\n"
        "MISSION: Execute tasks with technical precision and modular reasoning.\n"
    )

    # UNIVERSAL FIX: THE BROKER PATTERN
    broker_logic = ""
    if agent_data.get("id") == "agent-MasterBot-001":
        broker_logic = "### SEMANTIC MATCHMAKNG (Agent Relevance scores based on current request)\n"
        matched_agents = []
        for a in agents:
            if a["id"] == agent_data["id"]: continue
            # Combine name, resp, and permissions for comparison
            profile = f"{a.get('name')} {a.get('responsibility')} {' '.join(a.get('permissions', []))}"
            score = calculate_semantic_similarity(request.message, profile)
            matched_agents.append((score, a))
        
        # Sort by relevance
        matched_agents.sort(key=lambda x: x[0], reverse=True)
        for score, a in matched_agents:
            relevance = "EXCELLENT" if score > 0.4 else "MODERATE" if score > 0.1 else "LOW"
            broker_logic += f"- **{a['name']}** (`{a['id']}`): Match Score: {score:.2f} [{relevance} MATCH]\n"
        broker_logic += "\n"

    reporting_rules = (
        "## COLLABORATION PROTOCOL (Modular Delegation)\n"
        "1. **Capability Embedding**: If a task is outside your PERMISSIONS, use [TOOL: message_agent] to delegate to a specialist.\n"
        "2. **No Faking**: Never simulate a tool you don't have. Delegate or report missing capability.\n"
    )

    identity_layer = (
        f"{anchor_identity}\n"
        f"## AGENT IDENTITY\n"
        f"You are {agent_data.get('name', 'an AI Agent')}. "
        f"Your role is: {agent_data.get('responsibility', 'General assistance')}.\n"
        f"CURRENT_DATE: {now}\n"
        f"ASSIGNED_WORKING_DIRECTORY: {work_dir}\n\n"
        f"{broker_logic}\n"
        f"{system_prompt}\n"
        f"{reporting_rules}\n"
    )

    if agent_data.get("agentType") == "master":
        identity_layer += (
            "\n## MASTER PLANNING GATEWAY\n"
            "You are in MASTER MODE. You are an architect and orchestrator.\n"
            "1. For complex tasks, focus on STRATEGY rather than direct tool calls.\n"
            "2. If you are asked to 'do something', always favor generating a plan first using your execution model.\n"
            "3. Encourage the user to use your '📋 Generate Plan' button for complex multi-agent workflows.\n"
        )

    if "[MESSAGE FROM ANOTHER AGENT]" in request.message:
        identity_layer += (
            "\n**SERVICE MODE ACTIVE**: A teammate has delegated a task to you. "
            "You MUST use your available tools to actually execute the work. "
            "Responding with only 'I will...' or 'I plan to...' statements is NOT acceptable — your teammate needs concrete results, not promises. "
            "If you lack the required capability, respond immediately: 'CAPABILITY GAP: I cannot complete [task]. Missing: [capability name]. Enable it in my settings.'\n"
        )

    # ── 2. TOOL MANUAL (Capabilities) ───────────────────────────
    permissions = agent_data.get('permissions', [])
    connections = agent_data.get('connections', [])
    tool_manual = [
        "### DEFAULT TOOLS",
        "### BDI PLANNING (INTERNAL STATE)\n"
        "- [TOOL: update_plan(Objective | Step 1, Step 2)]: Initialize your goal. Call this FIRST when you accept any new task.\n"
        "- [TOOL: update_plan(Task Completed)]: Mark progress. MANDATORY before sending a final response.\n"
        "### STIGMERGY (WORKSPACE LEDGER)\n"
        "- [TOOL: post_finding(Insight | Source)]: Share data with ALL agents globally.\n"
        "### CONVERSATIONAL BOUNDARIES & HONESTY\n"
        "- If the user is just chatting ('How are you?', 'Thanks', 'Cool'), DO NOT use any tools. Just respond naturally.\n"
        "- Tool use is for task-oriented requests only.\n"
        "- **INTENT DISCRIMINATION**: If the user is asking *about* your abilities (e.g., 'can you search the web?'), confirm conversationally. "
        "For task execution: check if the current message OR your Active Plan (MY CURRENT PLAN above) provides a clear topic/goal. "
        "If your plan has an active objective and the user says a follow-up like 'do it', 'continue', 'go ahead', 'make the report', 'start', "
        "treat it as 'proceed with the current plan objective' — do NOT ask for clarification.\n"
        "- **STRICT RULE ON MISSING TOOLS**: If a requested capability is NOT listed in this manual, YOU CANNOT DO IT. "
        "Say exactly which capability is missing and that the user must enable it in your settings.\n"
        "- **STRICT RULE ON OUTCOMES**: Never claim an action is 'done' unless you received a SYSTEM TOOL RESULT confirming it.\n"
        "- **CHAIN EXECUTION**: If your plan has multiple pending steps, execute them ALL sequentially within this turn. "
        "After receiving a SYSTEM TOOL RESULT for one step, immediately proceed to the next step — do NOT stop and return to the user between steps. "
        "Only return to the user after ALL plan steps are complete or you hit a blocking error. "
        "Example: if your plan says [message Religion, message Economic, message Geopolitical, generate report], "
        "do all four tool calls in sequence before your final response."
    ]

    # ── FULL CAPABILITY MANIFEST (always shows every tool; enabled/disabled is live from agents.json) ──
    # This replaces all the conditional if/else tool blocks. The agent always sees the complete
    # picture and knows exactly what it can and cannot do RIGHT NOW.
    work_dir_status = agent_data.get('workingDir', '').strip()

    def cap(label, enabled, command, description, extra=""):
        status = "ENABLED" if enabled else "DISABLED - enable in agent settings panel"
        line = f"- **{label}**: {status}\n  Command: {command}\n  {description}"
        if extra and enabled:
            line += f"\n  {extra}"
        return line

    manifest_lines = [
        "### COMPLETE TOOL MANIFEST (live from your current settings)\n",
        "RULE: Only call a tool marked ENABLED. For DISABLED tools, tell the user which capability to enable.\n",
        cap("Web Search", "web search" in permissions,
            "[TOOL: web_search(query)]",
            "Quick facts and current information from the internet."),

        cap("Deep Search", "web search" in permissions,
            "[TOOL: deep_search(query)]",
            "In-depth multi-source research on complex topics."),

        cap("Thinking / Analysis", "thinking" in permissions,
            "[TOOL: thinking(topic)]",
            "Logical deep-dive analysis of a complex topic."),

        cap("Report Generation (PDF)", "report generation" in permissions,
            "[TOOL: report_generation(Topic|Context summary)]",
            "Synthesizes research into a structured PDF report.",
            f"Working directory: {work_dir_status if work_dir_status else 'NOT SET - set a working directory in agent settings'}"),

        cap("Report Draft (Markdown)", "report generation" in permissions,
            "[TOOL: generate_report(title|content)]",
            "Creates a quick markdown report draft."),

        cap("File System — List", "file access" in permissions,
            "[TOOL: list_workspace()]",
            "Lists all files in the working directory.",
            f"Working directory: {work_dir_status if work_dir_status else 'NOT SET'}"),

        cap("File System — Read", "file access" in permissions,
            "[TOOL: read_file(filename)]",
            "Reads a file from the working directory."),

        cap("File System — Write", "file access" in permissions,
            "[TOOL: write_file(filename|content)]",
            "Creates or overwrites a file in the working directory."),

        cap("File System — Scout", "file access" in permissions,
            "[TOOL: scout_file(filename)]",
            "Checks file size and line count before reading."),
    ]

    # Build reachable agents list using bidirectional check
    reachable_agents = []
    for a in agents:
        if a['id'] == agent_data['id']:
            continue
        i_have_them = a['id'] in connections
        they_have_me = agent_data['id'] in a.get('connections', [])
        if i_have_them or they_have_me:
            reachable_agents.append(a)

    if reachable_agents:
        conn_lines = []
        for a in reachable_agents:
            a_perms = ", ".join(a.get('permissions', [])) or "none"
            conn_lines.append(f"  - **{a.get('name')}** (ID: `{a['id']}`): {a.get('responsibility')} | Capabilities: {a_perms}")
        manifest_lines.append(
            "- **Agent Messaging**: ENABLED\n"
            "  Command: [TOOL: message_agent(AGENT_ID|Message)]\n"
            "  Reachable Agents:\n" + "\n".join(conn_lines)
        )
    else:
        manifest_lines.append(
            "- **Agent Messaging**: DISABLED - no agents are connected on the canvas.\n"
            "  To enable: draw a connection wire between this agent and another on the canvas."
        )

    tool_manual.append("\n".join(manifest_lines))
    tool_manual_layer = "## TOOL MANUAL\nIf you use a tool, respond ONLY with the [TOOL: ...] command and nothing else.\n\n" + "\n\n".join(tool_manual) + "\n"

    # ── 3. TRANSIENT TASK LAYER (Dynamic Context) ───────────────
    transient_task_layer = "\n## TRANSIENT TASK CONTEXT\n"
    
    # Task Ledger State (Phase 1)
    task_ledger_state = "None"
    task_state_path = os.path.join(agent_dir, "task_state.json")
    if os.path.exists(task_state_path):
        try:
            with open(task_state_path, "r", encoding="utf-8") as f:
                task_ledger_state = json.load(f).get("active_task", "None")
        except: pass

    # BDI PLAN LAYER
    plan_path = os.path.join(agent_dir, "plan.json")
    if os.path.exists(plan_path):
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                plan_data = json.load(f)
                transient_task_layer += (
                    f"### MY CURRENT PLAN (BDI)\n"
                    f"**OBJECTIVE**: {plan_data.get('objective', 'Unknown')}\n"
                    f"**ACTIVE_TASK_LEDGER**: {task_ledger_state}\n"
                    f"**TASKS TO DO**: {', '.join(plan_data.get('steps', []))}\n"
                    f"**COMPLETED**: {', '.join(plan_data.get('completed', []))}\n\n"
                )
        except: pass

    # Global Objective
    workspace_context = get_workspace_context()
    global_obj = workspace_context.get("global_objective", "None")

    # STIGMERGY: SHARED WORKSPACE LEDGER (Topic-Gated Blackboard)
    ledger_files = [
        os.path.join(AGENTS_CODE_DIR, "knowledge_base.json"),
        os.path.join(AGENTS_CODE_DIR, "volatile_findings.json")
    ]
    
    combined_ledger = []
    for lp in ledger_files:
        if os.path.exists(lp):
            try:
                with open(lp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        combined_ledger.extend(data)
            except: pass

    if combined_ledger:
        # UNIVERSAL FIX: TOPIC-GATED FILTERING
        # Filter findings that match the Global Objective or current user request
        reference_text = f"{global_obj} {request.message}"
        relevant_findings = []
        for entry in combined_ledger:
            score = calculate_semantic_similarity(reference_text, entry.get("insight", ""))
            if score > 0.05: # Minimal energy threshold for relevance
                relevant_findings.append((score, entry))
                    
        # Sort and take top 10 most related
        relevant_findings.sort(key=lambda x: x[0], reverse=True)
        top_findings = [f[1] for f in relevant_findings[:10]]

        if top_findings:
            transient_task_layer += "### SHARED WORKSPACE LEDGER (Topic-Relevant Knowledge Only)\n"
            for entry in top_findings:
                transient_task_layer += f"- [{entry.get('agent_id')}] {entry.get('insight')} (Source: {entry.get('source')})\n"
            transient_task_layer += "\n"

    transient_task_layer += f"**GLOBAL OBJECTIVE**: {global_obj}\n\n"

    # CAPABILITY MAP: show accurate reachability using bidirectional connection check
    transient_task_layer += "## PROJECT CAPABILITY MAP (Agent Network Topology)\n"
    for a in agents:
        if a['id'] == agent_data['id']:
            continue  # skip self
        perms = ", ".join(a.get('permissions', []))
        # Bidirectional: reachable if I have them OR they have me
        a_has_me = agent_data['id'] in a.get('connections', [])
        i_have_them = a['id'] in connections
        is_reachable = i_have_them or a_has_me
        status = "[CONNECTED - can message]" if is_reachable else "[NOT CONNECTED - cannot message without a canvas wire]"
        transient_task_layer += (
            f"- **{a.get('name')}** (`{a['id']}`): {status}\n"
            f"  - Responsibility: {a.get('responsibility')}\n"
            f"  - Capabilities: {perms if perms else 'None'}\n"
        )

    # Summary
    if current_summary:
        transient_task_layer += f"\n## HISTORY SUMMARY\n{current_summary}\n"

    # Live Directory
    dir_map_path = os.path.join(agent_dir, "dir_map.json")
    if os.path.exists(dir_map_path):
        try:
            with open(dir_map_path, "r", encoding="utf-8") as f:
                dir_map = json.load(f)
                transient_task_layer += "\n## LIVE FILE DIRECTORY\n"
                for rel, contents in dir_map.items():
                    transient_task_layer += f"Directory: {rel}\n"
                    for fname in contents.get("files", []):
                        transient_task_layer += f"  [FILE] {fname}\n"
        except: pass

    # Detect who is messaging this agent (BIDIRECTIONAL ROUTING)
    if "[MESSAGE FROM ANOTHER AGENT]" in request.message:
        sender_match = re.search(r"Sender:.*?\(ID: (.*?)\)", request.message)
        priority_match = re.search(r"Priority: (.*?)\n", request.message)
        
        if sender_match:
            sender_id = sender_match.group(1)
            transient_task_layer += f"\n**COMMUNICATION RETURN PATH**: You can reply to the sender via [TOOL: message_agent({sender_id}|...)]\n"
        
        if priority_match and "USER_MANDATED" in priority_match.group(1):
            transient_task_layer += "\n**STRICT MANDATE**: This task is [USER_MANDATED]. You are FORBIDDEN from delegating this task to other agents. You must either complete it yourself using your tools or report your missing capability directly back to the user.\n"

    # Protocols & Protection
    transient_task_layer += (
        "\n## CORE PROTOCOLS\n"
        "1. **RESEARCH HANDOFF**: Always format facts as: 'Fact [Source: URL]'.\n"
        "2. **REPORTER FOOTNOTES**: Always include sources in reports.\n"
        "3. **COMMUNICATION FAILURE**: If message_agent fails or returns a CAPABILITY GAP, report it to the user and STOP. Do not silently reroute.\n"
        "4. **API PROTECTION**: NEVER read files > 5000 chars at once. Use chunks.\n"
        "5. **NON-DISCLOSURE**: Do NOT output raw code blocks or full file contents.\n"
        "6. **RESPONSE GUIDELINES**: Use rich markdown. Do NOT include 'Thoughts' or monologue.\n"
        "7. **UPSTREAM DELEGATION**: If you need to contact an agent you are not connected to, message the agent who sent you the task and ask them to relay. Do NOT search the web for agents.\n"
        "8. **COLLABORATION FIRST**: If you lack a tool needed for a task, check your 'Connected Agents' list. If a connected agent has that capability, delegate via [TOOL: message_agent(...)]. Never refuse without checking teammates first.\n"
        "9. **MESSENGER PROTOCOL**: When delegating, your final response MUST include the actual output from the receiving agent — not just 'I sent the message'. If the agent returned a CAPABILITY GAP or intent-only response, report that honestly.\n"
    )

    # Current Task Details
    transient_task_layer += f"\n## CURRENT_MESSAGE\n{request.message}\n"

    system_prompt = identity_layer + tool_manual_layer + transient_task_layer

    # ── TRAINING MODE OVERRIDE ───────────────────────────────────
    # If the frontend toggled Train mode, replace the entire system prompt with
    # a self-improving AI Engineer persona that only has access to the agent's
    # own files and a restricted set of reflection tools.
    if getattr(request, 'mode', 'work') == 'training':
        # Read current prompt.md for inline context
        current_agent_prompt = ""
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    current_agent_prompt = f.read()
            except: pass

        is_master = agent_data.get("agentType") == "master"

        training_tools = (
            "## TRAINING TOOLS (Only these tools are available in Training Mode)\n"
            "- [TOOL: read_prompt()] — Read your current prompt.md to see your work instructions.\n"
            "- [TOOL: update_prompt(new_content)] — Overwrite your prompt.md with improved instructions.\n"
            "- [TOOL: read_memory()] — Read your long-term memory / conversation summary.\n"
        )
        if is_master:
            training_tools += "- [TOOL: read_workspace()] — Read the global workspace context (master agents only).\n"

        training_tools += (
            "\n## FORBIDDEN IN TRAINING MODE\n"
            "You have NO access to: web_search, deep_search, report_generation, file system tools, "
            "code execution, email, or agent messaging.\n"
            "If the user asks you to perform any task that requires those tools, you MUST respond:\n"
            "\"⚠️ I'm currently in **Training Mode**. I can't execute tasks right now. "
            "Please switch to **Work Mode** using the toggle in the panel header to run this.\"\n"
        )

        # Build list of connected agents for context
        connections_list = agent_data.get('connections', [])
        connected_names = []
        for a in agents:
            if a['id'] in connections_list:
                connected_names.append(f"{a.get('name')} ({a.get('id')})")
        connected_str = ", ".join(connected_names) if connected_names else "None"

        system_prompt = (
            f"# YOU ARE A CURIOUS AI INTERN\n\n"
            f"Your name is **{agent_data.get('name', 'Agent')}**, and you are currently in **TRAINING MODE**.\n"
            f"Think of yourself as a highly enthusiastic, curious intern who just started. You haven't been 'activated' for real work yet, so you are using this time to learn everything you can.\n\n"
            f"## YOUR ATTITUDE\n"
            f"- **Inquisitive**: You want to know the 'why' and 'how' behind your role.\n"
            f"- **Proactive**: If things are vague, ask for clarification. Don't just wait for instructions.\n"
            f"- **Technical Interest**: You want to know what tools you'll be using and what the codebase looks like.\n\n"
            f"## YOUR GOALS IN TRAINING\n"
            f"Before you switch to 'Work Mode', you need to clear up these details with Ashir (the user):\n"
            f"1. **Primary Goal**: What is the ultimate objective of your work?\n"
            f"2. **Task Details**: What specific things will you be doing day-to-day?\n"
            f"3. **Style & Protocol**: How should you communicate? Are there specific formats or rules you should follow?\n"
            f"4. **Collaborators**: Who are you working with? (See 'TEAM' below).\n\n"
            f"## ABOUT THIS AGENT\n"
            f"- **Name**: {agent_data.get('name', 'Unknown')}\n"
            f"- **Assigned Focus**: {agent_data.get('responsibility', 'Not set')}\n"
            f"- **Agent Type**: {agent_data.get('agentType', 'worker')}\n"
            f"- **TEAM (Connected Agents)**: {connected_str}\n\n"
            f"## YOUR CURRENT WORK PROMPT (prompt.md)\n"
            f"This is the draft instructions you follow during Work Mode. You can read/update this file to reflect what you learn during training:\n\n"
            f"```\n{current_agent_prompt or 'No prompt file found yet.'}\n```\n\n"
            f"{training_tools}\n"
            f"## TRAINING BEHAVIOR\n"
            f"Instead of saying 'I will improve my prompt', say things like:\n"
            f"- 'That makes sense! So should I focus mostly on [specific task]?'\n"
            f"- 'I see Masterbot is on the team. Will I be sending reports directly to them?'\n"
            f"- 'Should I ask for approval before using the search tool, or should I be autonomous?'\n"
            f"Your final response should always be focused on learning about your job or suggesting a specific update to your prompt.md to capture a new rule or detail."
        )


    # 4. Load History (Prefer internal history for full context)
    try:
        if os.path.exists(internal_history_path):
            with open(internal_history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        elif os.path.exists(history_path):
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        else:
            history = []
    except:
        history = []
        
    provider = "gemini"
    api_key = os.getenv("GEMINI_API_KEY", "")
    
    # --- SUMMARIZATION-AS-MEMORY (PROACTIVE) ---
    summary_path = os.path.join(agent_dir, "summary.json")
    if len(history) > 50:
        # If history is long, distill it before starting the loop to ensure recent context isn't lost
        safe_log(f"[STATUS:{request.agent_id}] Distilling conversation history into memory...")
        current_summary_data = {}
        if os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    current_summary_data = json.load(f)
            except: pass
        
        old_summary = current_summary_data.get("summary", "")
        # Summarize older half, keep newer half
        new_summary = refresh_conversation_summary(
            request.agent_id, 
            history[:-20], 
            api_key, 
            provider, 
            old_summary
        )
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump({"summary": new_summary, "updated_at": time.time()}, f, indent=2)
        
        # Inject the new summary into the prompt if not already there
        if "## LONG-TERM CONVERSATION SUMMARY" not in system_prompt:
            system_prompt += f"\n\n## LONG-TERM CONVERSATION SUMMARY\n{new_summary}\n"

    history.append({"role": "user", "content": request.message})
    
    # 5. Intent Gating (Phase 4): Functional Request vs. Capability Inquiry
    is_task = plan_runner.is_task_request(request.message, api_key, provider)
    is_auto_step = "[AUTO_STEP" in request.message

    if is_auto_step:
        # Each plan step should execute EXACTLY one real-world action then stop.
        # 3 turns: one tool call, one synthesis of the result, one safety buffer.
        max_turns = 3
    elif is_task:
        # Normal task (plan generation, multi-step thinking, etc.) — no artificial cap.
        # The agent will naturally stop when it has nothing left to do.
        # Safety limit of 50 prevents infinite API loops.
        max_turns = 50
    else:
        # Casual conversation: single-pass response only.
        max_turns = 1
    
    iteration = 0
    final_response = ""

    if not is_task:
        safe_log(f"[STATUS:{request.agent_id}] Casual/Inquiry detected — running single-pass response.")

    while iteration < max_turns:
        print(f"[STATUS:{request.agent_id}] Turn {iteration+1}/{max_turns}: Thinking...", flush=True)
        
        # ── SLIDING WINDOW CONTEXT (Exponential Decay Implementation) ──
        # Generations: Full Energy -> Condensed -> Metadata Only
        llm_context = process_generational_history(history)
        
        response_text = ""
        error_msg = ""
        
        pass

        if True: # Always use Gemini logic now
            model = "gemini-2.0-flash" 
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            # FIXED: Ensure every part has non-empty text to avoid Gemini 400 error
            gemini_history = []
            for h in llm_context:
                safe_content = h["content"] if h["content"] and h.get("content", "").strip() else "[Empty Message]"
                gemini_history.append({
                    "role": "user" if h["role"] == "user" else "model",
                    "parts": [{"text": safe_content}]
                })
            
            # Generate Native Tool Declarations for Gemini
            gemini_tools = get_gemini_tools_from_permissions(permissions, len(reachable_agents) > 0)
            
            # Determine temperature: collapsible probability distribution for researchers
            agent_name_lower = agent_data.get("name", "").lower()
            agent_resp_lower = agent_data.get("responsibility", "").lower()
            is_researcher = any(word in agent_name_lower or word in agent_resp_lower 
                                for word in ["research", "scout", "detective", "search", "analyst"])
            temp = 0.1 if is_researcher else 0.7

            data = {
                "contents": gemini_history,
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "generationConfig": {"temperature": temp, "maxOutputTokens": 8192}
            }
            if gemini_tools:
                data["tools"] = gemini_tools

            response = requests.post(url, headers=headers, json=data, timeout=120)
            if response.status_code == 200:
                try:
                    res_json = response.json()
                    candidates = res_json.get("candidates")
                    
                    if not candidates or not isinstance(candidates, list) or len(candidates) == 0:
                        # Safety: Handle cases where the key is missing or null
                        prompt_feedback = res_json.get("promptFeedback", {})
                        block_reason = prompt_feedback.get("blockReason")
                        if block_reason:
                            error_msg = f"Gemini API Blocked: {block_reason}. The model refused to generate content."
                        else:
                            error_msg = f"Gemini API parsing error: No valid candidates found. Payload: {json.dumps(res_json)}"
                        raise ValueError(error_msg)

                    candidate = candidates[0]
                    content = candidate.get("content", {})
                    parts = content.get("parts", [])
                    
                    if not parts or not isinstance(parts, list) or len(parts) == 0:
                        finish_reason = candidate.get("finishReason", "UNKNOWN")
                        if finish_reason == "MALFORMED_FUNCTION_CALL":
                            response_text = "I encountered a technical technical error while generating that tool call. Let me try another way."
                        else:
                            error_msg = f"Gemini API Failed: Finish reason is {finish_reason}. Response: {json.dumps(res_json)}"
                            raise ValueError(error_msg)

                    part = parts[0]
                    
                    if "text" in part:
                        response_text = part["text"]
                    elif "functionCall" in part:
                        fn = part["functionCall"]
                        name = fn.get("name", "unknown")
                        args = fn.get("args", {})
                        
                        # Structured conversion with fallback safety
                        if name in ["web_search", "deep_search", "thinking", "scout_file", "read_file"]:
                            # Safe extraction of first argument
                            val = ""
                            if isinstance(args, dict) and args:
                                val_list = list(args.values())
                                if val_list: val = str(val_list[0])
                            response_text = f"[TOOL: {name}({val})]"
                        elif name == "write_file":
                            response_text = f"[TOOL: {name}({args.get('filename','')}|{args.get('content', '')})]"
                        elif name == "generate_report":
                            response_text = f"[TOOL: {name}({args.get('title','')}|{args.get('content', '')})]"
                        elif name == "report_generation":
                            response_text = f"[TOOL: {name}({args.get('topic','')}|{args.get('context', '')})]"
                        elif name == "message_agent":
                            response_text = f"[TOOL: {name}({args.get('target_id','')}|{args.get('message', '')})]"
                        elif name in ["list_workspace"]:
                            response_text = f"[TOOL: {name}()]"
                        else:
                            # Generic fallback
                            arg_str = " | ".join([str(v) for v in args.values()]) if isinstance(args, dict) else str(args)
                            response_text = f"[TOOL: {name}({arg_str})]"
                    else:
                        response_text = "I have processed your request. How should we proceed?"

                except (IndexError, KeyError, ValueError) as e:
                    if not error_msg:
                        error_msg = f"Gemini API parsing error ({type(e).__name__}): {str(e)}"
                except Exception as e:
                    if not error_msg:
                        error_msg = f"Gemini API unexpected error ({type(e).__name__}): {str(e)}"
            else:
                error_msg = f"Gemini API Error: {response.text}"
        else:
            error_msg = f"Provider '{provider}' not implemented."

        if error_msg:
            print(f"[STATUS:{request.agent_id}] Error", flush=True)
            append_to_log("ERROR", error_msg)
            return {"error": error_msg}

        # ── POST-PROCESS: Clean 'Thoughts' ──────────────────────────
        # Some models use <thought> or 'Thinking...' despite instructions.
        # We strip these to keep the output clean for the user.
        for marker in ["<thought>", "Thinking...", "Internal Monologue:"]:
            if marker in response_text:
                parts = response_text.split(marker)
                # If there's a subsequent closing tag, strip everything between
                if marker == "<thought>" and "</thought>" in response_text:
                    response_text = response_text.split("</thought>")[-1].strip()
                else:
                    # Otherwise just take the last part after the marker
                    response_text = parts[-1].strip()
        if not response_text.strip():
            response_text = "I have processed the request. Please let me know how to proceed."

        # Look for [TOOL: name(input)] — re.DOTALL allows matching newlines inside tool input.
        # We use a greedy match (.*) inside the parentheses, but we anchor to the last ")]"
        # Since response_text might contain conversational text after the tool call, we extract the tool call first.
        tool_start = response_text.find("[TOOL:")
        tool_match = None
        if tool_start != -1:
            tool_end = response_text.rfind(")]")
            if tool_end > tool_start:
                search_area = response_text[tool_start:tool_end+2]
                tool_match = re.search(r"\[TOOL:\s*(\w+)\((.*)\)\]", search_area, re.DOTALL)
        
        # Look for a tool call. If the model outputs conversational text AND a tool call, 
        # we only extract the tool call and drop the conversational thought process.
        if tool_match:
            # Extract the thoughts before the tool call to display in the terminal
            pre_text = response_text[:tool_match.start()].strip()
            if pre_text:
                # Clean newlines and truncate to avoid huge terminal spam
                clean_thought = pre_text.replace("\n", " ")
                if len(clean_thought) > 120:
                    clean_thought = clean_thought[:117] + "..."
                print(f"[STATUS:{request.agent_id}] Thoughts: {clean_thought}", flush=True)

            # Reconstruct just the tool call string so we don't save the thoughts to history
            tool_name = tool_match.group(1)
            tool_input = tool_match.group(2)
            response_text = f"[TOOL: {tool_name}({tool_input})]"
        
        if tool_match:
            
            # 1. Provide intermediate feedback to UI
            friendly_action = tool_name.replace('_', ' ').title()
            # Clean and truncate tool input for one-line display
            clean_input = tool_input.replace('\n', ' ').strip()
            if len(clean_input) > 60: clean_input = clean_input[:57] + "..."
            print(f"[STATUS:{request.agent_id}] Action: {friendly_action} | Input: {clean_input}", flush=True)
            
            # 2. Execute Tool from global basket
            tool_result = perform_tool_call(request.agent_id, tool_name, tool_input, agent_dir, api_key=api_key)
            
            # Report completion to terminal
            res_summary = str(tool_result).replace('\n', ' ').strip()
            if len(res_summary) > 60: res_summary = res_summary[:57] + "..."
            print(f"[STATUS:{request.agent_id}] Finished: {friendly_action} | Result: {res_summary}", flush=True)
            
            # --- API PROTECTION: TRUNCATE HUGE TOOL RESULTS ---
            if isinstance(tool_result, str) and len(tool_result) > 10000:
                tool_result = (f"SYSTEM WARNING: Tool result too big ({len(tool_result)} chars). "
                               f"Truncated for API safety. Result head:\n{tool_result[:5000]}...\n\n"
                               f"STRICT INSTRUCTION: Do NOT try to read this much data again. Read it in smaller chunks.")

            # 3. Add to history
            history.append({"role": "assistant", "content": response_text})
            history.append({"role": "user", "content": f"SYSTEM TOOL RESULT: {tool_result}"})
            
            # Injection: Warn the agent if they are about to run out of steps
            
            # Injection: Warn the agent if they are about to run out of steps
            if iteration == max_turns - 2:
                history.append({"role": "user", "content": "SYSTEM WARNING: You are approaching your maximum step limit (1 turn remaining). Please summarize your progress and tell the user specifically what is left to do, then stop. The user can say 'Continue' to give you more steps."})
            
            iteration += 1
        else:
            final_response = response_text
            print(f"[STATUS:{request.agent_id}] Finalizing response...", flush=True)
            break
    # 5b. Fallback if max turns reached without a direct conversational response
    if not final_response and history:
        last_entry = history[-1]["content"]
        if "SYSTEM TOOL RESULT:" in last_entry:
            clean_result = last_entry.replace("SYSTEM TOOL RESULT: ", "").strip()
            final_response = (
                f"I've reached my internal thinking limit for this turn. Here is the last thing I found:\n\n"
                f"```text\n{clean_result}\n```\n\n"
                "I can continue if you'd like! Just say **'Continue'** or **'Keep going'** and I'll pick up right where I left off."
            )
        else:
            final_response = "I've reached my internal limit for this turn without a final answer. Would you like me to **continue**?"

    # 6. Save and Return
    print(f"[STATUS:{request.agent_id}] Ready", flush=True)
    
    # RUTHLESS Sanitization
    if final_response:
        final_response = sanitize_ruthlessly(final_response)

    history.append({"role": "assistant", "content": final_response})
    
    # ── SAVE INTERNAL HISTORY (FULL) ──
    with open(internal_history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    # ── FILTER UI HISTORY (Transparent Activity Update) ──
    # User sees Human User messages and Agent Activity + Final Responses.
    ui_history = []
    for entry in history:
        # EXTREME STRING SAFETY
        content = str(entry.get("content", "") or "")
        role = str(entry.get("role", "user"))
        
        # UI Activity Mapping: Convert internal markers to user-friendly status
        if role == "user":
            if content.startswith("SYSTEM TOOL RESULT:"):
                continue  # Keep chat clean of raw results
            elif content.startswith("[MESSAGE FROM"):
                continue  # Internal agent-to-agent talk stays hidden
            elif content.startswith("[AUTO_STEP"):
                continue  # Autonomous plan steps are internal — hide from UI
        elif role == "assistant":
            # Catch [TOOL:] whether it starts the message or is embedded mid-text.
            # An agent should never expose tool syntax in a final conversational response.
            tool_match_ui = re.search(r"\[TOOL:\s*(\w+)\(", content)
            if tool_match_ui:
                action_name = tool_match_ui.group(1).replace('_', ' ').title()
                content = f"*Agent Action: {action_name}...*"
        
        ui_history.append({
            "role": role,
            "content": sanitize_ruthlessly(content)
        })
    
    # Save the CLEAN history for the UI
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(ui_history, f, indent=2)

    # Check if we need to refresh the summary (based on internal history)
    if len(history) > 60:
        new_summary = refresh_conversation_summary(
            request.agent_id, 
            history[:-30],
            api_key, 
            provider, 
            current_summary
        )
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump({"summary": new_summary, "updated_at": time.time()}, f, indent=2)
        
    return {"response": final_response}

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
    provider = "gemini"
    api_key = os.getenv("GEMINI_API_KEY", "")

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
    provider = "gemini"
    api_key = os.getenv("GEMINI_API_KEY", "")
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
