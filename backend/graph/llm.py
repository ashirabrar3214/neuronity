import os
import time
from langchain_google_genai import ChatGoogleGenerativeAI

FAST_MODEL = os.getenv("FAST_MODEL", "gemini-2.0-flash")
REASONING_MODEL = os.getenv("REASONING_MODEL", "gemini-2.0-flash")
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "gemini-3.1-pro-preview")

# Minimum token count for Gemini context caching (API requirement)
_MIN_CACHE_TOKENS = 4096


def get_llm(mode: str = "fast", api_key: str = "", streaming: bool = True, cached_content: str = None):
    """Return a ChatGoogleGenerativeAI instance.

    mode:
      "fast"    — gemini-2.0-flash, for execution and compression
      "think"   — REASONING_MODEL, legacy
      "planner" — gemini-3.1-pro-preview, for ReAct planning node

    cached_content: optional Gemini cache name to reference
    """
    key = api_key or os.getenv("GEMINI_API_KEY", "")

    if mode == "planner":
        model = PLANNER_MODEL
        temperature = 0.2
        streaming = False  # planner always non-streaming (structured JSON output)
    elif mode == "think":
        model = REASONING_MODEL
        temperature = 0.2
    else:
        model = FAST_MODEL
        temperature = 0.3

    kwargs = dict(
        model=model,
        google_api_key=key,
        temperature=temperature,
        max_output_tokens=8192,
        streaming=streaming,
    )

    if cached_content:
        kwargs["cached_content"] = cached_content

    return ChatGoogleGenerativeAI(**kwargs)


# ---------------------------------------------------------------------------
# Gemini Context Cache Manager
# ---------------------------------------------------------------------------

# In-memory registry of active caches: agent_id -> {name, model, expires, content_hash}
_active_caches: dict = {}


def create_research_cache(
    agent_id: str,
    model: str,
    system_prompt: str,
    research_context: str,
    api_key: str,
    ttl_seconds: int = 1800,  # 30 min default
) -> str | None:
    """
    Create or reuse a Gemini context cache for a research session.

    Caches the system prompt + accumulated research data so subsequent
    planner/executor calls don't re-send the full context every time.

    Returns the cache name if successful, None if context is too small.
    """
    from google import genai
    from google.genai import types

    full_content = f"{system_prompt}\n\n{research_context}"

    # Rough token estimate: ~4 chars per token
    est_tokens = len(full_content) // 4
    if est_tokens < _MIN_CACHE_TOKENS:
        return None

    # Check if we already have a valid cache for this agent with same content
    content_hash = hash(full_content)
    existing = _active_caches.get(agent_id)
    if existing and existing.get("content_hash") == content_hash:
        # Same content, check if still valid
        if existing.get("expires", 0) > time.time():
            return existing["name"]
        # Expired, will recreate below

    # Clean up old cache if exists
    if existing and existing.get("name"):
        try:
            client = genai.Client(api_key=api_key)
            client.caches.delete(name=existing["name"])
            print(f"+++ [CTX_CACHE] Deleted old cache for {agent_id}", flush=True)
        except Exception:
            pass

    # Create new cache
    try:
        client = genai.Client(api_key=api_key)
        cache = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                display_name=f"research-{agent_id[:20]}",
                system_instruction=full_content,
                ttl=f"{ttl_seconds}s",
            )
        )
        _active_caches[agent_id] = {
            "name": cache.name,
            "model": model,
            "expires": time.time() + ttl_seconds,
            "content_hash": content_hash,
        }
        token_count = getattr(cache, "usage_metadata", None)
        print(f"+++ [CTX_CACHE] Created cache '{cache.name}' for {agent_id} "
              f"(~{est_tokens} tokens, TTL={ttl_seconds}s, usage={token_count})", flush=True)
        return cache.name
    except Exception as e:
        print(f"!!! [CTX_CACHE] Failed to create cache: {e}", flush=True)
        return None


def get_active_cache(agent_id: str) -> str | None:
    """Get the active cache name for an agent, or None if expired/missing."""
    existing = _active_caches.get(agent_id)
    if existing and existing.get("expires", 0) > time.time():
        return existing["name"]
    return None


def invalidate_cache(agent_id: str, api_key: str = ""):
    """Delete and remove the cache for an agent."""
    existing = _active_caches.pop(agent_id, None)
    if existing and existing.get("name"):
        try:
            from google import genai
            key = api_key or os.getenv("GEMINI_API_KEY", "")
            client = genai.Client(api_key=key)
            client.caches.delete(name=existing["name"])
            print(f"+++ [CTX_CACHE] Invalidated cache for {agent_id}", flush=True)
        except Exception:
            pass
