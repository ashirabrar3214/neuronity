import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from toolkit import scrape_website
from graph.knowledge_store import KnowledgeStore

async def test():
    # Example difficult URL to scrape (e.g. cloudflare protected or complex JS)
    url = "https://www.goldmansachs.com/insights/pages/the-rise-of-ai.html"
    agent_id = "test_scraper_agent"
    
    # ensure clean slate
    store = KnowledgeStore(agent_id)
    store.clear()
    
    print(f"Scraping {url}...")
    res = await scrape_website(url, agent_id)
    print(f"\n--- Result ---\n{res[:1000]}") # Print first 1000 chars of result

if __name__ == "__main__":
    if sys.stdout.encoding != 'utf-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    asyncio.run(test())
