"""Tests for CLI helpers: --version, --list-agents, --verbose (Tasks 10-12)."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.logging import enable_verbose, is_verbose, vlog
from main import get_version, list_agents


class TestVersion:
    def test_returns_string(self):
        assert isinstance(get_version(), str)
        assert get_version()

    def test_fallback_constant(self):
        # When importlib.metadata can't find the package, falls back to __version__
        with patch("importlib.metadata.version", side_effect=Exception("not installed")):
            import main

            assert get_version() == main.__version__


class TestListAgents:
    def test_includes_builtins(self):
        out = list_agents()
        for agent in ("FAST", "CODER", "RESEARCHER", "CLAUDE", "EXECUTOR", "CODEBASE", "CODEX", "SYNTHESIZE"):
            assert agent in out

    def test_has_descriptions(self):
        out = list_agents()
        assert "code generation" in out
        assert "web search" in out

    def test_is_string(self):
        assert isinstance(list_agents(), str)


class TestVerboseLogging:
    def teardown_method(self):
        enable_verbose(False)  # reset global state between tests

    def test_off_by_default_after_disable(self):
        enable_verbose(False)
        assert is_verbose() is False

    def test_enable(self):
        enable_verbose(True)
        assert is_verbose() is True

    def test_vlog_silent_when_off(self, capsys):
        enable_verbose(False)
        vlog("should not appear")
        captured = capsys.readouterr()
        assert "should not appear" not in captured.err
        assert "should not appear" not in captured.out

    def test_vlog_writes_stderr_when_on(self, capsys):
        enable_verbose(True)
        vlog("hello trace", tag="test")
        captured = capsys.readouterr()
        assert "hello trace" in captured.err
        assert "test" in captured.err
        # Must NOT pollute stdout
        assert "hello trace" not in captured.out

    def test_vlog_includes_tag(self, capsys):
        enable_verbose(True)
        vlog("msg", tag="orchestrator")
        assert "orchestrator" in capsys.readouterr().err
