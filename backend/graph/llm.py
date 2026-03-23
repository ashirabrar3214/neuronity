import os
from langchain_google_genai import ChatGoogleGenerativeAI

FAST_MODEL = os.getenv("FAST_MODEL", "gemini-2.0-flash")
REASONING_MODEL = os.getenv("REASONING_MODEL", "gemini-2.0-flash")


def get_llm(mode: str = "fast", api_key: str = "", streaming: bool = True):
    """Return a ChatGoogleGenerativeAI instance.

    mode: "fast" for execution turns, "think" for plan generation / reasoning
    """
    key = api_key or os.getenv("GEMINI_API_KEY", "")
    model = REASONING_MODEL if mode == "think" else FAST_MODEL

    kwargs = dict(
        model=model,
        google_api_key=key,
        temperature=0.3 if mode == "fast" else 0.2,
        max_output_tokens=8192,
        streaming=streaming,
    )

    return ChatGoogleGenerativeAI(**kwargs)
