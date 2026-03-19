import json
import os
import time
import requests

AGENTS_CODE_DIR = os.path.join(os.path.dirname(__file__), "agents_code")
BELIEFS_BASE_FILE = os.path.join(AGENTS_CODE_DIR, "beliefs_base.json")
BELIEFS_CONTEXT_FILE = os.path.join(AGENTS_CODE_DIR, "beliefs_context.json")
CORE_BELIEFS_FILE = os.path.join(AGENTS_CODE_DIR, "core_beliefs.json")

def update_belief_base(agent_id, fact, url="", session_id=None):
    """
    Belief Revision Function (BRF) with Fact Arbiter. 
    Updates the shared fact ledger with session-aware, verified information.
    """
    if not fact or len(fact.strip()) < 5:
        return False

    # 1. Load existing beliefs
    beliefs = []
    if os.path.exists(BELIEFS_BASE_FILE):
        try:
            with open(BELIEFS_BASE_FILE, "r", encoding="utf-8") as f:
                beliefs = json.load(f)
        except: pass

    # 2. Fact Arbiter: Check for contradictions or duplicates
    # For now, we use a simple overlap/substring check. 
    # High-level BDI would use a semantic LLM pass here.
    for b in beliefs:
        # Avoid exact duplicates
        if b["fact"].lower() == fact.lower():
            return True # Already known
        
    # 3. Tiered Archiving: "Belief Strengthening"
    # If a fact is mentioned across 3 different sessions, promote it to CORE.
    # (Simplified for now: count occurrences of similar facts)
    all_facts = [b["fact"].lower() for b in beliefs]
    similar_count = sum(1 for f in all_facts if fact.lower()[:50] in f)
    
    if similar_count >= 3:
        promote_to_core(fact, url)

    belief = {
        "agent_id": agent_id,
        "session_id": session_id,
        "timestamp": time.time(),
        "fact": fact,
        "url": url,
        "relevance": 1.0 # Initial relevance
    }
    
    beliefs.append(belief)
    
    with open(BELIEFS_BASE_FILE, "w", encoding="utf-8") as f:
        json.dump(beliefs, f, indent=2, ensure_ascii=False)
    
    return True

def promote_to_core(fact, url):
    """Promotes a high-confidence belief to the persistent Core Beliefs store."""
    core = []
    if os.path.exists(CORE_BELIEFS_FILE):
        try:
            with open(CORE_BELIEFS_FILE, "r", encoding="utf-8") as f:
                core = json.load(f)
        except: pass

    # Check for duplicates in core
    if any(c["fact"].lower() == fact.lower() for c in core):
        return

    core.append({
        "fact": fact,
        "url": url,
        "promoted_at": time.time()
    })

    with open(CORE_BELIEFS_FILE, "w", encoding="utf-8") as f:
        json.dump(core, f, indent=2, ensure_ascii=False)

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
    """Reads Context, Core, and Base beliefs."""
    context = {"global_objective": "No objective set."}
    if os.path.exists(BELIEFS_CONTEXT_FILE):
        try:
            with open(BELIEFS_CONTEXT_FILE, "r", encoding="utf-8") as f:
                context = json.load(f)
        except: pass
        
    core = []
    if os.path.exists(CORE_BELIEFS_FILE):
        try:
            with open(CORE_BELIEFS_FILE, "r", encoding="utf-8") as f:
                core = json.load(f)
        except: pass

    facts = []
    if os.path.exists(BELIEFS_BASE_FILE):
        try:
            with open(BELIEFS_BASE_FILE, "r", encoding="utf-8") as f:
                facts = json.load(f)
        except: pass
        
    return context, facts + core
