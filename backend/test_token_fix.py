import asyncio
import json
import os
import sys

# Ensure backend imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from toolkit import scrape_website
from graph.knowledge_store import KnowledgeStore

async def test_token_removal():
    agent_id = "token_tester"
    # Use a solid URL that doesn't block scrapers
    url = "https://nvidianews.nvidia.com/news/nvidia-blackwell-platform-arrives-to-power-a-new-era-of-computing"
    
    print(f"--- 1. Scraping: {url} ---")
    res = await scrape_website(url, agent_id)
    
    print("\n--- 2. Verifying full_text removal in LLM Context output ---")
    store = KnowledgeStore(agent_id)
    store.load()
    
    # Get the "Dirty" data (Original file on disk)
    disk_path = os.path.join(store.knowledge_dir, "graph.json")
    with open(disk_path, 'r', encoding='utf-8') as f:
        disk_graph = json.load(f)
    
    has_full_text_on_disk = any("full_text" in node for node in disk_graph.get("nodes", []))
    print(f"Original Graph on Disk has 'full_text'? {has_full_text_on_disk} (Should be True)")

    # Get the "Cleaned" data (The tool output)
    llm_graph = store.get_llm_graph()
    has_full_text_in_llm_payload = any("full_text" in node for node in llm_graph.get("nodes", []))
    
    print(f"Cleaned LLM Graph has 'full_text'? {has_full_text_in_llm_payload} (MUST BE FALSE)")
    
    if not has_full_text_in_llm_payload:
        print("\nVerification SUCCESS: full_text field successfully stripped for LLM consumption.")
    else:
        print("\n❌ Verification FAILED: full_text is still bleeding into the LLM context!")

    print(f"\nGraph Stats: {len(llm_graph['nodes'])} nodes, {len(llm_graph['links'])} edges.")

if __name__ == "__main__":
    asyncio.run(test_token_removal())
