"""Shared fixtures for all tests. No Ollama required — all LLM calls mocked."""
import sys
import os
from pathlib import Path

# Ensure agents/ root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


def make_state(**overrides) -> dict:
    """Return a minimal valid AgentState dict."""
    base = {
        "task": "test task",
        "route": None,
        "result": None,
        "history": [],
        "iterations": 0,
        "done": False,
        "agent_outputs": {},
        "output_dir": "/tmp/test_output",
        "memory": [],
        "session_history": [],
        "project_context": None,
        "force_route": None,
        "chat_messages": [],
        "fanout_tasks": None,
        "tokens_used": 0,
        "subtasks": None,
        "current_subtask": 0,
    }
    base.update(overrides)
    return base
