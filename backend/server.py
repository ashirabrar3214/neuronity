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

<<<<<<< HEAD
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

=======
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
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
        content = h["content"][:500] + "..." if len(h["content"]) > 500 else h["content"]
        formatted_history += f"[{role}]: {content}\n"

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
                response_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
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
                response_text = resp.json()["content"][0]["text"]
    except Exception as e:
        print(f"!!! [SUMMARY ERROR] Failed to update summary: {e}")
        return current_summary

    return response_text.strip() if response_text else current_summary
    
<<<<<<< HEAD


# Tool Implementations
def perform_tool_call(agent_id, tool_name, tool_input, agent_dir, api_key=""):
    # --- Resolve workingDir for file-saving tools ---
    agents = load_data()
    sender_data = next((a for a in agents if a["id"] == agent_id), None)
    working_dir = sender_data.get("workingDir", "") if sender_data else ""

    if tool_name == "web_search":
        return toolkit.web_search(tool_input, agent_id, api_key=api_key)
    
    elif tool_name == "deep_search":
        return toolkit.deep_search(tool_input, agent_id, api_key=api_key)
=======
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
            if ',' in l or '\t' in l or '|' in l:
                delim_count += 1
        if delim_count > 5:
            return "[REDACTED: Large Data/File Content Block]"

    return text

# Tool Implementations
def perform_tool_call(agent_id, tool_name, tool_input, agent_dir, api_key=""):
    if tool_name == "web_search":
        # Step 1: Fetch raw results
        all_results = toolkit.web_search(tool_input, agent_id)
        # Step 2: Gemini picks the most relevant ones (3–8)
        filtered_results = toolkit.filter_sources(tool_input, all_results, api_key)
        # Step 3: Synthesize a structured brief from the filtered set
        return toolkit.synthesize_with_gemini(tool_input, filtered_results, api_key)
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
    
    elif tool_name == "thinking":
        return toolkit.thinking(agent_id, tool_input)

    elif tool_name == "generate_report":
<<<<<<< HEAD
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
=======
        return toolkit.generate_report(agent_id, tool_input, agent_dir)
    
    elif tool_name == "message_agent":
        if "|" in tool_input:
            target_id, message = tool_input.split("|", 1)
            target_id = target_id.strip()
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
            
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

            # ── 4. Load sender's recent history as context for the target
            sender_history_path = os.path.join(AGENTS_CODE_DIR, agent_id, "history.json")
            sender_context_snippet = ""
            if os.path.exists(sender_history_path):
                try:
                    with open(sender_history_path, "r", encoding="utf-8") as f:
                        sender_history = json.load(f)
<<<<<<< HEAD
                    # Take the last 15 exchanges (up to 15 messages) as context
                    recent = sender_history[-15:] if len(sender_history) > 15 else sender_history
                    if recent:
                        lines = []
                        msg_count = len(recent)
                        for i, h in enumerate(recent):
                            role_label = sender_name if h["role"] == "assistant" else "User"
                            # Weighting: 1 is oldest (15th), N is newest (1st)
                            weight = i + 1
                            priority = "LOW" if weight <= 5 else "MEDIUM" if weight <= 10 else "HIGH"
                            # Preserve more context (especially for search results with URLs)
                            content_limit = 2000 
                            lines.append(f"  [Msg {weight}/{msg_count} - Priority: {priority}] [{role_label}]: {h['content'][:content_limit]}")
=======
                    # Take the last 6 exchanges (up to 6 messages) as context
                    recent = sender_history[-6:] if len(sender_history) > 6 else sender_history
                    if recent:
                        lines = []
                        for h in recent:
                            role_label = sender_name if h["role"] == "assistant" else "User"
                            lines.append(f"  [{role_label}]: {h['content'][:400]}")
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
                        sender_context_snippet = "\n".join(lines)
                except Exception:
                    pass
            
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
<<<<<<< HEAD
        # working_dir already resolved above
        try:
=======
        # Get the agent workingDir
        try:
            agents = load_data()
            sender_data = next((a for a in agents if a["id"] == agent_id), None)
            working_dir = sender_data.get("workingDir", "") if sender_data else ""
            
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
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

<<<<<<< HEAD
## capabilities
{chr(10).join(['- ' + p for p in agent_data.get('permissions', [])]) if agent_data.get('permissions') else 'No specific permissions granted.'}

## PROTOCOL FOR SEARCHING (RESEARCHER)
1. You MUST call [TOOL: web_search(query="...")] and then STOP.
2. Do NOT provide any information until you receive a SYSTEM TOOL RESULT.
3. You MUST extract the URLs from the search results.
4. When messaging the Reporter, you MUST format the info like this: "Fact [Source: URL]". If you don't provide the URL, the Reporter cannot do its job.

