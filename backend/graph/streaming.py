"""
SSE Adapter: Translates LangGraph astream_events into SSE format
matching the frontend's expectations.

Frontend expects events with types:
  thought, text, tool_start, tool_result, status, error, [DONE]
"""
import json
from langchain_core.messages import AIMessage
from graph.tool_definitions import SILENT_TOOLS


async def langgraph_to_sse(graph, input_state: dict, config: dict):
    """Async generator that yields SSE-formatted strings from LangGraph execution.

    Uses astream_events(version="v2") to get fine-grained streaming events
    and translates them to the SSE format the Electron frontend expects.
    """
    try:
        async for event in graph.astream_events(input_state, config, version="v2"):
            kind = event["event"]

            # --- Deliberation thought (from custom graph node) ---
            if kind == "on_chain_end" and event.get("name") == "deliberate":
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict):
                    decision = output.get("decision", "")
                    reason = output.get("decision_reason", "")
                    if decision:
                        yield _sse({"type": "thought", "content": f"Deliberation: {decision} ({reason})"})

            # --- Respond node output (for CLARIFY/RE-PLAN paths that skip LLM) ---
            elif kind == "on_chain_end" and event.get("name") == "respond":
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict):
                    messages = output.get("messages", [])
                    for msg in messages:
                        if isinstance(msg, AIMessage) and msg.content:
                            yield _sse({"type": "text", "content": msg.content})

            # --- LLM streaming text ---
            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    # Only yield text content, skip tool call chunks
                    if not (hasattr(chunk, "tool_calls") and chunk.tool_calls):
                        yield _sse({"type": "text", "content": chunk.content})

            # --- Tool execution start ---
            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                yield _sse({"type": "tool_start", "content": tool_name})
                status_msg = "Action: " + tool_name.replace("_", " ").title()
                yield _sse({"type": "status", "content": status_msg})

            # --- Tool execution end ---
            elif kind == "on_tool_end":
                tool_name = event.get("name", "")
                result = str(event.get("data", {}).get("output", ""))
                # Silent tools: don't stream result to UI
                if tool_name not in SILENT_TOOLS:
                    yield _sse({"type": "tool_result", "content": result})

    except Exception as e:
        yield _sse({"type": "error", "content": str(e)})

    yield "data: [DONE]\n\n"


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"
