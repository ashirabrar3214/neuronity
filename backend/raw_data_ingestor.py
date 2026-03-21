"""
ETL Ingestor: URL -> HTML -> sentence-aware chunked text -> ChromaDB

Bypasses the LLM entirely. Useful for ingesting full article pages cheaply
so the vector store can answer queries later via the "Look Before You Leap" gate.
"""

import asyncio
import re
import brf

CHUNK_TARGET = 800   # Target chars per chunk before we start a new one
OVERLAP_SENTENCES = 2  # Number of trailing sentences carried into the next chunk


def _sentence_split(text):
    """Split text into sentences on '. ', '.\n', '! ', '? ' boundaries."""
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _sliding_window_chunks(text):
    """
    Build overlapping chunks from raw text.

    Strategy:
    - Split text into sentences.
    - Accumulate sentences until the chunk reaches CHUNK_TARGET chars.
    - Seed the next chunk with the last OVERLAP_SENTENCES sentences of the
      previous chunk so context is never severed at boundaries.
    """
    sentences = _sentence_split(text)
    if not sentences:
        return []

    chunks = []
    current = []
    current_len = 0

    for sent in sentences:
        current.append(sent)
        current_len += len(sent) + 1  # +1 for the space separator

        if current_len >= CHUNK_TARGET:
            chunks.append(" ".join(current))
            # Carry last OVERLAP_SENTENCES sentences into the next chunk
            current = current[-OVERLAP_SENTENCES:] if len(current) > OVERLAP_SENTENCES else list(current)
            current_len = sum(len(s) + 1 for s in current)

    if current:
        chunks.append(" ".join(current))

    return chunks


async def ingest_url(url: str, agent_id: str) -> str:
    """
    Fetch a URL, strip the HTML boilerplate, chunk the plain text using a
    sentence-aware sliding window, and embed each chunk into ChromaDB.

    Also writes a one-line summary entry to knowledge_base.json so other
    agents can see this source was ingested.

    Returns a status string for the agent to report.
    """
    try:
        import httpx
        from bs4 import BeautifulSoup
    except ImportError as e:
        return f"Error: Missing dependency — {e}. Run: pip install httpx beautifulsoup4"

    # Fetch the page (spoofing a browser UA to avoid 403s)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text
    except Exception as e:
        return f"Error: Could not fetch {url} — {e}"

    # Strip HTML to plain text
    try:
        soup = BeautifulSoup(html, "html.parser")
        # Remove script/style noise
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        plain_text = soup.get_text(separator="\n")
        # Collapse excessive whitespace
        plain_text = re.sub(r'\n{3,}', '\n\n', plain_text).strip()
    except Exception as e:
        return f"Error: HTML parsing failed for {url} — {e}"

    if len(plain_text) < 50:
        return f"Warning: Page at {url} yielded very little text ({len(plain_text)} chars). Skipping."

    # Build chunks and embed into ChromaDB
    chunks = _sliding_window_chunks(plain_text)
    if not chunks:
        return f"Warning: Could not extract chunks from {url}."

    for i, chunk in enumerate(chunks):
        doc_id = f"{url}::chunk_{i}"
        brf.add_to_vector_store(chunk, url, agent_id, doc_id=doc_id)

    # Write a summary entry to knowledge_base.json for visibility
    summary = f"[Ingested] Full text of: {url} ({len(chunks)} chunks, {len(plain_text)} chars)"
    brf.update_belief_base(agent_id, summary, url)

    return f"Ingested {len(chunks)} chunks from {url} into the vector knowledge base."
