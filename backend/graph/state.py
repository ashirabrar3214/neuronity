from typing import TypedDict, Annotated, Literal
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """State for the single-agent reasoning graph."""

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

    # Deliberation result
    decision: str  # "SOLVE", "CLARIFY", "RE-PLAN", or ""
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
