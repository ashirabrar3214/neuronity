import requests
import json
import os

def deliberate(agent_id, message, api_key, provider, beliefs_context):
    """
    Goal Filter Phase (Deliberation).
    Decides if the agent has enough information to "Solve" (Intend) 
    or should "Clarify" (Ask a question).
    """
    if not message or len(message.strip()) < 5:
        return "CLARIFY", "Please provide more detail about your request."

    global_obj = beliefs_context.get("global_objective", "None")
    
    prompt = f"""You are the Deliberation Module of a BDI Agent. 
Current Beliefs (Objective): {global_obj}
Incoming Desire (User Message): "{message}"

Your job is to decide if we have enough information to commit to a concrete Plan (Solve) 
or if we must ask a question (Clarify).

RULES:
- If the request is vague (e.g. "Find news", "Report on war") without specific entities or goals, choose CLARIFY.
- If the request is conversational (e.g. "Thanks!", "Hi") choose CLARIFY.
- If the request is a specific task we can act on using web search or file tools, choose SOLVE.

Return ONLY a JSON object:
{{"decision": "SOLVE" | "CLARIFY", "reason": "Why did you make this choice?"}}
"""

    model = "gemini-2.0-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    data = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    
    try:
        resp = requests.post(url, json=data, timeout=30)
        if resp.status_code == 200:
            res_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Clean JSON from markdown if exists
            if "```json" in res_text:
                res_text = res_text.split("```json")[1].split("```")[0].strip()
            elif "```" in res_text:
                res_text = res_text.split("```")[1].strip()
            
            res_json = json.loads(res_text)
            return res_json.get("decision", "CLARIFY"), res_json.get("reason", "")
    except Exception as e:
        print(f"!!! [DELIBERATOR ERROR] {e}")

    return "CLARIFY", "Encountered an error in deliberation logic."
