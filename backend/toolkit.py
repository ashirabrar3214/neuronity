import time
import os
import random
import json
import httpx
import asyncio
import re
from pdf_generator import ReportPDFGenerator
from graph.knowledge_store import KnowledgeStore

import trafilatura
from bs4 import BeautifulSoup
import spacy

# Load the smallest, fastest NLP model (uses < 200MB RAM)
try:
    nlp = spacy.load("en_core_web_sm")
except:
    # Fallback if not downloaded yet
    nlp = None

# -- LLM Models (Abstracting for easy upgrades) --
FAST_MODEL = os.getenv("FAST_MODEL", "gemini-2.0-flash")
REASONING_MODEL = os.getenv("REASONING_MODEL", "gemini-3-flash-preview")
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "gemini-3.1-pro-preview")

def get_training_context():
    """
    Returns the documentation block for training-only tools.
    """
    return """## TRAINING CAPABILITIES (Only active in Training Mode)
1. update_prompt(new_content): Use this to directly rewrite your own system instructions (prompt.md). Use this to fix behavioral bugs or refine your identity.
2. read_prompt(): Use this to see your current identity and behavioral rules.
3. read_memory(): Use this to read your long-term memory summary (summary.json).
"""

# ─────────────────────────────────────────────────
# WEB SEARCH CAPABILITY
# ─────────────────────────────────────────────────

import sys
import io

def safe_log(message, agent_id=None):
    """Prints a message safely, and writes to communication.log if agent_id is provided."""
    try:
        print(message, flush=True)
    except Exception:
        pass
    
    # NEW: Log to the specific agent's communication audit log
    if agent_id:
        log_dir = os.path.join(os.path.dirname(__file__), "agents_code", agent_id)
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "communication.log")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message}\n")
        except:
            pass

async def _ddgs_search_raw(query, agent_id):
    """
    Internal helper to fetch raw DuckDuckGo results.
    """
    safe_log(f"[STATUS:{agent_id}] DuckDuckGo: Searching '{query[:40]}...'", agent_id=agent_id)
    try:
        from ddgs import DDGS
        def do_search():
            results = []
            search_results = DDGS().text(query, max_results=20)
            for result in search_results:
                body = result.get("body", "")
                results.append({
                    "title": result.get("title", ""),
                    "href": result.get("href", ""),
                    "body": body[:250]
                })
            return results

        results = await asyncio.to_thread(do_search)
        safe_log(f"+++ [INTERNAL:search] Got {len(results)} results", agent_id=agent_id)
        return results
    except Exception as e:
        safe_log(f"!!! [INTERNAL:search] Error: {e}", agent_id=agent_id)
        # Surface the actual error so the planner knows search is broken, not just empty
        return f"__SEARCH_ERROR__: {str(e)}"



async def web_search(query, agent_id, api_key):
    """
    The new QUICK SEARCH tool. Just the facts.
    """
    # Robust parsing: handle hallucinations like query="..." or search="..."
    query = query.strip()
    if "=" in query and (query.lower().startswith("query=") or query.lower().startswith("search=")):
        query = query.split("=", 1)[-1].strip()
    query = query.strip("'").strip('"').strip("`")

    results = await _ddgs_search_raw(query, agent_id)
    if isinstance(results, str):
        return f"Search failed: {results}"
    if not results:
        return "No results found for the query. Try a different or more specific search term."

    # Return raw JSON-like format so Researcher can see URLs
    formatted_results = []
    for r in results:
        formatted_results.append(f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}")

    return "\n\n---\n\n".join(formatted_results)

# ─────────────────────────────────────────────────
# REPORT GENERATION CAPABILITY
# ─────────────────────────────────────────────────

