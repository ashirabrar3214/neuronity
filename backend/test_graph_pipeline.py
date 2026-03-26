import asyncio
import json
import os
import sys

# Ensure backend imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from toolkit import scrape_website
from graph.knowledge_store import KnowledgeStore
from ddgs import DDGS

async def run_test():
    agent_id = "test_agent_llm"
    print("--- 1. Searching for 'rise of LLMs' ---")
    # Quick search using ddgs
    try:
        search_results = DDGS().text("rise of LLMs", max_results=2)
        urls = [r["href"] for r in search_results][:2]
    except Exception as e:
        print(f"Search failed, using fallback URLs: {e}")
        urls = [
            "https://en.wikipedia.org/wiki/Large_language_model",
            "https://www.ibm.com/topics/large-language-models"
        ]
    
    print(f"Will scrape the following URLs: {urls}")
    
    print("\n--- 2. Scraping and Knowledge Injection (Processing...) ---")
    for url in urls:
        print(f"Scraping: {url}...")
        # Scrape website handles extraction and graph injection internally now!
        res = await scrape_website(url, agent_id)
        if "Error" in res:
            print(f"Failed to scrape: {res}")
        else:
            print(f"Success! Passed {len(res)} characters back to text context.")

    print("\n--- 3. Verifying Graph Structure ---")
    store = KnowledgeStore(agent_id)
    store.load()
    
    sources = [n for n, attrs in store.graph.nodes(data=True) if attrs.get("node_type") == "source"]
    entities = [n for n, attrs in store.graph.nodes(data=True) if attrs.get("node_type") == "entity"]
    
    print(f"\nTotal Sources Saved: {len(sources)}")
    print(f"Total Entities (Hopping Points) Created: {len(entities)}")
    
    print("\n--- Sample Entity Graph Connections ---")
    # Show first 10 entities
    for ent in entities[:10]:
        attrs = store.graph.nodes[ent]
        # find what sources 'ent' is connected to via 'mentioned_in'
        mentions = list(store.graph.neighbors(ent))
        print(f"  [{attrs.get('category')}] {attrs.get('label')} --> Mentioned in {len(mentions)} source(s)")
        
    print(f"\nGraph successfully saved to: backend/agents_code/{agent_id}/knowledge/graph.json")
    print("You can view the full JSON file to see the extracted tables, dates, and full text nodes!")

if __name__ == "__main__":
    asyncio.run(run_test())
