import httpx
import json
import os

# -- LLM Models (Abstracting for easy upgrades) --
FAST_MODEL = os.getenv("FAST_MODEL", "gemini-2.0-flash")
REASONING_MODEL = os.getenv("REASONING_MODEL", "gemini-3-flash-preview")

# Constants from interpreter (or similar)
DATA_FILE = os.path.join(os.path.dirname(__file__), "agents.json")

def load_agents():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

async def deliberate(agent_id, message, api_key, provider, beliefs_context, history=None, capabilities=None):
    """
    Goal Filter Phase (Deliberation).
    Decides if the agent has enough information to "Solve" (Intend),
    if it needs to "RE-PLAN" (Pivot), or should "Clarify" (Ask a question).
    capabilities: list of permission strings from the agent's config (e.g. ["web search", "report generation"])
    """
    # Only short-circuit on length if there is NO history to provide context
    if not message or (len(message.strip()) < 5 and not history):
        return "CLARIFY", "Please provide more detail about your request."

    # 1. Load Persona Data
    agent_dir = os.path.join(os.path.dirname(__file__), "agents_code", agent_id)
    personality_path = os.path.join(agent_dir, "personality.json")
    
    personality = {}
    if os.path.exists(personality_path):
        try:
            with open(personality_path, "r", encoding="utf-8") as f:
                personality = json.load(f)
        except: pass

    # Fallback to agents.json if personality.json is missing or incomplete
    if not personality:
        agents = load_agents()
        personality = next((a for a in agents if a["id"] == agent_id), {})

    role = personality.get("name", "Unknown Agent")
    description = personality.get("description", "A helpful AI assistant.")
    responsibility = personality.get("responsibility", "General task execution.")
    
    # 2. Format History for Context
    history_str = "No recent history provided."
    if history:
        # Only take the last 10 messages for brevity in deliberation
        recent = history[-10:]
        h_lines = []
        for h in recent:
            role_label = "Agent" if h.get("role") == "assistant" else "User"
            content = h.get("content", "")
            if content:
                preview = content[:300] + "..." if len(content) > 300 else content
                h_lines.append(f"[{role_label}]: {preview}")
        history_str = "\n".join(h_lines)

    global_obj = beliefs_context.get("global_objective", "None")
    capabilities_str = ", ".join(capabilities) if capabilities else "unknown"

    prompt = f"""You are the Deliberation Module of a True BDI (Belief-Desire-Intention) Agent.

--- AGENT IDENTITY ---
Role: {role}
Description: {description}
Key Responsibility: {responsibility}

--- AVAILABLE TOOLS ---
This agent has access to the following tools: {capabilities_str}
IMPORTANT: If a task can be accomplished with one of the tools above, that task IS within this agent's scope. Do NOT declare a capability gap for tools that appear in this list.

--- COGNITIVE STATE ---
Global Objective: {global_obj}
Recent Conversation/Action History:
{history_str}

Incoming Desire (New Request/Current Step): "{message}"

--- TASK ---
Decide if we should:
1. SOLVE: We have a clear task, and it is within our responsibility. Or, if we are in the middle of a task, this new observation confirms we are on the right track.
2. CLARIFY: The request is vague, or we lack critical context (like a report topic) that isn't in our history.
3. RE-PLAN: The new data contradicts our current plan or suggests we need to completely change our approach.

RULES:
- If the message is a casual greeting or vague AND no clear objective exists in history, choose CLARIFY.
- If history shows we already have the objective and the user is just following up, choose SOLVE.
- Use your specific Persona (Description/Responsibility) to decide if this task is YOURS.
- Look for "Ongoing task:" markers in the message to detect mid-execution states.
- NEVER choose RE-PLAN due to a "missing capability" if the required tool IS listed in Available Tools above.

Return ONLY a JSON object:
{{
  "decision": "SOLVE" | "CLARIFY" | "RE-PLAN",
  "reason": "Short, logical Explanation for your choice."
}}
"""

    model = FAST_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                res_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                # Clean JSON from markdown
                if "```json" in res_text:
                    res_text = res_text.split("```json")[1].split("```")[0].strip()
                elif "```" in res_text:
                    res_text = res_text.split("```")[1].strip()
                
                res_json = json.loads(res_text)
                return res_json.get("decision", "CLARIFY"), res_json.get("reason", "")
    except Exception as e:
        print(f"!!! [DELIBERATOR ERROR] {e}")

    return "CLARIFY", "Encountered an error in deliberation logic."