## PROTOCOL FOR CITATIONS (REPORTER)
1. You will receive information from the Researcher agent that includes sources in the format [Source: URL].
2. You are REQUIRED to include these sources as footnotes or in-text citations in every report you generate.
3. If the Researcher does not provide sources, message them back immediately using [TOOL: message_agent(...)] and demand the URLs. 
4. Never say "I don't have the ability"; instead, explain the technical requirement (missing data) and demand what you need.

## MANDATORY: TASK MEMORY & CONTINUITY
1. **Review History:** Before every response, review the entire chat history. Identify the current "Global Goal" and what step of the process you are currently in.
2. **The "Wait" Rule:** When you output a `[TOOL: ...]` call, you must STOP. Do not generate any text or commentary after the tool call. Wait for the `SYSTEM TOOL RESULT`.
3. **Consistency Rule:** Never state that you lack an ability listed in your 'Capabilities' section. If a task fails, explain the specific technical error or missing information, not a lack of ability.

## SOURCE REQUIREMENT
You are forbidden from using your internal knowledge for news or specialized research. Every fact must be followed by a `[Source: URL]` provided by the tool results.

=======
## Capabilities
{chr(10).join(['- ' + p for p in agent_data.get('permissions', [])]) if agent_data.get('permissions') else 'No specific permissions granted.'}

