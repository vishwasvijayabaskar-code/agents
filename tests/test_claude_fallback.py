"""Tests for CLAUDE node graceful degradation (bug fix)."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from nodes.claude import claude
from tests.conftest import make_state


class TestClaudeFallback:
    def test_cli_failure_falls_back_to_api(self):
        """CLI present but 401s → API fallback used, its result wins."""
        state = make_state(task="architect a system")
        with (
            patch("nodes.claude.shutil.which", return_value="/usr/bin/claude"),
            patch("nodes.claude._claude_cli", return_value=("[Claude CLI error: 401]", False)),
            patch("nodes.claude._claude_api_fallback", return_value="API answer here"),
        ):
            result = claude(state)
        assert result["agent_outputs"]["CLAUDE"] == "API answer here"

    def test_cli_success_used_directly(self):
        """CLI succeeds → no API fallback."""
        state = make_state(task="architect a system")
        with (
            patch("nodes.claude.shutil.which", return_value="/usr/bin/claude"),
            patch("nodes.claude._claude_cli", return_value=("CLI answer", True)),
            patch("nodes.claude._claude_api_fallback") as mock_api,
        ):
            result = claude(state)
        assert result["agent_outputs"]["CLAUDE"] == "CLI answer"
        mock_api.assert_not_called()

    def test_no_cli_uses_api(self):
        """No CLI binary → API path directly."""
        state = make_state(task="architect a system")
        with (
            patch("nodes.claude.shutil.which", return_value=None),
            patch("nodes.claude._claude_api_fallback", return_value="API answer"),
        ):
            result = claude(state)
        assert result["agent_outputs"]["CLAUDE"] == "API answer"

    def test_cli_fail_and_no_api_key_clean_message(self):
        """CLI fails AND no API key → clean guidance message, not raw 401."""
        state = make_state(task="architect a system")
        no_key_msg = "[Claude node: set ANTHROPIC_API_KEY in .env or install claude CLI]"
        with (
            patch("nodes.claude.shutil.which", return_value="/usr/bin/claude"),
            patch("nodes.claude._claude_cli", return_value=("[Claude CLI error: 401]", False)),
            patch("nodes.claude._claude_api_fallback", return_value=no_key_msg),
        ):
            result = claude(state)
        assert "ANTHROPIC_API_KEY" in result["agent_outputs"]["CLAUDE"]


class TestClaudeCliReturnsTuple:
    def test_cli_returns_tuple(self):
        """_claude_cli must return (text, success) for the chaining logic."""
        from nodes.claude import _claude_cli

        state = make_state(task="x")
        proc = type("P", (), {"stdout": "", "stderr": "boom", "returncode": 1})()
        with patch("nodes.claude.subprocess.run", return_value=proc), patch("nodes.claude.print_agent_header"):
            out, ok = _claude_cli(state)
        assert ok is False
        assert isinstance(out, str)