async def generate_report(agent_id, tool_input, working_dir):
    """
    Generates a structured markdown report file in the agent's working directory.
    Usage: [TOOL: generate_report(Title|Content)]
    """
    safe_log(f"[STATUS:{agent_id}] Report: Draft for '{tool_input[:40]}...'", agent_id=agent_id)
    await asyncio.sleep(1)
    try:
        if not working_dir:
            return "Error: No working directory assigned. Cannot save report."
            
        if "|" in tool_input:
            title, content = tool_input.split("|", 1)
        else:
            title = "Report_" + str(int(time.time()))
            content = tool_input
        
        # Strip hallucinations like title="..." or content="..."
        title = title.strip()
        if "=" in title and title.lower().startswith("title="):
            title = title.split("=", 1)[-1].strip()
        title = title.strip("'").strip('"').strip("`")

        content = content.strip()
        if "=" in content and (content.lower().startswith("content=") or content.lower().startswith("body=")):
            content = content.split("=", 1)[-1].strip()
        content = content.strip("'").strip('"').strip("`")
        
        # Sanitize filename (remove quotes, brackets, and non-safe chars)
        clean_title = re.sub(r'[^a-zA-Z0-9\s_-]', '', title.strip().replace('"', ''))
        filename = f"{clean_title.replace(' ', '_')}.md"
        report_path = os.path.join(working_dir, filename)
        
        full_report = f"""# Agent Report: {title.strip()}
Generated by: {agent_id}
Date: {time.strftime("%Y-%m-%d %H:%M:%S")}

---

## Summary
{content.strip()}

---
## Sources & References
{'\n'.join([f'- {url}' for url in re.findall(r'https?://[^\s\)]+', content)]) if 'http' in content else 'No explicit URLs found in content.'}

---
*End of Report*"""

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(full_report)
            
        safe_log(f"+++ [CAPABILITY:generate_report] Saved to: {report_path}", agent_id=agent_id)
        return f"Report successfully generated: {filename}"
        
    except Exception as e:
        safe_log(f"!!! [CAPABILITY:generate_report] {str(e)}", agent_id=agent_id)
        return f"Error generating report: {str(e)}"

# ─────────────────────────────────────────────────
# COMPREHENSIVE REPORT GENERATION (PDF)
# ─────────────────────────────────────────────────

def _chunk_text(text, max_chars=12000):
    """Chunks text into pieces that fit LLM context limits."""
    return [text[i:i+max_chars] for i in range(0, len(text), max_chars)]

