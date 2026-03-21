import json
import os
import time
import threading

AGENTS_CODE_DIR = os.path.join(os.path.dirname(__file__), "agents_code")
KNOWLEDGE_BASE_FILE = os.path.join(AGENTS_CODE_DIR, "knowledge_base.json")

# --- ChromaDB Vector Store (lazy singleton) ----------------------------------
# Initialized on first use. Gracefully degrades to None if chromadb is not installed.
# All write calls use _chroma_lock to prevent SQLite contention on Windows.
_chroma_client = None
_chroma_collection = None
_chroma_lock = threading.Lock()
CHROMA_STORE_PATH = os.path.join(os.path.dirname(__file__), "chroma_store")


def _get_chroma_collection():
    """Return the ChromaDB collection, lazily initializing it on first call.
    Returns None if chromadb or sentence-transformers are not installed."""
    global _chroma_client, _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection
    with _chroma_lock:
        # Double-checked locking
        if _chroma_collection is not None:
            return _chroma_collection
        try:
            import chromadb
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
            os.makedirs(CHROMA_STORE_PATH, exist_ok=True)
            _chroma_client = chromadb.PersistentClient(path=CHROMA_STORE_PATH)
            emb_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
            _chroma_collection = _chroma_client.get_or_create_collection(
                name="easy_company_kb",
                embedding_function=emb_fn,
                metadata={"hnsw:space": "cosine"}
            )
            return _chroma_collection
        except ImportError:
            return None
        except Exception as e:
            print(f"[BRF] ChromaDB init failed: {e}", flush=True)
            return None


def add_to_vector_store(fact, url, agent_id, doc_id=None):
    """Embed and store a fact into ChromaDB alongside knowledge_base.json.
    doc_id defaults to str(hash(fact)) for deduplication — re-upserting the
    same fact is a no-op from ChromaDB's perspective."""
    collection = _get_chroma_collection()
    if collection is None:
        return
    if not fact or len(fact.strip()) < 5:
        return
    if doc_id is None:
        doc_id = str(hash(fact.strip()))
    try:
        with _chroma_lock:
            collection.upsert(
                ids=[doc_id],
                documents=[fact.strip()],
                metadatas=[{"url": url or "", "agent_id": agent_id or ""}]
            )
    except Exception as e:
        print(f"[BRF] ChromaDB upsert failed: {e}", flush=True)


def vector_search_beliefs(query, top_k=5, threshold=0.72):
    """Semantic search over the ChromaDB collection.

    Returns a list of (score, entry_dict) tuples where score >= threshold.
    score is the cosine similarity (1 - chroma_distance).
    Returns [] if ChromaDB is unavailable or no results meet the threshold.
    """
    collection = _get_chroma_collection()
    if collection is None:
        return []
    if not query or len(query.strip()) < 3:
        return []
    try:
        results = collection.query(
            query_texts=[query.strip()],
            n_results=min(top_k, max(collection.count(), 1)),
            include=["documents", "metadatas", "distances"]
        )
        hits = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            score = 1.0 - dist  # cosine similarity from cosine distance
            if score >= threshold:
                hits.append((score, {
                    "fact": doc,
                    "url": meta.get("url", ""),
                    "agent_id": meta.get("agent_id", "")
                }))
        hits.sort(key=lambda x: x[0], reverse=True)
        return hits
    except Exception as e:
        print(f"[BRF] ChromaDB query failed: {e}", flush=True)
        return []

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

    entry = {
        "agent_id": agent_id,
        "session_id": session_id,
        "timestamp": time.time(),
        "fact": fact,
        "url": url,
        "relevance": 1.0
    }
    beliefs.append(entry)
    kb["base_facts"] = beliefs
    _save_kb(kb)

    # Mirror to vector store for semantic search (fire-and-forget, non-blocking)
    add_to_vector_store(fact, url, agent_id)
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
