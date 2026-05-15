from typing import TypedDict, Optional

class AgentState(TypedDict):
    task: str
    route: Optional[str]
    result: Optional[str]
    history: list[str]
    iterations: int
    done: bool
    agent_outputs: dict[str, str]
    output_dir: Optional[str]
    memory: list[dict]
    session_history: list[dict]
    project_context: Optional[str]
    force_route: Optional[str]
    chat_messages: list[dict]
    fanout_tasks: Optional[dict]
    tokens_used: int
    subtasks: Optional[list[dict]]
    current_subtask: int