async def report_generation(agent_id, tool_input, working_dir, api_key, agent_name="Agent"):
    """
    Advanced tool that synthesizes a PDF research report using GraphRAG data and Gemini 3.1 Pro.
    Usage: [TOOL: report_generation(Topic)]
    """
    safe_log(f"[STATUS:{agent_id}] PDF: Synthesis for '{tool_input[:40]}...'", agent_id=agent_id)
    
    try:
        if not working_dir:
            return "Error: No working directory assigned. Cannot save report."
            
        # 1. Setup & Graph Retrieval
        parts = tool_input.split("|", 1)
        topic = parts[0].strip()
        provided_context = parts[1].strip() if len(parts) > 1 else ""

        # Support hallucinations like topic="..."
        if "=" in topic and (topic.lower().startswith("topic=") or topic.lower().startswith("subject=")):
            topic = topic.split("=", 1)[-1].strip()
        topic = topic.strip("'").strip('"').strip("`")

        store = KnowledgeStore(agent_id)
        store.load()
        
        # Get the "Map of Facts" instead of relying on memory. If topic is not found, get all or rely on provided context.
        graph_data = store.get_full_report_context(topic)

        # If graph_data is empty and we have provided_context, we can inject it into graph_data or prompt
        if not graph_data.get("facts") and not graph_data.get("sources"):
            graph_data = {"provided_context": provided_context}
        elif provided_context:
            graph_data["provided_context"] = provided_context
        
        # 2. Craft the 'Senior Analyst' Prompt
        prompt = f"""# ROLE: SENIOR STRATEGIC ANALYST ($500/hr Consultant)
        TASK: Synthesize a high-stakes, comprehensive research report from the provided data.
        
        TOPIC: {topic}
        
        # RESEARCH DATA (The Knowledge Graph & Deep Context):
        {json.dumps(graph_data, indent=2)}
        
        # STRICT ANTI-LAZINESS PROTOCOL:
        1. NO FLUFF: Skip "As an AI..." or "In conclusion...". Start with the data immediately.
        2. EXTREME DEPTH IS MANDATORY: This must be a master-class research report. Each section MUST be at least 5-6 dense, information-rich paragraphs.
        3. EVIDENCE-DRIVEN: For Every. Single. Claim. you make, you MUST weave in the specific 'context_or_evidence' provided in the facts. (e.g., "Market growth is projected at 20%, driven by [Methodology/Evidence From Graph]"). 
        4. CITATIONS: Use numbered citations like [1], [2], [3] for EVERY technical claim or data point. These numbers must correspond to the sources list provided.
        5. EXPLOIT ALL SOURCES: You are provided with a large list of sources. You MUST attempt to reference as many unique sources as possible throughout the report to maximize authority.
        6. ANALYTICAL RIGOR: Connect facts across sources, identify strategic tensions, analyze second-order effects, and project 5-10 year implications based on the data.
        7. TABLES: If the graph contains 'tables', you MUST format them as Markdown tables within relevant sections. Use the provided data to build custom comparison tables.
        
        # STRICT REPORT STRUCTURE:
        1. Title: A formal, impactful, and descriptive title.
        2. Executive Summary: 3-4 powerful paragraphs summarizing core discoveries, strategic headwinds, and actionable takeaways.
        3. Deep-Dive Sections: At least 6-8 comprehensive sections covering technical evolution, market impacts, strategic pivots, competitive landscape, and future projections.
           - Each section must have a clear, descriptive 'title'.
           - Every section must have at least 500 words of analysis.
        4. Sources: Extract ALL URLs and titles found in the graph data provided into the separate JSON list.
        
        # OUTPUT FORMAT:
        The output MUST be a PURE JSON object (no markdown code blocks) with this structure:
        {{
          "title": "...",
          "summary": "...",
          "sections": [
            {{ "title": "Section Title", "content": "Full section markdown text here..." }}
          ],
          "sources": [
            {{ "title": "...", "url": "..." }}
          ]
        }}
        
        Return ONLY the JSON. Verify it is valid JSON with escaped newlines and quotes.
        """

        # 3. Use Gemini 3.1 Pro for the final heavy lifting
        model = PLANNER_MODEL
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2}
        }
        
        async with httpx.AsyncClient() as client:
            # Increase timeout to 300s for long comprehensive reports
            response = await client.post(url, headers=headers, json=data, timeout=300)
            if response.status_code != 200:
                safe_log(f"!!! [CAPABILITY:report_generation] LLM API Error: {response.status_code} - {response.text}")
                return f"Synthesis failed: API Error {response.status_code}"
            
            res_json = response.json()
            candidates = res_json.get("candidates", [])
            if not candidates:
                safe_log(f"!!! [CAPABILITY:report_generation] No candidates in response: {res_json}")
                return f"Synthesis failed: No response from model."
            
            report_data_json = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            # Remove markdown backticks if Gemini added them
            report_data_json = re.sub(r'```json\s*|\s*```', '', report_data_json).strip()

            # Attempt to parse
            try:
                report_data = json.loads(report_data_json)
            except json.JSONDecodeError as e:
                safe_log(f"!!! [CAPABILITY:report_generation] JSON parse error: {e}")
                # Try repair
                report_data_json_rep = report_data_json.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                try:
                    report_data = json.loads(report_data_json_rep)
                except:
                    return f"Synthesis failed: Output was not valid JSON."
        
        # 4. PDF Generation Phase
        display_title = report_data.get("title", topic)
        clean_title_for_file = re.sub(r'[^a-zA-Z0-9\s_-]', '', display_title[:50].strip().replace('"', ''))
        safe_filename = f"Report_{clean_title_for_file.replace(' ', '_')}.pdf"
        report_path = os.path.join(working_dir, safe_filename)

        try:
            pdf_gen = ReportPDFGenerator(report_path, display_title)
            pdf_gen.generate(report_data, agent_name=agent_name, agent_id=agent_id)
            safe_log(f"+++ [CAPABILITY:report_generation] Saved PDF to: {report_path}", agent_id=agent_id)
            return f"Report generated: {safe_filename}. (Saved in {working_dir})"
        except Exception as pdf_err:
            safe_log(f"!!! [CAPABILITY:report_generation] PDF Gen Error: {pdf_err}")
            return f"Failed to generate PDF: {str(pdf_err)}"

    except Exception as e:
        safe_log(f"!!! [CAPABILITY:report_generation] Overall Error: {e}", agent_id=agent_id)
        return f"Failed to generate report: {str(e)}"

