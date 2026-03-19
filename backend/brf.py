import json
import os
import time

AGENTS_CODE_DIR = os.path.join(os.path.dirname(__file__), "agents_code")
# CHANGE 1: Use the single Knowledge Base Ledger
KNOWLEDGE_BASE_FILE = os.path.join(AGENTS_CODE_DIR, "knowledge_base.json")

def _load_kb():
    if os.path.exists(KNOWLEDGE_BASE_FILE):
        try:
            with open(KNOWLEDGE_BASE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"context": {"global_objective": "No objective set."}, "base_facts": [], "core_facts": []}

def _save_kb(data):
    with open(KNOWLEDGE_BASE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def update_belief_base(agent_id, fact, url="", session_id=None):
    if not fact or len(fact.strip()) < 5:
        return False

    kb = _load_kb()
    beliefs = kb.get("base_facts", [])

    for b in beliefs:
        if b["fact"].lower() == fact.lower():
            return True 
        
    all_facts = [b["fact"].lower() for b in beliefs]
    similar_count = sum(1 for f in all_facts if fact.lower()[:50] in f)
    
    if similar_count >= 3:
        promote_to_core(fact, url, kb)

    beliefs.append({
        "agent_id": agent_id,
        "session_id": session_id,
        "timestamp": time.time(),
        "fact": fact,
        "url": url,
        "relevance": 1.0
    })
    
    kb["base_facts"] = beliefs
    _save_kb(kb)
    return True

def promote_to_core(fact, url, kb):
    core = kb.get("core_facts", [])
    if any(c["fact"].lower() == fact.lower() for c in core):
        return

    core.append({
        "fact": fact, "url": url, "promoted_at": time.time()
    })
    kb["core_facts"] = core

def update_belief_context(new_goal):
    if not new_goal or len(new_goal.strip()) < 10:
        return False
        
    kb = _load_kb()
    kb["context"] = {"global_objective": new_goal.strip(), "last_update": time.time()}
    _save_kb(kb)
    return True

def get_beliefs():
    kb = _load_kb()
    return kb.get("context", {}), kb.get("base_facts", []) + kb.get("core_facts", [])

def clear_volatile_beliefs():
    kb = _load_kb()
    kb["base_facts"] = []
    _save_kb(kb)
