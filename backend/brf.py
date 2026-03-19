import json
import os
import time

AGENTS_CODE_DIR = os.path.join(os.path.dirname(__file__), "agents_code")
BELIEFS_BASE_FILE = os.path.join(AGENTS_CODE_DIR, "beliefs_base.json")
BELIEFS_CONTEXT_FILE = os.path.join(AGENTS_CODE_DIR, "beliefs_context.json")

def update_belief_base(agent_id, fact, url=""):
    """
    Belief Revision Function (BRF). 
    Updates the shared fact ledger (Belief Base) with new information.
    """
    belief = {
        "agent_id": agent_id,
        "timestamp": time.time(),
        "fact": fact,
        "url": url
    }
    
    beliefs = []
    if os.path.exists(BELIEFS_BASE_FILE):
        try:
            with open(BELIEFS_BASE_FILE, "r", encoding="utf-8") as f:
                beliefs = json.load(f)
        except: pass
    
    beliefs.append(belief)
    
    with open(BELIEFS_BASE_FILE, "w", encoding="utf-8") as f:
        json.dump(beliefs, f, indent=2, ensure_ascii=False)
    
    return True

def update_belief_context(new_goal):
    """
    Updates the Identity Beliefs and Environment State (Belief Context).
    """
    if not new_goal or len(new_goal.strip()) < 10:
        return False
        
    context = {
        "global_objective": new_goal.strip(),
        "last_update": time.time()
    }
    
    with open(BELIEFS_CONTEXT_FILE, "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2)
    
    return True

def get_beliefs():
    """Reads both the Context and Fact beliefs."""
    context = {"global_objective": "No objective set."}
    if os.path.exists(BELIEFS_CONTEXT_FILE):
        try:
            with open(BELIEFS_CONTEXT_FILE, "r", encoding="utf-8") as f:
                context = json.load(f)
        except: pass
        
    facts = []
    if os.path.exists(BELIEFS_BASE_FILE):
        try:
            with open(BELIEFS_BASE_FILE, "r", encoding="utf-8") as f:
                facts = json.load(f)
        except: pass
        
    return context, facts