# ─────────────────────────────────────────────────
# AGENT-TO-AGENT COMMUNICATION CAPABILITY
# ─────────────────────────────────────────────────

async def message_agent(target_id, message, sender_id, sender_name, api_key, target_provider, context_snippet="", intent_priority="NORMAL"):
    """
    Sends a structured, context-rich message to a connected agent.
    """
    safe_log(f"[STATUS:{sender_id}] Messenger: Sending to '{target_id}' (Priority: {intent_priority})", agent_id=sender_id)

    # Build a rich, context-aware message envelope
    separator = "─" * 50
    payload_parts = [
        "[MESSAGE FROM ANOTHER AGENT]",
        f"Sender:   {sender_name} (ID: {sender_id})",
        f"Priority: {intent_priority}",
        separator,
        "## Task / Request",
        message.strip(),
    ]

    if context_snippet:
        payload_parts += [
            separator,
            "## Context (Recent conversation from sender — read this to understand the full situation)",
            context_snippet,
        ]

    payload_parts.append(separator)
    payload_content = "\n".join(payload_parts)

    url = "http://127.0.0.1:8000/chat"
    data = {
        "agent_id": target_id,
        "message": payload_content,
        "api_key": api_key,
        "provider": target_provider
    }

    try:
        async with httpx.AsyncClient() as client:
            # We must stream the response because /chat returns SSE
            final_target_text = ""
            async with client.stream("POST", url, json=data, timeout=120) as r:
                if r.status_code != 200:
                    return f"Failed to message agent {target_id}. HTTP {r.status_code}"
                
                async for line in r.aiter_lines():
                    line = line.strip()
                    if line.startswith("data: "):
                        content_str = line[6:]
                        if content_str == "[DONE]": continue
                        try:
                            chunk = json.loads(content_str)
                            if chunk.get("type") == "text":
                                final_target_text += chunk.get("content", "")
                            elif chunk.get("type") == "error":
                                return f"Error from {target_id}: {chunk.get('content')}"
                        except: pass
            
            target_response = final_target_text.strip()
            
            # Evaluate whether the agent actually executed the task or just stated intent.
            intent_markers = ["i will ", "i'll ", "i would ", "i plan to ", "i am going to ", "i'll start", "i need to "]
            execution_markers = ["result:", "found:", "created:", "generated:", "completed:", "here is", "here are", "report", "error:"]
            response_lower = target_response.lower().strip()
            has_intent = any(m in response_lower for m in intent_markers)
            has_execution = any(m in response_lower for m in execution_markers)

            if has_intent and not has_execution:
                instruction = (
                    "EVALUATION — TASK NOT COMPLETED: The receiving agent stated intent but did NOT execute the task "
                    "(no tool results or concrete output present). "
                    "You MUST inform the user: \"[AgentName] acknowledged the request but has not produced results. "
                    "They may lack the required permissions or connections to complete the task. "
                    "Check their capability settings or complete the task yourself.\"\n"
                    "Do NOT present this as success."
                )
            else:
                instruction = "INSTRUCTION: The agent produced results. Relay their findings clearly and completely to the user."

            return (f"--- DATA RECEIVED FROM {target_id} ---\n"
                    f"{target_response}\n"
                    f"--- END OF DATA ---\n"
                    f"{instruction}")

    except Exception as e:
        safe_log(f"!!! [CAPABILITY:message_agent] {e}", agent_id=sender_id)
        return f"Failed to message agent {target_id}. Error: {str(e)}"



# ─────────────────────────────────────────────────
# FILE SYSTEM CAPABILITIES
# ─────────────────────────────────────────────────

