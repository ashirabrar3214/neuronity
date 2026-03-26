import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from toolkit import _ddgs_search_raw, scrape_website
from graph.knowledge_store import KnowledgeStore

async def test_agent_simulation():
    agent_id = "test_agent_real_sim_01"
    query = "Rise of AI market growth 2024"
    
    # ensure clean slate
    store = KnowledgeStore(agent_id)
    store.clear()
    
    print(f"--- 1. Agent executes: web_search('{query}') ---")
    results = await _ddgs_search_raw(query, agent_id)
    
    if isinstance(results, str):
        print(f"Search failed: {results}")
        return
        
    print(f"Found {len(results)} URLs")
    for r in results:
        print(f"  - {r['href']}")
        
    print(f"\n--- 2. Agent executes: scrape_website() on up to 20 URLs ---")
    
    success_count = 0
    fail_count = 0
    
    # Run the scrapes (sequential for the test, an agent orchestrator might batch them)
    # We will limit to 5 for speed, or let's do all 20 since the user wants to see it scale
    # I'll let it rip on all urls
    
    for i, r in enumerate(results):
        url = r['href']
        print(f"\n[{i+1}/{len(results)}] Scraping {url} ...")
        res = await scrape_website(url, agent_id)
        
        if "Scraped successfully but no main text" in res or "Error:" in res:
            print(f"⚠️ Warning/Fail: {res.split(str(url))[-1][:100].strip()}...")
            fail_count += 1
        else:
            print("✅ Success! Facts mapped to Knowledge Graph.")
            success_count += 1
            
    print(f"\n--- 3. Scraping Summary ---")
    print(f"Success: {success_count} | Fails/Empty: {fail_count} | Total Attempted: {len(results)}")
    
    print(f"\n--- 4. Inspecting final Knowledge Graph ---")
    store.load()
    print(f"Path: backend/agents_code/{agent_id}/knowledge/graph.json")
    print(f"Nodes in Graph: {len(store.graph.nodes)}")
    print(f"Edges in Graph: {len(store.graph.edges)}")
    
    # Just grab some facts to prove they exist
    facts = [data for _, data in store.graph.nodes(data=True) if data.get('type') == 'FACT']
    print(f"Total structured facts extracted: {len(facts)}")
    if facts:
        print(f"Sample Fact 1: {facts[0].get('content')}")
        if len(facts) > 1:
            print(f"Sample Fact 2: {facts[-1].get('content')}")

if __name__ == "__main__":
    if sys.stdout.encoding != 'utf-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    asyncio.run(test_agent_simulation())
