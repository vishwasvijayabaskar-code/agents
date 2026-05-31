from typing import TypedDict


class AgentState(TypedDict):
    task: str
    route: str | None
    result: str | None
    history: list[str]
    iterations: int
    done: bool
    agent_outputs: dict[str, str]
    output_dir: str | None
    memory: list[dict]
    session_history: list[dict]
    project_context: str | None
    force_route: str | None
    chat_messages: list[dict]
    fanout_tasks: dict | None
    tokens_used: int
    subtasks: list[dict] | None
    current_subtask: int
    project_context_path: str | None  # absolute path for CodebaseIndex