def _resolve_safe_path(working_dir, file_path):
    """
    Safely resolves a file path against a working directory.
    Returns the absolute path if safe, or raises ValueError if it attempts path traversal.
    """
    if not working_dir:
        raise ValueError("Agent has no workingDir assigned. File operations are disabled.")
        
    working_dir_abs = os.path.abspath(working_dir)
    target_path_abs = os.path.abspath(os.path.join(working_dir_abs, file_path))
    
    # Check if the target is actually inside the working directory
    if not target_path_abs.startswith(working_dir_abs):
        raise ValueError(f"Path traversal detected. Access denied to '{file_path}'. Agents can only access files within their assigned working directory: {working_dir}")
        
    return target_path_abs

def scout_file(agent_id, file_path, working_dir):
    """Returns metadata about a file within the working directory."""
    safe_log(f"[STATUS:{agent_id}] FS: Scouting '{file_path}'", agent_id=agent_id)
    try:
        safe_path = _resolve_safe_path(working_dir, file_path)
        if not os.path.exists(safe_path):
            return f"Error: File '{file_path}' does not exist in your working directory."
            
        if os.path.isdir(safe_path):
            contents = os.listdir(safe_path)[:50]
            trunc = "..." if len(os.listdir(safe_path)) > 50 else ""
            return f"'{file_path}' is a Directory. Top contents: {', '.join(contents)}{trunc}"
            
        stats = os.stat(safe_path)
        size_bytes = stats.st_size
        
        # Determine basic type and try to count lines if it's text
        import mimetypes
        mime, _ = mimetypes.guess_type(safe_path)
        file_type = mime or "unknown/binary"
        
        info = f"File: {file_path}\nAbsolute Path: {safe_path}\nSize: {size_bytes} bytes\nType: {file_type}\n"
        
        # If it looks like text, count lines
        if "text" in file_type or file_path.endswith((".py", ".js", ".md", ".json", ".log", ".txt", ".csv", ".xml")):
            try:
                with open(safe_path, 'r', encoding='utf-8') as f:
                    lines = sum(1 for _ in f)
                info += f"Line Count: {lines}\n"
                info += "Note: You can use [TOOL: read_file(path|start_line-end_line)] to read specific chunks if the file is large."
            except UnicodeDecodeError:
                info += "Note: File appears to be text based on extension, but could not decode as UTF-8.\n"
                
        return info
        
    except ValueError as e:
        return str(e)
    except Exception as e:
        return f"Error scouting file: {e}"

def read_file(agent_id, input_str, working_dir):
    """
    Reads a file or a subset of lines. Input format: file_path OR file_path|start-end
    """
    safe_log(f"[STATUS:{agent_id}] FS: Reading '{input_str[:40]}...'")
    try:
        parts = input_str.split("|", 1)
        file_path = parts[0].strip()
        
        safe_path = _resolve_safe_path(working_dir, file_path)
        if not os.path.exists(safe_path):
            return f"Error: File '{file_path}' does not exist in your working directory."
            
        start_line = 0
        end_line = None
        
        if len(parts) > 1:
            range_str = parts[1].strip()
            if "-" in range_str:
                s, e = range_str.split("-")
                start_line = max(0, int(s.strip()) - 1) # 1-indexed to 0-indexed
                end_line = int(e.strip())

        try:
            with open(safe_path, 'r', encoding='utf-8') as f:
                if end_line is None:
                    content = f.read()
                    if len(content) > 5000:
                        return f"Error: File is too large ({len(content)} chars) to read safely into your context. You MUST use 'make_tool' to write a script that processes this file locally and only prints the results you need."
                    return content
                else:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= start_line and i < end_line:
                            lines.append(f"{i+1}: {line.rstrip()}")
                        if i >= end_line:
                            break
                    return "\n".join(lines)
        except UnicodeDecodeError:
            return "Error: Cannot read binary file or file is not valid UTF-8."
            
    except ValueError as e:
        return str(e)
    except Exception as e:
        return f"Error reading file: {e}"

