import httpx
import json
import os

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

async def deliberate(agent_id, message, api_key, provider, beliefs_context):
    """
    Goal Filter Phase (Deliberation).
    Decides if the agent has enough information to "Solve" (Intend), 
    if it needs to "RE-PLAN" (Pivot), or should "Clarify" (Ask a question).
    """
    if not message or len(message.strip()) < 5:
        return "CLARIFY", "Please provide more detail about your request."

    # 1. Load Persona Data
    agents = load_agents()
    persona = next((a for a in agents if a["id"] == agent_id), {})
    role = persona.get("name", "Unknown Agent")
    description = persona.get("description", "A helpful AI assistant.")
    responsibility = persona.get("responsibility", "General task execution.")
    permissions = persona.get("permissions", [])
    capabilities = ", ".join(permissions) if permissions else "none"

    global_obj = beliefs_context.get("global_objective", "None")
    
    prompt = f"""You are the Deliberation Module of a True BDI (Belief-Desire-Intention) Agent.
    
--- AGENT IDENTITY ---
Role: {role}
Description: {description}
Key Responsibility: {responsibility}
Available Capabilities: {capabilities}

--- COGNITIVE STATE ---
Current Beliefs (Goal): {global_obj}
Incoming Desire (Request/Step): "{message}"

--- TASK ---
Decide if we should:
1. SOLVE: We have a clear task and all information needed to start or continue.
2. CLARIFY: The request is vague, conversational, or outside our responsibility.
3. RE-PLAN: We are already executing a task, but this new information suggests our current intentions are obsolete or we need a major pivot.

RULES:
- If the message is a casual greeting or vague, choose CLARIFY.
- If the message is a specific actionable task within our responsibility, choose SOLVE.
- If the message contains "Ongoing task:" and you detect a contradiction with current info, choose RE-PLAN.
- Be decisive. SOLVE is the default for clear tasks.

Return ONLY a JSON object:
{{
  "decision": "SOLVE" | "CLARIFY" | "RE-PLAN",
  "reason": "Short, logical Explanation for your choice."
}}
"""

    model = "gemini-2.0-flash"
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
