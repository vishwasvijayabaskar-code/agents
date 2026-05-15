"""Agent-to-agent delegation (Tier 8D).

Allows worker nodes to delegate subtasks to other agents mid-execution.
Example: CODER output contains <delegate agent="RESEARCHER">look up API docs for X</delegate>
Post-processor detects the tag, runs the delegated task, injects result back.

Max 1 delegation per agent per task to prevent infinite loops.
"""
import re
from typing import Callable

# Pattern: <delegate agent="AGENT_NAME">query text</delegate>
_DELEGATE_PATTERN = re.compile(
    r'<delegate\s+agent="(\w+)">(.*?)</delegate>',
    re.DOTALL | re.IGNORECASE,
)


def parse_delegation(output: str) -> tuple[str, str] | None:
    """Extract first delegation tag from agent output.
    Returns (agent_name, query) or None."""
    match = _DELEGATE_PATTERN.search(output)
    if match:
        agent = match.group(1).upper()
        query = match.group(2).strip()
        if agent and query:
            return (agent, query)
    return None


def strip_delegation_tags(output: str) -> str:
    """Remove delegation tags from output text."""
    return _DELEGATE_PATTERN.sub("", output).strip()


def execute_delegation(
    agent_name: str,
    query: str,
    node_fn: Callable,
    state: dict,
) -> str:
    """Run a delegated task using the target agent's node function.
    Returns the delegated agent's output."""
    # Build a minimal sub-state for the delegated task
    sub_state = {
        "task": query,
        "route": None,
        "result": None,
        "history": [],
        "iterations": 0,
        "done": False,
        "agent_outputs": {},
        "output_dir": state.get("output_dir"),
        "memory": [],
        "session_history": [],
        "project_context": state.get("project_context"),
        "force_route": None,
        "chat_messages": [],
        "fanout_tasks": None,
        "tokens_used": 0,
        "subtasks": None,
        "current_subtask": 0,
    }

    result_state = node_fn(sub_state)
    return result_state.get("result") or ""