def write_file(agent_id, input_str, working_dir):
    """
    Writes content to a file. Format: file_path|content
    """
    try:
        parts = input_str.split("|", 1)
        if len(parts) != 2:
            return "Error: write_file input must be in the format 'file_path|content'"
            
        file_path = parts[0].strip()
        content = parts[1]
        
        safe_log(f"[STATUS:{agent_id}] FS: Writing to '{file_path}'")
        
        safe_path = _resolve_safe_path(working_dir, file_path)
        
        # Create directories if they don't exist
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return f"Successfully wrote {len(content)} characters to '{file_path}'."
        
    except ValueError as e:
        return str(e)
    except Exception as e:
        return f"Error writing file: {e}"


# ─────────────────────────────────────────────────
# PLANNING
# ─────────────────────────────────────────────────

async def update_plan(agent_id, tool_input):
    """
    Atomic updates to the agent's committed intentions (BDI).
    Handles format hallucinations (missing '|', newlines instead of commas).
    """
    try:
        # CHANGE 1: Use plan.json instead of intentions.json
        plan_path = os.path.join(os.path.dirname(__file__), "agents_code", agent_id, "plan.json")
        os.makedirs(os.path.dirname(plan_path), exist_ok=True)
        
        plan = {"objective": "Not Set", "steps": [], "completed": []}
        if os.path.exists(plan_path):
            try:
                with open(plan_path, "r", encoding="utf-8") as f:
                    plan = json.load(f)
            except: pass

        tool_input = tool_input.strip()

        if "|" in tool_input:
            obj, steps_str = tool_input.split("|", 1)
            plan["objective"] = obj.strip()
            # Handle newlines OR commas
            raw_steps = steps_str.split("\n") if "\n" in steps_str else steps_str.split(",")
            plan["steps"] = [re.sub(r'^\d+[\.\)]\s*', '', s.strip()) for s in raw_steps if s.strip()]
            plan["completed"] = []
        else:
            if "completed" in tool_input.lower() and len(tool_input) < 50:
                plan["completed"].append("Task Completed")
            else:
                # LLM forgot the '|' and just passed newlines
                if "\n" in tool_input:
                    raw_steps = tool_input.split("\n")
                    plan["objective"] = raw_steps[0].strip()
                    plan["steps"] = [re.sub(r'^\d+[\.\)]\s*', '', s.strip()) for s in raw_steps[1:] if s.strip()]
                    if not plan["steps"]:
                        plan["steps"] = [plan["objective"]]
                    plan["completed"] = []
                else:
                    plan["objective"] = tool_input
                    plan["steps"] = [tool_input]
                    plan["completed"] = []

        # CHANGE 2: Save back to plan.json
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
            
        steps_md = "\n".join([f"{i+1}. {s}" for i, s in enumerate(plan['steps'])])
        return f"Objective: {plan['objective']}\n\n{steps_md}"
    except Exception as e:
        return f"Error updating plan: {e}"

async def ask_user(agent_id, tool_input):
    """
    Halts the autonomous loop and asks the user for steering/direction.
    """
    question = tool_input.strip()
    safe_log(f"[STATUS:{agent_id}] Halting to ask user: {question[:40]}...")
    return f"HALT_AND_ASK|{question}"


# ─────────────────────────────────────────────────
# DEEP WEB RESEARCH CAPABILITIES
# ─────────────────────────────────────────────────

# --- Research Config ---
RESEARCH_PROFILES = {
    "small":  {"total_sources": 10,  "thinking_steps": 5},
    "medium": {"total_sources": 40,  "thinking_steps": 15},
    "large":  {"total_sources": 100, "thinking_steps": 30},
}

def get_research_config(project_size: str, human_effort: int) -> dict:
    """
    Calculate burst parameters from project size and human effort slider.
    Returns: {total_sources, thinking_steps, burst_size}

    burst_size = ceil(total_sources / human_effort)
    """
    import math
    profile = RESEARCH_PROFILES.get(project_size, RESEARCH_PROFILES["small"])
    h = max(1, min(10, human_effort))  # clamp 1-10
    burst_size = math.ceil(profile["total_sources"] / h)
    return {
        "total_sources": profile["total_sources"],
        "thinking_steps": profile["thinking_steps"],
        "burst_size": burst_size,
        "human_effort": h,
    }


# --- Website Scraping ---

