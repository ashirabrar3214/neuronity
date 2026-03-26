import asyncio
import os
import sys
import json
from dotenv import load_dotenv

# Load your environment variables
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from toolkit import report_generation
from graph.knowledge_store import KnowledgeStore

async def test_synthesis():
    # --- CHANGE THIS TO YOUR LATEST AGENT FOLDER ---
    target_agent_id = "agent-bot-1774558755353" 
    # -----------------------------------------------
    
    working_dir = os.path.join(os.path.dirname(__file__), "agents_code", target_agent_id)
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in environment.")
        return

    print(f"Loading Knowledge Graph for {target_agent_id}...")
    store = KnowledgeStore(target_agent_id)
    store.load()
    
    # 1. Manually pull the deep facts to see what Gemini is actually getting
    all_facts = []
    print("\n--- EXTRACTING FACTS FROM GRAPH ---")
    topics = store.get_all_topics()
    if not topics:
        print("⚠️ No topics found in graph. Pulling raw facts...")
        # Fallback if topics are missing
        for nid, attrs in store.graph.nodes(data=True):
            if attrs.get("node_type") == "fact":
                srcs = store.get_sources_for_fact(nid)
                src = srcs[0]["url"] if srcs else "unknown"
                ev = attrs.get("context_or_evidence", "")
                fact_text = f"- CLAIM: {attrs['content']}"
                if ev:
                    fact_text += f"\n  EVIDENCE: {ev}"
                fact_text += f"\n  SOURCE: {src}"
                all_facts.append(fact_text)
    else:
        for topic in topics:
            facts = store.get_facts_by_topic(topic["label"])
            for f in facts:
                src = f["sources"][0]["url"] if f["sources"] else "unknown"
                ev = f.get("context_or_evidence", "")
                
                fact_text = f"- CLAIM: {f['content']}"
                if ev:
                    fact_text += f"\n  EVIDENCE: {ev}"
                fact_text += f"\n  SOURCE: {src}"
                all_facts.append(fact_text)
            
    facts_context = "\n\n".join(all_facts)
    
    if not all_facts:
        print("❌ ERROR: Your Knowledge Map is empty! There are no facts.")
        return
        
    print(f"✅ Found {len(all_facts)} deep facts.")
    print("\n--- SNEAK PEEK OF DATA GOING TO GEMINI 3.1 PRO ---")
    print(facts_context[:800] + "\n...\n--------------------------------------------------\n")
    
    # 2. Trigger Gemini 3.1 Pro
    topic = "The Rise and Strategic Evolution of Large Language Models"
    # The tool_input for report_generation in toolkit.py expects "Topic|ProvidedContext"
    tool_input = f"{topic}|{facts_context}"
    
    print("🧠 Firing Gemini 3.1 Pro (This takes 30-60 seconds)...")
    try:
        result = await report_generation(
            agent_id=target_agent_id, 
            tool_input=tool_input, 
            working_dir=working_dir, 
            api_key=api_key, 
            agent_name="TestAgent"
        )
        
        print("\n=== SYNTHESIS RESULT ===")
        print(result)
        
        # If it generated a file, let's try to read it
        if "Report generated:" in result:
            filename = result.split(": ")[1].split(". (")[0]
            # Replace .pdf with .md if it was markdown, but toolkit says it saves PDF
            # Wait, toolkit saves PDF but it also creates the Markdown report in generate_report?
            # No, report_generation creates a PDF using ReportPDFGenerator.
            # But generate_report (simpler tool) creates .md.
            print(f"PDF generated at: {os.path.join(working_dir, filename)}")
            
    except Exception as e:
        print(f"❌ CRITICAL ERROR during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Fix for Windows console encoding
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    elif sys.stdout.encoding != 'utf-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        
    asyncio.run(test_synthesis())
