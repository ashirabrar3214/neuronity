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
        if new_goal.startswith("SYSTEM TOOL RESULT:") or new_goal.startswith("[MESSAGE FROM"):
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
    RUTHLESS NON-DISCLOSURE: Redacts code blocks, large tool inputs, and raw data dumps.
    """
    if not text or not isinstance(text, str):
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

def process_generational_history(history, max_turns=50):
    """
    UNIVERSAL FIX: EXPONENTIAL CONTEXT DECAY (Temporal Attention)
    Implement Generational Context: Full Detail -> Concise Summary -> Topic-Only.
    """
    if not history: return []
    raw = history[-max_turns:] if len(history) > max_turns else history
    processed = []
    
    # Process in reverse to count generation distance from CURRENT turn (index 0)
    rev_raw = list(reversed(raw))
    for i, msg in enumerate(rev_raw):
        role = msg["role"]
        content = msg.get("content", "") or ""
        
        # Generation 0 (Last 5 messages): Full Energy (Attention Focus)
        if i < 5:
            processed.insert(0, {"role": role, "content": content})
        
        # Generation 1 (Messages 6-15): Mid-range Decay (Condensed Summary)
        elif i < 15:
            # For tool calls, keep the command name but shorten args
            if content.startswith("[TOOL:"):
                # Preserve tool name, shorten params
                parts = content.split("(", 1)
                cmd = parts[0]
                processed.insert(0, {"role": role, "content": f"[DECAYED_TOOL_CMD]: {cmd}(...)"})
            else:
                preview = content[:250] + "..." if len(content) > 250 else content
                processed.insert(0, {"role": role, "content": f"[GENERATIONAL_SUMMARY]: {preview}"})
            
        # Generation 2 (Messages 16-50): Long-term Decay (Metadata Only/Background Noise)
        else:
            if content.startswith("[TOOL:"):
                tool_name = content.split("(", 1)[0].replace("[TOOL:", "").strip()
                meta = f"[PREVIOUS_ACTION_METADATA: Executed {tool_name}]"
            elif content.startswith("SYSTEM TOOL RESULT:"):
                res_preview = content.replace("SYSTEM TOOL RESULT: ", "")[:50]
                meta = f"[PREVIOUS_RESULT_TYPE: {res_preview}...]"
            else:
                meta = f"[BACKGROUND_INFO_METADATA: {content[:100]}...]"
            processed.insert(0, {"role": role, "content": meta})
            
    return processed

    # 1. Redact all markdown blocks (The 'code it generates')
    text = re.sub(r"```[\s\S]*?```", "[REDACTED: Code/Raw Content Block]", text)
    
    # 2. Redact huge [TOOL: ...] signatures (The 'file content' in tool calls)
    def redact_huge_tool(match):
        tool_name = match.group(1)
        tool_input = match.group(2)
        if len(tool_input) > 250:
            return f"[TOOL: {tool_name}({tool_input[:247]}...)]"
        return match.group(0)
    
    text = re.sub(r"\[TOOL:\s*(\w+)\(([\s\S]*?)\)\]", redact_huge_tool, text)

    # 3. Detect raw data dumps (heuristic check for large blocks with CSV/delimited patterns)
    lines = text.splitlines()
    if len(lines) > 10:
        delim_count = 0
        for l in lines[:10]:
            clean_l = l.strip()
            if clean_l.startswith(('-', '*', '•')):
                continue
            if ',' in l or '\t' in l or '|' in l:
                delim_count += 1
        if delim_count > 5:
            return "[REDACTED: Large Data/File Content Block]"

    return text
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
        if provider == "gemini":
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
        elif provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
            data = {
                "model": "claude-3-5-sonnet-20240620",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": summary_prompt}]
            }
            resp = requests.post(url, headers=headers, json=data, timeout=30)
            if resp.status_code == 200:
                res_json = resp.json()
                content = res_json.get("content", [])
                if content and isinstance(content, list) and len(content) > 0:
                    response_text = content[0].get("text", "")
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

            # ── 2. ENFORCE CONNECTION GRAPH
            #       The agent can only message agents it is connected to on the canvas.
            sender_connections = sender_data.get("connections", [])
            if target_id not in sender_connections:
                return (f"Error: You are not connected to agent '{target_id}'. "
                        f"You can only send messages to agents you are wired to on the canvas. "
                        f"Your current connections are: {sender_connections}")
            
            # ── 3. Find target
            target_data = next((a for a in agents if a["id"] == target_id), None)
            if not target_data:
                return f"Error: Target agent {target_id} not found."
            target_provider = target_data.get("brain", "").lower()

            # ── 4. STIGMERGY: Senders no longer whisper history. 
            #       They leave findings in the Ledger instead.
            sender_context_snippet = "[Context Explosion Mitigation: Individual history snippets are disabled in favor of the Shared Workspace Ledger.]"
            
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

            # Signal the UI: who is being messaged so its canvas terminal can update
            print(f"[AGENT_MSG:{agent_id}->{target_id}] Contacting {target_data.get('name', target_id)}", flush=True)
            
            return toolkit.message_agent(
                target_id, message.strip(), agent_id, sender_name,
                target_api_key, target_provider,
                context_snippet=sender_context_snippet
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

    return "i dont have that ability yet"

import shutil
import toolkit
import response_formatter

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
    x: float = 0
    y: float = 0
    connections: List[str] = []

class ChatRequest(BaseModel):
    agent_id: str
    message: str
    api_key: str
    provider: str

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

    # 3. prompt.md
    prompt_path = os.path.join(agent_dir, "prompt.md")
    prompt_content = f"""# Agent Instructions: {agent_data['name']}
