import os
from langchain_google_genai import ChatGoogleGenerativeAI

FAST_MODEL = os.getenv("FAST_MODEL", "gemini-2.0-flash")
REASONING_MODEL = os.getenv("REASONING_MODEL", "gemini-2.0-flash")
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "gemini-3.1-pro-preview")


def get_llm(mode: str = "fast", api_key: str = "", streaming: bool = True):
    """Return a ChatGoogleGenerativeAI instance.

    mode:
      "fast"    — gemini-2.0-flash, for execution and compression
      "think"   — REASONING_MODEL, legacy
      "planner" — gemini-3.1-pro-preview, for ReAct planning node
    """
    key = api_key or os.getenv("GEMINI_API_KEY", "")

    if mode == "planner":
        model = PLANNER_MODEL
        temperature = 0.2
        streaming = False  # planner always non-streaming (structured JSON output)
    elif mode == "think":
        model = REASONING_MODEL
        temperature = 0.2
    else:
        model = FAST_MODEL
        temperature = 0.3

    kwargs = dict(
        model=model,
        google_api_key=key,
        temperature=temperature,
        max_output_tokens=8192,
        streaming=streaming,
    )

    return ChatGoogleGenerativeAI(**kwargs)
