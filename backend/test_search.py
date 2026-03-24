import asyncio
from duckduckgo_search import DDGS

async def test_search():
    print("Trying keywords= and list() conversion...")
    try:
        with DDGS() as ddgs:
            # Explicit keywords
            # Fixed in v6: text() takes keywords=
            res = list(ddgs.text(keywords="python development", max_results=5))
            print(f"Results: {len(res)}")
            for r in res:
                print(f"- {r.get('title')}")
                
    except Exception as e:
        print(f"Error type: {type(e).__name__}")
        print(f"Error msg: {e}")

if __name__ == "__main__":
    asyncio.run(test_search())