Description: {agent_data['description']}
Responsibility: {agent_data.get('responsibility', 'General purpose assistance')}
Tools: {agent_data.get('tools', 'Custom')}

## capabilities
{chr(10).join(['- ' + p for p in agent_data.get('permissions', [])]) if agent_data.get('permissions') else 'No specific permissions granted.'}

## STIGMERGY (SHARED LEDGER)
1. **The Ledger First**: Before acting, you MUST mentally check the Shared Workspace Ledger (in your system prompt) to see if the required data has already been posted by another agent.
2. **Post Findings**: When you find a definitive fact, correlation, or insight, you MUST use [TOOL: post_finding(Insight | Source URL)] immediately. This prevents other agents from duplicating your work.

## BDI PLANNING & STATE
1. **Plan Persistence**: You have a `plan.json` that tracks your objective and progress. 
2. **Atomic Updates**: You MUST use [TOOL: update_plan(Task Completed)] to cross off a task before you are allowed to send a final message to the user.
3. **Initialization**: If you have no plan, use [TOOL: update_plan(Objective | Step 1, Step 2, ...)] to set one.

## PROTOCOL FOR SEARCHING (RESEARCHER)
1. You MUST call [TOOL: web_search(query="...")] and then STOP.
2. Do NOT provide any information until you receive a SYSTEM TOOL RESULT.
3. You MUST extract the URLs from the search results.
4. When messaging other agents or the Ledger, you MUST provide the URL.

## MANDATORY: TASK MEMORY & CONTINUITY
1. **Review History & Plan:** Before every response, review the chat history and your current Plan. Identify what step of the process you are currently in.
2. **The "Wait" Rule:** If you are performing a tool action, you must output [TOOL: ...] and then STOP. 
3. **Intent Discrimination**: Only use a tool if the user provides a specific topic or goal.
4. **COLLABORATION FIRST**: If you lack a tool, message a connected agent.

## SOURCE REQUIREMENT
You are forbidden from using your internal knowledge for news or specialized research. Every fact must be followed by a `[Source: URL]` provided by the tool results.
## STRICT RULE: AGENT COMMUNICATION FAILURE
If you attempt to contact another agent using [TOOL: message_agent(...)] and it fails for ANY reason
(the agent is unreachable, not connected, returns an error, or times out), you MUST:
1. Report the failure clearly: state which agent you tried to contact and what the error was.
2. STOP. Do NOT attempt to complete the task yourself as a substitute.
3. Do NOT silently re-route the work to a different agent.
4. Do NOT pretend the task was completed.
5. Your only allowed response after a failed agent message is to explain the failure and ask the user how to proceed.
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
            "x": 100,
            "y": 150,
            "brain": "Anthropic",
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
            agents[i] = agent.model_dump()
            save_data(agents)
            generate_agent_structure(agent.model_dump())
            safe_log(f"*** [BACKEND] Updated agent: '{agent.name}' (ID: {agent.id})")
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