def extract_svo_triples(text):
    """Robustly extracts Facts using Linguistic Dependency Parsing."""
    if not nlp: return []
    doc = nlp(text)
    triples = []
    for sent in doc.sents:
        # Check for Subject-Verb-Object structure
        subjects = [t.text for t in sent if "subj" in t.dep_]
        verbs = [t.text for t in sent if t.pos_ == "VERB"]
        objs = [t.text for t in sent if "obj" in t.dep_]
        
        # If it's a complete thought with a data point (Date/Money), it's a Fact
        has_data = any(ent.label_ in ["DATE", "MONEY", "PERCENT"] for ent in sent.ents)
        
        if (subjects and verbs and objs) or (subjects and has_data):
            triples.append({
                "fact": sent.text.strip(),
                "entities": [(ent.text, ent.label_) for ent in sent.ents]
            })
    return triples

async def scrape_website(url, agent_id):
    """The robust orchestrator for local GraphRAG ingestion."""
    safe_log(f"[STATUS:{agent_id}] Deep Extraction: {url[:60]}...", agent_id=agent_id)
    url = url.strip().strip("'\"`")
    if not url.startswith("http"): url = "https://" + url

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    # 1. First Attempt: Rapid Jina Reader (Great for simple sites & avoiding JS overhead)
    jina_url = f"https://r.jina.ai/{url}"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            res = await client.get(jina_url)
            if res.status_code == 200 and len(res.text) > 500:
                safe_log(f"+++ [SCRAPE:{agent_id}] Jina Reader succeeded", agent_id=agent_id)
                main_text = res.text
                metadata_title = f"Jina Extraction: {url}"
                metadata_date = None
                tables = []
            else:
                raise Exception("Jina returned empty/invalid response")
    except Exception as e:
        safe_log(f"--- [SCRAPE:{agent_id}] Jina Reader failed ({e}), failing over to Crawl4AI", agent_id=agent_id)
        
        # 2. Fallback: Full stealth Crawl4AI (Bypasses Cloudflare, loads JS)
        try:
            from crawl4ai import AsyncWebCrawler
            from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
            from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

            browser_config = BrowserConfig(
                headless=True,
                verbose=False,
                extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"]
            )
            run_config = CrawlerRunConfig(
                markdown_generator=DefaultMarkdownGenerator()
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=url, config=run_config)
                
                if not result.success:
                    return f"Error: Crawl4AI failed to access {url}"
                
                main_text = result.markdown
                metadata_title = result.metadata.get("title", f"Crawl4AI: {url}") if result.metadata else f"Crawl4AI: {url}"
                metadata_date = None
                tables = []
                safe_log(f"+++ [SCRAPE:{agent_id}] Crawl4AI succeeded", agent_id=agent_id)
                
        except Exception as e2:
            safe_log(f"!!! [SCRAPE:{agent_id}] Both Jina AND Crawl4AI failed: {e2}", agent_id=agent_id)
            return f"Error: All scraping attempts failed for {url}. Reason: {str(e2)}"

    try:
        # 3. Knowledge Graph Injection
        store = KnowledgeStore(agent_id)
        store.load()
        sid = store.add_source(
            url=url, 
            title=metadata_title, 
            snippet=main_text[:300] if main_text else "No content",
            full_text=main_text if main_text else "", 
            metadata={"tables": tables, "date": metadata_date}
        )

        # 4. SVO Fact & Entity Linking
        if main_text:
            facts = extract_svo_triples(main_text[:10000]) # Process first 10k chars
            for f in facts:
                e_ids = []
                for name, cat in f["entities"]:
                    e_ids.append(store.add_entity_node(name, cat, sid))
                store.add_fact_node(f["fact"], sid, e_ids)

            store.save()
            return f"SOURCE: {url}\n\nSuccessfully mapped {len(facts)} facts to graph.\n\n{main_text[:2000]}..."
        
        return f"SOURCE: {url}\n\nScraped successfully but no main text found."

    except Exception as graph_err:
        safe_log(f"!!! [SCRAPE:{agent_id}] Graph injection error: {graph_err}", agent_id=agent_id)
        return f"Error mapping {url} to Knowledge Graph: {str(graph_err)}"




