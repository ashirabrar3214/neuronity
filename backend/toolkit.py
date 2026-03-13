import time
import os
import random
import json
import requests

# ─────────────────────────────────────────────────
# WEB SEARCH CAPABILITY
# ─────────────────────────────────────────────────

import sys
import io

def safe_log(message):
    """Prints a message safely, handling potential Unicode encoding issues on Windows consoles."""
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        try:
            print(message.encode('ascii', 'replace').decode('ascii'), flush=True)
        except:
            pass
    except Exception:
        pass

def web_search(query, agent_id):
    """
    Fetches up to 15 DuckDuckGo results for the query.
    Returns a list[dict] with keys: title, href, body.
    """
    safe_log(f"[STATUS:{agent_id}] Searching Web")
    
    try:
        from ddgs import DDGS
        
        results = []
        for result in DDGS().text(query, max_results=15):
            results.append({
                "title": result.get("title", ""),
                "href": result.get("href", ""),
                "body": result.get("body", "")
            })
        
        safe_log(f"+++ [CAPABILITY:web_search] Got {len(results)} results for '{query}'")
        return results
    
    except Exception as e:
        safe_log(f"!!! [CAPABILITY:web_search] Error: {e}")
        return [{"title": "Search Error", "href": "", "body": f"Could not fetch results: {str(e)}"}]


def filter_sources(query, search_results, api_key):
    """
    Asks Gemini to pick only the most relevant sources from the full result set.
    Returns a filtered list[dict] (subset of search_results).
    """
    safe_log(f"[STATUS] Filtering sources")
    
    if not search_results or not api_key:
        return search_results
    
    # Build a numbered index for Gemini to reference
    index_lines = []
    for i, r in enumerate(search_results):
        index_lines.append(f"{i}: [{r['title']}] — {r['body'][:200]}")
    index_text = "\n".join(index_lines)
    
    filter_prompt = f"""You are a research librarian. Given the query and a list of search results, select only the most relevant and authoritative sources.

QUERY: {query}

SEARCH RESULTS:
{index_text}

Respond with ONLY a JSON array of the index numbers to keep. Example: [0, 2, 5, 8]
Select between 3 and 8 sources. Prioritize: relevance, authority (Wikipedia, major news, official sites), and recency.
"""
    
    model = "gemini-2.0-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    data = {
        "contents": [{"role": "user", "parts": [{"text": filter_prompt}]}],
        "generationConfig": {"temperature": 0.1}  # Low temperature for consistent JSON output
    }
    
    try:
        response = requests.post(url, headers={"Content-Type": "application/json"}, json=data, timeout=15)
        if response.status_code == 200:
            raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            # Extract the JSON array from the response
            import re
            match = re.search(r'\[([\d,\s]+)\]', raw)
            if match:
                indices = json.loads(match.group(0))
                filtered = [search_results[i] for i in indices if 0 <= i < len(search_results)]
                safe_log(f"+++ [CAPABILITY:filter] Kept {len(filtered)}/{len(search_results)} sources")
                return filtered if filtered else search_results
    except Exception as e:
        safe_log(f"!!! [CAPABILITY:filter] Error: {e} — using all results")
    
    # Fallback: return all results if filtering fails
    return search_results



def synthesize_with_gemini(query, search_results, api_key):
    """
    Function 2: Feed raw search results JSON to Gemini, get a clean synthesis.
    Always appends a ### Sources section built directly from the raw results.
    """
    safe_log(f"[STATUS] Synthesizing results with Gemini")
    
    raw_context = "\n\n".join([
        f"Source: {r['title']}\nURL: {r['href']}\nContent: {r['body']}"
        for r in search_results
    ])
    
    synthesis_prompt = f"""You are an expert research assistant. Analyze the search results below to fulfill the USER'S REQUEST.

USER'S ORIGINAL REQUEST: {query}

SEARCH RESULTS FOUND:
{raw_context}

STRICT RULES:
1. If the user provided a specific format (e.g., 'top 3 snippets'), follow it EXACTLY.
2. If no specific format is requested, provide a **Comprehensive Research Report**:
   - Start with a clear, descriptive title.
   - Provide a 1-2 paragraph executive summary.
   - Use 'Key Findings' sections with descriptive subheadings.
   - **MANDATORY**: For every major claim or piece of news, cite the source and INCLUDE its URL in the text.
   - Ensure the report is detailed and informative, covering multiple perspectives if present in the data.
3. Use the CURRENT_DATE provided in the system prompt for context.
4. Do NOT include 'Thoughts', 'Thinking', or any conversational preamble. Just the report content.
"""
    
    model = "gemini-2.0-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"role": "user", "parts": [{"text": synthesis_prompt}]}],
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=20)
        if response.status_code == 200:
            gemini_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        else:
            print(f"!!! [CAPABILITY:synthesize] Gemini error {response.status_code}: {response.text}", flush=True)
            gemini_text = f"Search found results but synthesis failed.\n\n{raw_context}"
    except Exception as e:
        safe_log(f"!!! [CAPABILITY:synthesize] Exception: {e}")
        gemini_text = f"Search found results but could not synthesize: {str(e)}"

    # --- Always append Sources section directly from raw results (never trust LLM for URLs) ---
    sources_lines = ["### Sources\n"]
    for r in search_results:
        title = r.get("title", "Untitled")
        url_link = r.get("href", "")
        if url_link:
            sources_lines.append(f"- [{title}]({url_link})")
    
    sources_section = "\n".join(sources_lines)
    return f"{gemini_text.strip()}\n\n{sources_section}"


