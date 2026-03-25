from typing import TypedDict, Annotated, Literal
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """State for the ReAct-style iterative agent graph."""

    # Core conversation — add_messages appends and deduplicates automatically
    messages: Annotated[list[BaseMessage], add_messages]

    # Agent identity
    agent_id: str
    agent_name: str
    agent_type: Literal["master", "worker"]
    permissions: list[str]
    connected_agents: list[dict]  # [{id, name, responsibility, permissions}]
    working_dir: str
    system_prompt: str

    # Legacy deliberation fields (kept for transition compatibility)
    decision: str
    decision_reason: str

    # Execution control
    mode: Literal["work", "training"]
    is_auto_step: bool
    iteration: int
    max_iterations: int

    # Session
    api_key: str
    session_id: str

    # Training mode extras
    current_prompt_md: str  # Content of prompt.md for training mode

    # ── ReAct loop fields ──────────────────────────────────────────────
    goal: str                        # Original user prompt, captured once
    plan_iterations: int             # Outer loop counter (incremented each plan call)
    max_plan_iterations: int         # Hard cap (default 50)
    current_steps: list              # [{id, description, type, tool_name, tool_args, result}]
    iteration_summaries: list        # ~100-token compressed summary per iteration
    planner_decision: str            # "CONTINUE" | "ASK_USER" | "DONE"
    consecutive_clarifications: int  # ASK_USER counter — force terminate at 3
    planner_response: str            # Final answer text (populated when DONE)
    planner_question: str            # Question for user (populated when ASK_USER)

    # ── HITL engine fields ────────────────────────────────────────────
    hitl_phase: str                  # Current HITL phase (or empty)
    hitl_session_id: str             # Active HITL session ID


class WorkmapState(TypedDict):
    """State for the multi-agent workmap orchestration graph."""

    agent_id: str  # Master agent owning this workmap
    project_id: str
    task: str  # Original user task
    nodes: list[dict]  # Workmap node definitions
    completed_results: dict  # {node_id: result_summary}
    current_node_id: str
    status: str  # "PAUSED", "RUNNING", "COMPLETED"
    api_key: str
    provider: str
    agents_info: str  # Connected agents description string
