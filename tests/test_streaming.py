"""Streaming-contract tests (Task 18).

User-facing worker output must go through _call_stream (live tokens in TUI +
web SSE), not the silent _call. These tests lock that in to prevent regression.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.conftest import make_state


class TestStreamingContract:
    def test_researcher_streams_output(self):
        from nodes.researcher import researcher
        state = make_state(task="research async patterns")
        with patch("nodes.researcher._search", return_value=[]), \
             patch("nodes.researcher._format_search_results", return_value="no results"), \
             patch("nodes.researcher._call_stream", return_value="findings") as mock_stream:
            researcher(state)
        mock_stream.assert_called_once()
        assert state["agent_outputs"]["RESEARCHER"] == "findings"

    def test_codebase_agent_streams_output(self):
        from nodes.codebase_agent import codebase_agent
        state = make_state(task="how does auth work")
        with patch("nodes.codebase_agent._call_stream", return_value="auth uses JWT") as mock_stream:
            codebase_agent(state)
        mock_stream.assert_called_once()
        assert state["agent_outputs"]["CODEBASE"] == "auth uses JWT"

    def test_coder_streams_output(self):
        from nodes.coder import coder
        state = make_state(task="write hello world")
        with patch("nodes.coder._call_stream", return_value="print('hi')") as mock_stream:
            coder(state)
        mock_stream.assert_called_once()

    def test_fast_streams_output(self):
        from nodes.fast import fast
        state = make_state(task="what is 2+2")
        with patch("nodes.fast._call_stream", return_value="4") as mock_stream:
            fast(state)
        mock_stream.assert_called_once()

    def test_claude_api_fallback_streams(self):
        """The Anthropic API fallback path must use streaming (messages.stream)."""
        import importlib
        import inspect

        # import_module returns the submodule (not the re-exported claude fn from nodes/__init__)
        claude_mod = importlib.import_module("nodes.claude")
        src = inspect.getsource(claude_mod)
        # The API fallback should use the streaming context manager, not a blocking create()
        assert "messages.stream" in src