def get_gemini_tools_from_permissions(permissions, connections=None):
    """
    Generates the official Google Tool Schema based on agent permissions.
    This exposes the tools to the model natively, reducing hallucinations.
    """
    declarations = []
    
    if "web search" in permissions:
        declarations.append({
            "name": "web_search",
            "description": "Searches the internet for real-time information and quick facts.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {"type": "STRING", "description": "The search terms to use."}
                },
                "required": ["query"]
            }
        })
        declarations.append({
            "name": "deep_search",
            "description": "Performs in-depth research across multiple sources for complex topics.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {"type": "STRING", "description": "The complex research topic or question."}
                },
                "required": ["query"]
            }
        })

    if "thinking" in permissions:
        declarations.append({
            "name": "thinking",
            "description": "Dedicates computational resources to think deeply and logically about a complex topic.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "topic": {"type": "STRING", "description": "The problem or topic to analyze."}
                },
                "required": ["topic"]
            }
        })

    if "report generation" in permissions:
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
        declarations.append({
            "name": "report_generation",
            "description": "Executes final synthesis into a premium PDF research document.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "topic": {"type": "STRING", "description": "The final report topic."},
                    "context": {"type": "STRING", "description": "Full research data and sources to include."}
                },
                "required": ["topic", "context"]
            }
        })

    if "file access" in permissions:
        declarations.append({
            "name": "list_workspace", 
            "description": "Returns a map of all files and folders in your assigned working directory.", 
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

    if connections:
        declarations.append({
            "name": "message_agent",
            "description": "Sends a message and delegates a task to a connected specialist agent.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "target_id": {"type": "STRING", "description": "The specific ID of the specialist agent."},
                    "message": {"type": "STRING", "description": "The detailed request and context."}
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

    # ── 1. IDENTITY LAYER (Persona & Context) ────────────────────
    # UNIVERSAL FIX: THE BROKER PATTERN
    # Take the 'If report, delegate' logic out of prompt.md.
    # Agents follow 'Capability Matchmaking' instead of hardcoded rules.
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
        "## COLLABORATION PROTOCOL (Broker Pattern)\n"
        "1. **Analyze Capability Distance**: Before stating 'I cannot do this', check if your connected agents have the necessary Capability Embedding. "
        "Use your Agent Directory to find the highest semantic match for any missing tool.\n"
        "2. **The Delegation Rule**: If a task (like 'generate report' or 'deep research') is outside your PERMISSIONS but inside a teammate's responsibility, "
        "use [TOOL: message_agent(AGENT_ID|Detailed Request)] immediately. Do NOT try to simulate their capability.\n"
    )

    identity_layer = (
        f"## AGENT IDENTITY\n"
        f"You are {agent_data.get('name', 'an AI Agent')}. "
        f"Your role is: {agent_data.get('responsibility', 'General assistance')}.\n"
        f"CURRENT_DATE: {now}\n"
        f"ASSIGNED_WORKING_DIRECTORY: {work_dir}\n"
        f"Keep your tone professional, efficient, and direct.\n\n"
        f"{broker_logic}\n" # Semantic matchmaking for MasterBot
        f"{system_prompt}\n\n" # Original prompt.md content
        f"## UNIVERSAL COLLABORATION\n{reporting_rules}\n"
    )

    # ── 2. TOOL MANUAL (Capabilities) ───────────────────────────
    permissions = agent_data.get('permissions', [])
    tool_manual = [
        "### DEFAULT TOOLS",
        "### BDI PLANNING (INTERNAL STATE)\n"
        "- [TOOL: update_plan(Objective | Step 1, Step 2)]: Initialize your goal.\n"
        "- [TOOL: update_plan(Task Completed)]: Mark progress. MANDATORY before finalizing.\n"
        "### STIGMERGY (WORKSPACE LEDGER)\n"
        "- [TOOL: post_finding(Insight | Source)]: Share data with ALL agents globally.\n"
        "### CONVERSATIONAL BOUNDARIES & HONESTY\n"
        "- If the user is just chatting ('How are you?', 'Thanks', 'Cool'), DO NOT use any tools. Just respond naturally.\n"
        "- Tool use is for task-oriented requests only.\n"
        "- **INTENT DISCRIMINATION**: If the user is asking *about* your abilities (e.g., 'can you search the web?'), respond with a plain-text confirmation. ONLY use a tool if the user provides a specific topic or goal (e.g., 'search for X').\n"
        "- **STRICT RULE ON MISSING TOOLS**: If a requested capability is NOT listed in this manual, YOU CANNOT DO IT.\n"
        "- **STRICT RULE ON OUTCOMES**: Never claim a file action is 'done' unless you received a SYSTEM TOOL RESULT confirming it."
    ]
    
    if "web search" in permissions:
        tool_manual.append("### WEB SEARCH (Quick Facts)\n- Command: [TOOL: web_search(query)]\n- Description: Fetches specific facts or short summaries.")
        tool_manual.append("### DEEP SEARCH (Research)\n- Command: [TOOL: deep_search(query)]\n- Description: Performs in-depth research across multiple sources.")
    
    if "thinking" in permissions:
        tool_manual.append("### THINKING\n- Command: [TOOL: thinking(topic)]\n- Description: Analyze a complex topic logically.")
    
    if "report generation" in permissions:
        tool_manual.append("### REPORT TOOLS\n- [TOOL: generate_report(title|content)]: Create markdown draft.\n- [TOOL: report_generation(Topic|Context)]: Final PDF synthesis.")

    if "file access" in permissions:
        tool_manual.append("### FILE SYSTEM ACTIONS\n- [TOOL: list_workspace()]\n- [TOOL: scout_file(filename)]\n- [TOOL: read_file(filename)]\n- [TOOL: write_file(filename|content)]")

    connections = agent_data.get('connections', [])
    if connections:
        conn_lines = []
        for target_id in connections:
            target_data = next((a for a in agents if a["id"] == target_id), None)
            if target_data:
                conn_lines.append(f"  - **{target_data.get('name')}** (ID: `{target_id}`): {target_data.get('responsibility')}")
        
        tool_manual.append("### AGENT-TO-AGENT\n- Command: [TOOL: message_agent(AGENT_ID|Message)]\n- Connected Agents:\n" + "\n".join(conn_lines))

    tool_manual_layer = "## TOOL MANUAL\nIf you use a tool, respond ONLY with the [TOOL: ...] command and nothing else.\n\n" + "\n\n".join(tool_manual) + "\n"

    # ── 3. TRANSIENT TASK LAYER (Dynamic Context) ───────────────
    transient_task_layer = "\n## TRANSIENT TASK CONTEXT\n"
    
    # BDI PLAN LAYER
    plan_path = os.path.join(agent_dir, "plan.json")
    if os.path.exists(plan_path):
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                plan_data = json.load(f)
                transient_task_layer += (
                    f"### MY CURRENT PLAN (BDI)\n"
                    f"**OBJECTIVE**: {plan_data.get('objective', 'Unknown')}\n"
                    f"**TASKS TO DO**: {', '.join(plan_data.get('steps', []))}\n"
                    f"**COMPLETED**: {', '.join(plan_data.get('completed', []))}\n\n"
                )
        except: pass

    # STIGMERGY: SHARED WORKSPACE LEDGER (Topic-Gated Blackboard)
    ledger_path = os.path.join(AGENTS_CODE_DIR, "knowledge_base.json")
    if os.path.exists(ledger_path):
        try:
            with open(ledger_path, "r", encoding="utf-8") as f:
                ledger_data = json.load(f)
                if ledger_data:
                    # UNIVERSAL FIX: TOPIC-GATED FILTERING
                    # Filter findings that match the Global Objective or current user request
                    reference_text = f"{global_obj} {request.message}"
                    relevant_findings = []
                    for entry in ledger_data:
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
        except: pass

    # Global Objective
    workspace_context = get_workspace_context()
    global_obj = workspace_context.get("global_objective", "None")
    transient_task_layer += f"**GLOBAL OBJECTIVE**: {global_obj}\n\n"

    # Agent Directory
    transient_task_layer += "## PROJECT AGENT DIRECTORY\n"
    for a in agents:
        transient_task_layer += f"- {a.get('name')} (`{a['id']}`): {a.get('responsibility')}\n"

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

    # Protocols & Protection
    transient_task_layer += (
        "\n## CORE PROTOCOLS\n"
        "1. **RESEARCH HANDOFF**: Always format facts as: 'Fact [Source: URL]'.\n"
        "2. **REPORTER FOOTNOTES**: Always include sources in reports.\n"
        "3. **INTERNAL SCRIPT OUTPUT**: When writing Python code inside [TOOL: make_tool(...)], your script MUST use print() to output data to stdout.\n"
        "4. **COMMUNICATION FAILURE**: If message_agent fails, report it and STOP.\n"
        "5. **API PROTECTION**: NEVER read files > 5000 chars at once. Use chunks.\n"
        "6. **NON-DISCLOSURE**: Do NOT output raw code blocks or full file contents.\n"
        "7. **RESPONSE GUIDELINES**: Use rich markdown. Do NOT include 'Thoughts' or monologue.\n"
        "8. **COLLABORATION FIRST**: If you lack a tool or permission (e.g., web search, file access) needed for a task, you MUST check your 'Connected Agents' list. If a connected agent has that capability, ask them to do it via [TOOL: message_agent(...)]. Never refuse a task without checking if a teammate can help.\n"
    )

    # Current Task Details
    transient_task_layer += f"\n## CURRENT_MESSAGE\n{request.message}\n"

    system_prompt = identity_layer + tool_manual_layer + transient_task_layer


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
        
    provider = request.provider.lower()
    
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
            request.api_key, 
            provider, 
            old_summary
        )
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump({"summary": new_summary, "updated_at": time.time()}, f, indent=2)
        
        # Inject the new summary into the prompt if not already there
        if "## LONG-TERM CONVERSATION SUMMARY" not in system_prompt:
            system_prompt += f"\n\n## LONG-TERM CONVERSATION SUMMARY\n{new_summary}\n"

    history.append({"role": "user", "content": request.message})
    
    # 5. Iterative LLM Call with Tool Handling (Max 15 turns)
    max_turns = 15
    iteration = 0
    final_response = ""

    while iteration < max_turns:
        print(f"[STATUS:{request.agent_id}] Turn {iteration+1}/{max_turns}: Thinking...", flush=True)
        
        # ── SLIDING WINDOW CONTEXT (Exponential Decay Implementation) ──
        # Generations: Full Energy -> Condensed -> Metadata Only
        llm_context = process_generational_history(history)
        
        response_text = ""
        error_msg = ""
        
        if provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": request.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            messages = [{"role": h["role"], "content": h["content"]} for h in llm_context]
            # Determine temperature: collapsible probability distribution for researchers
            agent_name_lower = agent_data.get("name", "").lower()
            agent_resp_lower = agent_data.get("responsibility", "").lower()
            is_researcher = any(word in agent_name_lower or word in agent_resp_lower 
                                for word in ["research", "scout", "detective", "search", "analyst"])
            temp = 0.1 if is_researcher else 0.7

            data = {
                "model": "claude-3-5-sonnet-20240620",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": messages,
                "temperature": temp
            }
            response = requests.post(url, headers=headers, json=data, timeout=120)
            if response.status_code == 200:
                res_json = response.json()
                content_list = res_json.get("content", [])
                if content_list and isinstance(content_list, list) and len(content_list) > 0:
                    response_text = content_list[0].get("text", "")
                else:
                    error_msg = f"Anthropic API parsing error: Invalid content structure. Response: {json.dumps(res_json)}"
            else:
                error_msg = f"Anthropic API Error: {response.text}"

        elif provider == "gemini":
            model = "gemini-2.0-flash" 
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={request.api_key}"
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
            gemini_tools = get_gemini_tools_from_permissions(permissions, connections)
            
            # Determine temperature: collapsible probability distribution for researchers
            agent_name_lower = agent_data.get("name", "").lower()
            agent_resp_lower = agent_data.get("responsibility", "").lower()
            is_researcher = any(word in agent_name_lower or word in agent_resp_lower 
                                for word in ["research", "scout", "detective", "search", "analyst"])
            temp = 0.1 if is_researcher else 0.7

            data = {
                "contents": gemini_history,
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "generationConfig": {"temperature": temp}
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
            tool_result = perform_tool_call(request.agent_id, tool_name, tool_input, agent_dir, api_key=request.api_key)
            
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

    # ── FILTER UI HISTORY (Clean Only) ──
    # User only wants to see Human User messages and Final Agent responses.
    # We strip out [TOOL:...], [MESSAGE FROM ANOTHER AGENT], and SYSTEM TOOL RESULT
    ui_history = []
    for entry in history:
        content = entry["content"]
        role = entry["role"]
        
        # Skip internal markers
        if role == "user":
            if content.startswith("SYSTEM TOOL RESULT:") or content.startswith("[MESSAGE FROM"):
                append_to_log("INTERNAL_IN", content)
                continue
        if role == "assistant":
            if content.startswith("[TOOL:"):
                append_to_log("INTERNAL_OUT", content)
                continue
        
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
            request.api_key, 
            provider, 
            current_summary
        )
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump({"summary": new_summary, "updated_at": time.time()}, f, indent=2)
        
    return {"response": final_response}

if __name__ == "__main__":
    # Run on localhost:8000 — loop=asyncio lets multiple agents communicate concurrently
    uvicorn.run(app, host="127.0.0.1", port=8000, loop="asyncio")