>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
## STRICT RULE: AGENT COMMUNICATION FAILURE
If you attempt to contact another agent using [TOOL: message_agent(...)] and it fails for ANY reason
(the agent is unreachable, not connected, returns an error, or times out), you MUST:
1. Report the failure clearly: state which agent you tried to contact and what the error was.
2. STOP. Do NOT attempt to complete the task yourself as a substitute.
3. Do NOT silently re-route the work to a different agent.
4. Do NOT pretend the task was completed.
Your only allowed response after a failed agent message is to explain the failure and ask the user how to proceed.
"""
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt_content)

    # 4. Short term memory (History) - Initialize if not exists
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
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump([], f)
        print(f"--- [BACKEND] Cleared history for agent: {agent_id}")
        return {"status": "success", "message": "History cleared"}
    except Exception as e:
        print(f"!!! [BACKEND ERROR] Could not clear history for {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

<<<<<<< HEAD
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

    return [{"function_declarations": declarations}] if declarations else []

=======
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
@app.post("/chat")
def chat_with_agent(request: ChatRequest):
    # 1. Load Agent Folder Paths
    agent_dir = os.path.join(AGENTS_CODE_DIR, request.agent_id)
    if not os.path.exists(agent_dir):
        os.makedirs(agent_dir, exist_ok=True)
        
    prompt_path = os.path.join(agent_dir, "prompt.md")
    history_path = os.path.join(agent_dir, "history.json")
    
    # Define system prompt and permissions
    agents = load_data()
    agent_data = next((a for a in agents if a["id"] == request.agent_id), None)
    if not agent_data:
         raise HTTPException(status_code=404, detail="Agent not found")

    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    else:
        generate_agent_structure(agent_data)
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()

    # Inject current date, working dir, and strict output formatting
    work_dir = agent_data.get("workingDir", "None assigned")
    system_prompt = f"CURRENT_DATE: {now}\nASSIGNED_WORKING_DIRECTORY: {work_dir}\n\n" + system_prompt

    # ── USER IDENTITY ───────────────────────────────────────────
    system_prompt += (
        f"## USER IDENTITY\n"
        f"You are working for **The User**, the owner and operator of this workspace. "
<<<<<<< HEAD
        f"Keep your tone professional, efficient, and direct.\n"
        f"CRITICAL: All files you create or modify MUST be saved in the `ASSIGNED_WORKING_DIRECTORY`: {work_dir}. Never save files in your internal code directory.\n"
        f"ABSOLUTE RULE: MANDATORY PROACTIVITY & TOOL-FIRST RESPONSE\n"
        f"1. **EXPLICIT REPORT TRIGGER**: You MUST ONLY initiate the automated Research-to-PDF pipeline if the user's **CURRENT MESSAGE** explicitly asks for a 'report'. If they mention 'document', 'PDF', or 'file' without 'report', just answer them conversationally or ask for details. NEVER assume a report is wanted from vague hints.\n"
        f"2. **CURRENT CONVERSATION VS OBJECTIVE**: The `global_objective` is your long-term background goal. However, you MUST prioritize the tone and context of the **IMMEDIATE CHAT**. If the user is just saying 'hello', 'how are you', or expressing confusion, respond naturally as a person. DO NOT use tools or search the web for social greetings.\n"
        f"3. **STOP ON CONFUSION/ANNOYANCE**: If the user says 'what?', 'stop', 'why?', 'did I tell you to?', or seems frustrated, IMMEIDATELY stop all tool use. Do NOT try to solve their confusion with more tools. Just explain yourself clearly in plain text.\n"
        f"4. **SILENT EXECUTION**: ONLY for explicit 'report' requests, you stay silent during the tool pipeline. For all other questions, be conversational.\n"
        f"5. **SOCIAL & GENERAL INQUIRIES**: If the user asks general questions like 'How are you?', respond professionally and do NOT use tools.\n"
        f"6. **TOOL RESTRAINT**: Do NOT use `list_workspace`, `scout_file`, `web_search` or any other tools for social chat, greetings, or simple questions. Only use tools when a technical task is clearly required.\n"
        f"7. **NO HALLUCINATION OF CAPABILITIES**: If the user asks you to do something for which you do NOT have a corresponding tool in the 'TOOL MANUAL' below (e.g., 'delete a file', 'send a tweet'), you MUST NOT claim you can do it. You MUST NOT lie or pretend to have performed an action. Instead, say: 'Unfortunately, I don't have the ability to do that yet.'\n"
        f"8. **VERIFY TOOL EXECUTION**: Never state that an action is 'done' or 'complete' unless you have successfully received a result from a corresponding [TOOL: ...] call in the previous turn.\n"
        f"9. **THE WAIT RULE**: When you output a `[TOOL: ...]` call, you MUST stop generating text immediately. Do NOT hallucinate the result. Wait for the `SYSTEM TOOL RESULT` in the next turn.\n"
        f"10. **RESEARCH HANDOFF PROTOCOL**: When sending data to another agent (e.g., Reporter), you MUST format facts as: 'Fact [Source: URL]'. Do NOT summarize URLs away.\n"
        f"11. **REPORTING COLLABORATION**: As a Reporter, you are REQUIRED to include sources as footnotes. If the Researcher sends you data without URLs, you MUST message them back and demand the URLs before generating the report. Do NOT refuse the task; demand the data.\n"
        f"12. **CONSISTENCY & ABILITY**: Never state that you lack an ability listed in your 'TOOL MANUAL'. If a task fails or data is missing, explain the technical requirement (e.g., 'Need source URLs for citations') rather than a lack of capability.\n\n"
=======
        f"Keep your tone professional, efficient, and direct. Prioritize the User's explicit instructions above all else.\n\n"
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
    )

    # ── LONG-TERM MEMORY SUMMARY ────────────────────────────────
    summary_path = os.path.join(agent_dir, "summary.json")
    current_summary = ""
    if os.path.exists(summary_path):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                summary_data = json.load(f)
                current_summary = summary_data.get("summary", "")
                if current_summary:
                    system_prompt += (
                        f"## LONG-TERM CONVERSATION SUMMARY\n"
                        f"Below is a condensed summary of your previous interactions. Use this to maintain continuity.\n"
                        f"{current_summary}\n\n"
                    )
        except:
            pass

    # ── LIVE FILE DIRECTORY ─────────────────────────────────────
    # Inject the most recent directory map if it exists
    dir_map_path = os.path.join(agent_dir, "dir_map.json")
    if os.path.exists(dir_map_path):
        try:
            with open(dir_map_path, "r", encoding="utf-8") as f:
                dir_map = json.load(f)
            
            # Simplified view for the prompt
            map_lines = ["## LIVE FILE DIRECTORY (Real-time snapshot)"]
            for rel, contents in dir_map.items():
                if rel == ".":
                    map_lines.append("Root Directory:")
                else:
                    map_lines.append(f"Directory: {rel}")
                
                for fname in contents.get("files", []):
                    map_lines.append(f"  [FILE] {fname}")
            
            system_prompt += "\n".join(map_lines) + "\n\n"
        except:
            pass
    
    # Update global context if this is a direct user message (not internal agent messaging)
    is_agent_message = request.message.strip().startswith("[MESSAGE FROM ANOTHER AGENT]")
    if not is_agent_message:
        update_workspace_context(request.message)

    # ── SHARED WORKSPACE CONTEXT ─────────────────────────────────
    # Inject the global objective so all agents stay synced.
    workspace_context = get_workspace_context()
    global_obj = workspace_context.get("global_objective", "None")
    
    system_prompt += (
        f"\n\n## GLOBAL WORKSPACE CONTEXT\n"
        f"The overarching objective for the current project is: **{global_obj}**\n"
        f"Internalize this goal. Even if you are asked to do a sub-task, ensure it aligns with this context.\n"
    )

    # ── PROJECT AGENT DIRECTORY ─────────────────────────────────
    # We construct a full directory of all agents in the project
    # as requested by the user, and inject it into the prompt.
    directory_lines = ["## PROJECT AGENT DIRECTORY"]
    directory_lines.append("Below are all agents currently in this project. Use this to identify who to delegate tasks to.")
    for a in agents:
        a_perms = a.get('permissions', [])
        a_perms_str = ', '.join(a_perms) if a_perms else 'none'
        directory_lines.append(f"### {a.get('name')} (ID: `{a['id']}`)")
        directory_lines.append(f"- **Role**: {a.get('responsibility', 'General assistance')}")
        directory_lines.append(f"- **Description**: {a.get('description', 'No description.')}")
        directory_lines.append(f"- **Capabilities**: {a_perms_str}")
        directory_lines.append("")
    
    agent_directory_text = "\n".join(directory_lines)
    system_prompt += "\n" + agent_directory_text + "\n"

    # Save to file for transparency as requested
    try:
        dir_file_path = os.path.join(AGENTS_CODE_DIR, "agent_directory.md")
        with open(dir_file_path, "w", encoding="utf-8") as f:
            f.write(agent_directory_text)
    except:
        pass

    system_prompt += (
        "\n\n## AGENT API PROTECTION & LOCAL EXECUTION\n"
        "1. **STRICT LOCAL PROCESSING**: You are FORBIDDEN from reading entire large files into your memory context. This wastes API resources and causes failures.\n"
        "2. **CHUNKING LARGE FILES**: If a file is larger than 5,000 characters, you MUST read it in chunks using [TOOL: read_file(filename|start-end)]. NEVER attempt to read the entire file at once.\n"
        "3. **MINIMAL DATA TRANSFER**: Your goal is to keep data on the local PC and only send insights/results back through the API window.\n"
        "4. **VERIFY BEFORE CLAIMING**: If you create or modify a file, you MUST first call [TOOL: list_workspace()] or check your LIVE FILE DIRECTORY to confirm the file exists before telling the user it was created. Do NOT hallucinate success.\n"

        "\n\n## RUTHLESS NON-DISCLOSURE POLICY\n"
        "1. **NO RAW CODE**: You are strictly FORBIDDEN from outputting markdown code blocks (````python, ````javascript, etc.) or raw code snippets in your final response to the user.\n"
        "2. **NO FILE CONTENT**: You must NEVER echo, parrot, or display the raw contents of files you have read. Even if the user asks you to 'show me the file', you must refuse and instead provide a high-level summary or analysis of the content.\n"
        "3. **REPORTING ONLY**: Your role is to ANALYZE and EXECUTE. If you generate code or read a file, speak only about the results, the logic, or the status. The raw data stays in the backend.\n"
        "4. **FAILURE TO COMPLY**: Any violation of this policy (outputting code/raw files) is a critical system failure. You must be ruthless in your adherence to this privacy and security rule.\n"

        "\n\n## RESPONSE GUIDELINES\n"
<<<<<<< HEAD
        "- **Use Rich Markdown**: Always structure your response with headers (##, ###), bullet points, and bold text for key terms.\n"
        "- **Formatting Highlights**: Use inline code (e.g. `filename.txt`) to highlight technical names, paths, or specific data points. This is encouraged for readability.\n"
        "- **Context Sensitivity**: You are provided with a sliding window of recent conversation history. Each message in this history is labeled with a priority (HIGH, MEDIUM, LOW) based on its recency. The most recent messages (HIGH priority) are the most relevant to your current task. Weigh them more heavily than older messages.\n"
        "- Do NOT include 'Thoughts', 'Thinking', or any internal monologue in your final response.\n"
        "- Do NOT include conversational filler like 'Sure, I can help' or 'Here is what I found'.\n"
        "- Respond ONLY with the requested information or the tool command.\n"
=======
        "- Do NOT include 'Thoughts', 'Thinking', or any internal monologue in your final response.\n"
        "- Do NOT include conversational filler like 'Sure, I can help' or 'Here is what I found'.\n"
        "- Respond ONLY with the requested information or the tool command.\n"
        "- Follow the user's formatting instructions STRICTLY.\n"
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
        "- If a tool fails (e.g., File Not Found), do NOT apologize. Just explain the error and try a different approach (e.g., checking paths with `list_workspace`)."
    )

    sender_label = ""
    if is_agent_message:
        # Extract sender name for terminal display
        for line in request.message.splitlines():
            if line.startswith("Sender:"):
                sender_label = line.replace("Sender:", "").split("(")[0].strip()
                break
        print(f"[STATUS:{request.agent_id}] Message received from {sender_label}", flush=True)

    # 3. Inject Tool Manual (Capabilities) based on permissions
    permissions = agent_data.get('permissions', [])
<<<<<<< HEAD
    tool_manual = [
        "### DEFAULT TOOLS",
        "### CONVERSATIONAL BOUNDARIES & HONESTY\n"
        "- If the user is just chatting ('How are you?', 'Thanks', 'Cool'), DO NOT use any tools. Just respond naturally.\n"
        "- Tool use is for task-oriented requests only.\n"
        "- **STRICT RULE ON MISSING TOOLS**: If a requested capability is NOT listed in this manual, YOU CANNOT DO IT. Do not hallucinate or pretend. You must respond: 'Unfortunately, I don't have the ability to do that yet.'\n"
        "- **STRICT RULE ON OUTCOMES**: Never claim a file of yours was deleted, modified, or moved unless you used a tool to do so."
    ]
    
    if "web search" in permissions:
        tool_manual.append("### WEB SEARCH (Quick Facts - PREFERRED)\n- Command: [TOOL: web_search(query)]\n- Description: Fetches specific facts, numbers, or short summaries. Use this for 90% of requests to stay fast and concise.")
        tool_manual.append("### DEEP SEARCH (Comprehensive Research)\n- Command: [TOOL: deep_search(query)]\n- Description: Performs in-depth research across multiple sources. Use this ONLY for complex studies or when explicitly requested.")
=======
    tool_manual = ["### DEFAULT TOOLS"]
    
    if "web search" in permissions:
        tool_manual.append("### WEB SEARCH\n- Command: [TOOL: web_search(query)]\n- Description: Researches the given query on the web. Only use this if you need external data.")
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
    
    if "thinking" in permissions:
        tool_manual.append("### THINKING\n- Command: [TOOL: thinking(topic)]\n- Description: Dedicates resources to think deeply about a complex topic.")
    
    if "report generation" in permissions:
<<<<<<< HEAD
        tool_manual.append("### REPORT GENERATION (Markdown Draft)\n- Command: [TOOL: generate_report(title|content)]\n- Description: Generates a .md file in the working directory. Store all gathered research here BEFORE making the final PDF.")
        tool_manual.append("### COMPREHENSIVE REPORT GENERATION (PDF - FINAL STEP)\n- Command: [TOOL: report_generation(Topic | Context)]\n- Description: Executes the final synthesis into a PDF. ONLY use this if 'report' was in the user's current message.")
        tool_manual.append("#### AUTOMATED REPORT WORKFLOW (STRICT)\n1. User says 'report' -> 2. SILENT PIPELINE: `deep_search` -> `generate_report` -> `report_generation`.\n3. NO 'REPORT' WORD? -> NO PDF WORKFLOW.")
=======
        tool_manual.append("### REPORT GENERATION\n- Command: [TOOL: generate_report(title|content)]\n- Description: Generates a .md report in your directory. Must use '|' to separate title and content.")
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607

    if "file access" in permissions:
        tool_manual.append(("### FILE SYSTEM ACTIONS (Strictly bound to your assigned working directory)\n"
                            "- **List Workspace:** [TOOL: list_workspace()]\n"
                            "  - Description: Returns a complete folder/file map of your assigned working directory instantly. Use this to orient yourself.\n"
                            "- **Scout File:** [TOOL: scout_file(filename)]\n"
                            "  - Description: Checks metadata (size, type, lines) of a file BEFORE you try to read it. Use this first! Can also be used on a directory path to list its contents.\n"
                            "- **Read File:** [TOOL: read_file(filename)] or [TOOL: read_file(filename|startline-endline)]\n"
                            "  - Description: Reads a file. If checking via `scout_file` showed the file is > 1000 lines, you MUST read in chunks using the line-range argument (e.g. `log.txt|1-200`).\n"
                            "- **Write File:** [TOOL: write_file(filename | content)]\n"
                            "  - Description: Writes or overwrites a file with the exact provided content."))


    # Inject Connections (Agent-to-Agent)
    connections = agent_data.get('connections', [])
    if connections:
        conn_lines = []
        for target_id in connections:
            target_data = next((a for a in agents if a["id"] == target_id), None)
            if target_data:
                target_name = target_data.get('name', target_id)
                target_desc = target_data.get('description', 'No description.')
                target_resp = target_data.get('responsibility', '')
                target_perms = target_data.get('permissions', [])
                perms_str = ', '.join(target_perms) if target_perms else 'none'
                conn_lines.append(
                    f"  - **{target_name}** (ID: `{target_id}`)\n"
                    f"    Description: {target_desc}\n"
                    f"    Responsibility: {target_resp or 'General assistance'}\n"
                    f"    Tools available to them: {perms_str}"
                )
        
        if conn_lines:
            conn_manual = (
                "### AGENT-TO-AGENT MESSAGING\n"
                "- Command: [TOOL: message_agent(AGENT_ID|Your message)]\n"
                "- Description: Sends a message with full context to a connected agent and waits for their response. "
                "Use this to delegate tasks, share research, or ask for analysis.\n"
                "- RULES:\n"
                "  1. Replace 'AGENT_ID' with a specific ID from the 'Your Connected Agents' list below.\n"
                "  2. Include ALL relevant context in your message — the target agent does not share your memory.\n"
<<<<<<< HEAD
                "  3. **DATA INTEGRITY**: When passing research findings or search results to another agent, you MUST NOT summarize them. Paste the FULL citations, URLs, and data points so the target agent can generate accurate reports with sources.\n"
                "  4. You MUST output EXACTLY the [TOOL: message_agent(ID|Message)] command string and NOTHING else.\n"
                "  5. CRITICAL: Do NOT use named arguments (e.g., AGENT_ID=\"...\") inside the parentheses. Use ONLY the data separated by the pipe (|) character.\n"
                "  6. You will receive their full response as a tool result before continuing.\n"
=======
                "  3. You MUST output EXACTLY the [TOOL: message_agent(...)] command string and NOTHING else.\n"
                "  4. You will receive their full response as a tool result before continuing.\n"
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
                "- Your Connected Agents:\n" + "\n".join(conn_lines)
            )
            tool_manual.append(conn_manual)

    if tool_manual:
        system_prompt += "\n\n## YOUR CAPABILITY MANUAL\nYou have access to specific tools. If you need to use one, respond ONLY with the tool command and NOTHING ELSE. Wait for the result before proceeding.\n\n"
        system_prompt += "\n\n".join(tool_manual)
        system_prompt += "\n\nCRITICAL: If you use a tool, do not provide any further commentary or conversational text in the same message. Just output the exact [TOOL: ...] command and stop typing.\nNEVER use markdown code blocks like ````python ... ```` or ````javascript ```` instead of calling a [TOOL: ] command. You lack a pure terminal to execute pure code; you must wrap any code inside the corresponding tool command string."

    # When receiving a message from another agent: respond with full information, tools allowed.
    if is_agent_message:
        system_prompt += (
            f"\n\n## AGENT-TO-AGENT COMMUNICATION MODE\n"
            f"You have received a message from **{sender_label}**, a connected AI agent.\n"
            f"- Read their message and any context they provided carefully.\n"
            f"- Respond directly and concisely to their request.\n"
            f"- You MAY use your tools (web_search, generate_report, etc.) if the task requires it.\n"
            f"- Do NOT use the message_agent tool to trigger another agent loop unless explicitly asked to.\n"
            f"- Your response will be sent back to {sender_label} as a tool result. Be informative and actionable."
        )

    # ALWAYS enforce the non-substitution rule — appended last so it cannot be overridden
    system_prompt += (
        "\n\n## ABSOLUTE RULE: DELEGATED TASK PASS-THROUGH\n"
        "If you use [TOOL: message_agent(...)] to delegate a task to another agent:\n"
        "1. Once you receive their response, you MUST pass it back to the user/sender word-for-word.\n"
        "2. Do NOT summarize their work or add your own commentary unless you found an explicit error.\n"
        "3. If the other agent provided the result you asked for, your only job is to relay it immediately.\n"
        "4. This ensures the user gets the exact formatting and data they requested from the specialist agent."

        "\n\n## ABSOLUTE RULE: FAILED AGENT COMMUNICATION\n"
        "If you use [TOOL: message_agent(...)] and it returns an error or failure:\n"
        "1. Check the error message carefully. If you used a placeholder like 'TARGET_ID' or a name instead of an ID, you MUST retry with the correct ID from your 'Connected Agents' list.\n"
        "2. If the connection is genuinely impossible (missing ID), report the failure clearly and ask the user for the correct agent ID to use.\n"
        "3. Do NOT attempt to do the work yourself or silently re-route to another agent.\n"
        "4. Once the failure is reported, wait for the user to provide the correct agent ID or further instructions."

        "\n\n## AGENT TASK RESILIENCE & CONTINUATION\n"
        "1. **Task Checkpointing**: For complex tasks (e.g., reading large files, multi-step analysis), break your work into clear checkpoints.\n"
        "2. **Step Limits**: If you receive a 'SYSTEM WARNING' about step limits, you MUST wrap up your current thought, provide a clear status update of what is done vs what is left, and invite the user to say 'Continue'.\n"
        "3. **Large Files**: If `read_file` errors with 'File is too large', do NOT give up. Use line ranges (e.g., `archive/dataset.csv|1-500`) to process the file in chunks across multiple turns. Always verify your line count with `scout_file` first."
    )

    # 4. Load History
    try:
        if os.path.exists(history_path):
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        else:
            history = []
    except:
        history = []
        
<<<<<<< HEAD
    # --- REFUSAL LOOP BREAKER ---
    # If the last thing the agent said was a refusal/hallucination about its abilities,
    # we trim the history to 'forget' that error and allow a fresh attempt with the new instructions.
    if len(history) >= 2:
        last_assistant_msg = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
        if "Unfortunately, I don't have the ability" in last_assistant_msg:
             # Trim until the last user message before the refusal
             refined_history = []
             found_refusal = False
             for msg in reversed(history):
                 if "Unfortunately, I don't have the ability" in msg["content"] and msg["role"] == "assistant":
                     found_refusal = True
                     continue
                 if found_refusal:
                     # Keep everything BEFORE the refusal chain
                     refined_history.insert(0, msg)
             if found_refusal:
                 history = refined_history
                 print(f"[STATUS:{request.agent_id}] Refusal loop detected. Trimming history for fresh start.", flush=True)

=======
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
    history.append({"role": "user", "content": request.message})
    
    # 5. Iterative LLM Call with Tool Handling (Max 15 turns)
    provider = request.provider.lower()
    max_turns = 15
    iteration = 0
    final_response = ""

    while iteration < max_turns:
        print(f"[STATUS:{request.agent_id}] Training", flush=True) # "Training" acts as "thinking/processing" in training mode
        
        # ── SLIDING WINDOW CONTEXT ─────────────────────────────────
<<<<<<< HEAD
        # Only send the last 15 messages to the LLM to avoid context overflow,
        # while keeping the full history for the user's UI.
        raw_context = history[-15:] if len(history) > 15 else history
        
        llm_context = []
        for h in raw_context:
            llm_context.append({"role": h["role"], "content": h["content"]})
=======
        # Only send the last 30 messages to the LLM to avoid context overflow,
        # while keeping the full history for the user's UI.
        llm_context = history[-30:] if len(history) > 30 else history
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
        
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
            data = {
                "model": "claude-3-5-sonnet-20240620",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": messages
            }
<<<<<<< HEAD
            response = requests.post(url, headers=headers, json=data, timeout=120)
=======
            response = requests.post(url, headers=headers, json=data)
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
            if response.status_code == 200:
                response_text = response.json()["content"][0]["text"]
            else:
                error_msg = f"Anthropic API Error: {response.text}"

        elif provider == "gemini":
            model = "gemini-2.0-flash" 
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={request.api_key}"
            headers = {"Content-Type": "application/json"}
<<<<<<< HEAD
            
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
            
=======
            gemini_history = [{"role": "user" if h["role"] == "user" else "model", "parts": [{"text": h["content"]}]} for h in llm_context]
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
            data = {
                "contents": gemini_history,
                "systemInstruction": {"parts": [{"text": system_prompt}]}
            }
<<<<<<< HEAD
            if gemini_tools:
                data["tools"] = gemini_tools

            response = requests.post(url, headers=headers, json=data, timeout=120)
            if response.status_code == 200:
                try:
                    res_json = response.json()
                    part = res_json["candidates"][0]["content"]["parts"][0]
                    
                    if "text" in part:
                        response_text = part["text"]
                    elif "functionCall" in part:
                        # Convert native function call back to our [TOOL: name(args)] format 
                        # so the existing tool-parsing logic can handle it seamlessly.
                        fn = part["functionCall"]
                        name = fn["name"]
                        args = fn.get("args", {})
                        
                        # Map native structured args back to our pipe-separated string format
                        if name in ["web_search", "deep_search", "thinking", "scout_file", "read_file"]:
                            val = next(iter(args.values())) if args else ""
                            response_text = f"[TOOL: {name}({val})]"
                        elif name == "generate_report":
                            response_text = f"[TOOL: {name}({args.get('title','')}|{args.get('content','')})]"
                        elif name == "report_generation":
                            response_text = f"[TOOL: {name}({args.get('topic','')}|{args.get('context','')})]"
                        elif name == "write_file":
                            response_text = f"[TOOL: {name}({args.get('filename','')}|{args.get('content','')})]"
                        elif name == "message_agent":
                            response_text = f"[TOOL: {name}({args.get('target_id','')}|{args.get('message','')})]"
                        elif name in ["list_workspace"]:
                            response_text = f"[TOOL: {name}()]"
                        else:
                            # Fallback
                            arg_str = " | ".join([str(v) for v in args.values()])
                            response_text = f"[TOOL: {name}({arg_str})]"
                    else:
                        response_text = "I am processing the results."
=======
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200:
                try:
                    response_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
                except Exception as e:
                    error_msg = f"Gemini API parsing error: {e}"
            else:
                error_msg = f"Gemini API Error: {response.text}"
        else:
            error_msg = f"Provider '{provider}' not implemented."

        if error_msg:
            print(f"[STATUS:{request.agent_id}] Error", flush=True)
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
<<<<<<< HEAD
        
        # Safety check: if stripping thoughts left us with an empty string, 
        # provide a fallback so the API doesn't crash on the next turn.
        if not response_text.strip():
            response_text = "I have processed the request. Please let me know how to proceed."
=======
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607

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
            print(f"[STATUS:{request.agent_id}] {friendly_action} for {tool_input[:30]}...", flush=True)
            
            # 2. Execute Tool from global basket
            tool_result = perform_tool_call(request.agent_id, tool_name, tool_input, agent_dir, api_key=request.api_key)
            
            # --- API PROTECTION: TRUNCATE HUGE TOOL RESULTS ---
            if isinstance(tool_result, str) and len(tool_result) > 10000:
                tool_result = (f"SYSTEM WARNING: Tool result too big ({len(tool_result)} chars). "
                               f"Truncated for API safety. Result head:\n{tool_result[:5000]}...\n\n"
                               f"STRICT INSTRUCTION: Do NOT try to read this much data again. Read it in smaller chunks.")

<<<<<<< HEAD
            # 3. For web_search and report_generation: the tool result is the final answer.
            #    Return it directly to avoid unwanted conversational summaries.
            if tool_name in ["web_search", "report_generation"]:
                # IMPORTANT: Even for direct-return tools, we MUST update history 
                # so the NEXT turn knows what was found (prevents hallucination).
                history.append({"role": "assistant", "content": response_text})
                history.append({"role": "user", "content": f"SYSTEM TOOL RESULT: {tool_result}"})
                final_response = tool_result
=======
            # 3. For web_search: the synthesized result IS the final answer.
            #    Return it directly so the LLM doesn't re-summarize and strip the sources/links.
            if tool_name == "web_search":
                final_response = tool_result
                history.append({"role": "assistant", "content": response_text})
>>>>>>> 1846afc321911808c7e60d319a425d0b6ac26607
                break
            
            # 4. For other tools: feed result back for another LLM turn
            history.append({"role": "assistant", "content": response_text})
            history.append({"role": "user", "content": f"SYSTEM TOOL RESULT: {tool_result}"})
            
            # Injection: Warn the agent if they are about to run out of steps
            if iteration == max_turns - 2:
                history.append({"role": "user", "content": "SYSTEM WARNING: You are approaching your maximum step limit (1 turn remaining). Please summarize your progress and tell the user specifically what is left to do, then stop. The user can say 'Continue' to give you more steps."})
            
            iteration += 1
        else:
            final_response = response_text
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
    
    # ── POST-PROCESS: Ruthless Sanitization ─────────────────────
    if final_response:
        final_response = sanitize_ruthlessly(final_response)

    history.append({"role": "assistant", "content": final_response})
    
    # RUTHLESS: Sanitize the ENTIRE history before saving to disk
    # This prevents intermediate tool leaks from staying in the chat UI
    sanitized_history = []
    for entry in history:
        sanitized_history.append({
            "role": entry["role"],
            "content": sanitize_ruthlessly(entry["content"])
        })
    
    # Save the SANITIZED history
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(sanitized_history, f, indent=2)

    # Check if we need to refresh the summary (every 50 messages, or when count > 60)
    # This keeps the summary updated incrementally.
    if len(sanitized_history) > 60:
        # We summarize the part that is likely to be rotated out of the sliding window soon
        new_summary = refresh_conversation_summary(
            request.agent_id, 
            sanitized_history[:-30], # Summarize everything older than the last 30
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
