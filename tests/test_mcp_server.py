"""Regression tests for mcp_server (mypy surfaced an import-time crash)."""
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_mcp_server_imports():
    """mcp_server must import without crashing.

    Regression: FastMCP was called with an unsupported `version=` kwarg,
    raising TypeError at import and breaking the entire MCP server.
    """
    mod = importlib.import_module("mcp_server")
    assert hasattr(mod, "mcp")


def test_search_memory_uses_correct_kwarg():
    """search_memory must call _relevant_memory with `k`, not `n_results`.

    Regression: it passed n_results= which _relevant_memory(task, k=5)
    does not accept — a guaranteed TypeError at call time.
    """
    import inspect

    import mcp_server

    src = inspect.getsource(mcp_server)
    assert "n_results=" not in src