# ─────────────────────────────────────────────────
# THINKING CAPABILITY
# ─────────────────────────────────────────────────

def thinking(agent_id, topic):
    """
    Simulates a deep thinking process for a specific topic.
    """
    safe_log(f"[STATUS:{agent_id}] Thinking")
    time.sleep(3)
    return f"Thinking complete on '{topic}'. Ready to respond with deeper analysis."


# ─────────────────────────────────────────────────
# REPORT GENERATION CAPABILITY
# ─────────────────────────────────────────────────

def generate_report(agent_id, tool_input, agent_dir):
    """
    Generates a structured markdown report file in the agent's directory.
    Usage: [TOOL: generate_report(Title|Content)]
    """
    safe_log(f"[STATUS:{agent_id}] Generating Report")
    time.sleep(1)
    try:
        if "|" in tool_input:
            title, content = tool_input.split("|", 1)
        else:
            title = "Report_" + str(int(time.time()))
            content = tool_input
        
        filename = f"{title.strip().replace(' ', '_')}.md"
        report_path = os.path.join(agent_dir, filename)
        
        full_report = f"""# Agent Report: {title.strip()}
Generated by: {agent_id}
Date: {time.strftime("%Y-%m-%d %H:%M:%S")}

---

## Summary
{content.strip()}

---
*End of Report*"""

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(full_report)
            
        safe_log(f"+++ [CAPABILITY:generate_report] Saved to: {report_path}")
        return f"Report successfully generated: {filename}"
        
    except Exception as e:
        safe_log(f"!!! [CAPABILITY:generate_report] {str(e)}")
        return f"Error generating report: {str(e)}"

# ─────────────────────────────────────────────────
# AGENT-TO-AGENT COMMUNICATION CAPABILITY
# ─────────────────────────────────────────────────

def message_agent(target_id, message, sender_id, sender_name, api_key, target_provider, context_snippet=""):
    """
    Sends a structured, context-rich message to a connected agent.
    The payload includes:
      - Sender identity (name + ID)
      - The explicit task/request
      - A snippet of the sender's recent conversation history for context
    Runs the HTTP call in a new daemon thread to avoid event-loop deadlocks.
    """
    safe_log(f"[STATUS:{sender_id}] Contacting agent {target_id}...")

    # Build a rich, context-aware message envelope
    separator = "─" * 50
    payload_parts = [
        "[MESSAGE FROM ANOTHER AGENT]",
        f"Sender:   {sender_name} (ID: {sender_id})",
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

    import threading
    result_container = {}
    error_container = {}

    def do_request():
        try:
            resp = requests.post(url, json=data, timeout=120)
            result_container["status"] = resp.status_code
            result_container["body"] = resp.json() if resp.status_code == 200 else resp.text
        except Exception as ex:
            error_container["err"] = str(ex)

    t = threading.Thread(target=do_request, daemon=True)
    t.start()
    t.join(timeout=120)  # wait up to 2 minutes

    if error_container:
        safe_log(f"!!! [CAPABILITY:message_agent] {error_container['err']}")
        return f"Failed to message agent {target_id}. Error: {error_container['err']}"

    if not result_container:
        return f"Timed out waiting for response from agent {target_id}."

    if result_container["status"] == 200:
        body = result_container["body"]
        if isinstance(body, dict) and "error" in body:
            return f"Error from {target_id}: {body['error']}"
        target_response = body.get("response", "") if isinstance(body, dict) else ""
        return f"Response from {target_id}:\n{target_response}"

    err = f"HTTP {result_container['status']}: {result_container['body']}"
    safe_log(f"!!! [CAPABILITY:message_agent] {err}")
    return f"Failed to message agent {target_id}. Error: {err}"



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
    safe_log(f"[STATUS:{agent_id}] Scouting '{file_path}'")
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
    safe_log(f"[STATUS:{agent_id}] Reading '{input_str}'")
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
        
        safe_log(f"[STATUS:{agent_id}] Writing to '{file_path}'")
        
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