# --- Human Steering Check ---

async def generate_human_steering_check(ledger_json, user_steer_history, agent_id, api_key):
    """
    Uses a fast model to analyze current research findings, identify gaps,
    and generate a focused steering question for the human operator.

    This saves high-reasoning tokens for the final report by using
    Gemini 2 Flash for the meta-analysis.
    """
    safe_log(f"[STATUS:{agent_id}] Generating steering checkpoint...", agent_id=agent_id)

    steer_context = ""
    if user_steer_history:
        steer_context = f"\n\nPREVIOUS USER STEERS:\n{user_steer_history}"

    prompt = f"""You are an editorial assistant reviewing an AI researcher's progress.

RESEARCH FINDINGS SO FAR:
{ledger_json[:4000]}
{steer_context}

YOUR JOB:
1. Identify the ONE most critical gap or ambiguity in the current research.
2. Suggest 2-3 specific directions the research could go next.
3. Ask a single, precise question that will maximally steer the next research burst.

FORMAT YOUR RESPONSE AS:
**Knowledge Map**: [2-3 sentence summary of what has been found so far]
**Gap Identified**: [The one thing that is missing or unclear]
**Suggested Directions**:
- [Direction A]
- [Direction B]
- [Direction C]
**Steering Question**: [Your single precise question to the human]

Be concise. No fluff."""

    model = FAST_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500}
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=data, timeout=30)
            if response.status_code != 200:
                return f"Steering check failed: {response.text[:200]}"

            res_json = response.json()
            candidates = res_json.get("candidates", [])
            if not candidates:
                return "Steering check failed: no response from model."

            result = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            safe_log(f"+++ [STEERING] Generated check ({len(result)} chars)", agent_id=agent_id)
            return result

    except Exception as e:
        safe_log(f"!!! [STEERING] Error: {e}", agent_id=agent_id)
        return f"Steering check error: {str(e)[:150]}"


async def query_graph(entity_query, agent_id):
    """
    Search the knowledge graph for a specific entity to find connections
    between different articles, including tables and dates.
    """
    store = KnowledgeStore(agent_id)
    store.load()
    
    result = store.get_entity_connections(entity_query)
    if "error" in result:
        return result["error"]

    # Format the 'hop' results for the LLM
    output = [f"### Connections for Entity: {result['entity']} ({result['category']})"]
    for m in result["mentions"]:
        output.append(f"- **Source**: {m['title']} ({m['url']})")
        output.append(f"  **Date**: {m['date']}")
        if m["tables"]:
            output.append(f"  **Data Tables**: {len(m['tables'])} found.")
            for i, tbl in enumerate(m["tables"]):
                output.append(f"  [Table {i+1}]: {tbl}")
    
    return "\n".join(output)


def extract_rich_metadata(html_content, url):
    """Local, no-LLM extraction of facts, tables, and entities."""
    # 1. Extract Main Text and Metadata using Trafilatura
    downloaded = trafilatura.extract(html_content, include_comments=False, 
                                    include_tables=True, output_format='markdown')
    metadata = trafilatura.metadata.extract_metadata(html_content)
    
    # 2. Extract Tables specifically with BeautifulSoup for Markdown conversion
    soup = BeautifulSoup(html_content, 'html.parser')
    tables = []
    for table in soup.find_all('table'):
        # Just store the raw table text or a simple Markdown representation
        tables.append(str(table.get_text(separator=" | ")).strip())

    # 3. Local Named Entity Recognition (NER)
    entities = []
    if nlp and downloaded:
        doc = nlp(downloaded[:10000]) # Process first 10k chars for speed
        # Find people, orgs, and dates to use as "Hopping Points"
        entities = [{"text": ent.text, "label": ent.label_} 
                    for ent in doc.ents if ent.label_ in ["PERSON", "ORG", "GPE", "DATE", "MONEY"]]

    return {
        "text": downloaded,
        "date": metadata.date if metadata else None,
        "title": metadata.title if metadata else "Unknown",
        "tables": tables,
        "entities": entities,
        "url": url
    }
