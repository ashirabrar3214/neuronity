import os
from langgraph.checkpoint.memory import MemorySaver

# Use in-memory checkpointer for simplicity.
# Each agent conversation is keyed by thread_id = agent_id.
_checkpointer = None


def get_checkpointer():
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = MemorySaver()
    return _checkpointer
