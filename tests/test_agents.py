"""Tests for individual agent nodes — all LLM calls mocked."""
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.conftest import make_state


# ---------------------------------------------------------------------------
# FAST node
# ---------------------------------------------------------------------------

class TestFastNode:
    def test_fast_returns_result(self):
        from nodes.fast import fast
        state = make_state(task="what is 2+2")
        with patch("nodes.fast._call_stream", return_value="4"):
            result = fast(state)
        assert result["result"] == "4"
        assert result["agent_outputs"]["FAST"] == "4"
        assert "Fast agent completed" in result["history"]

    def test_fast_handles_error(self):
        from nodes.fast import fast
        state = make_state(task="error task")
        with patch("nodes.fast._call_stream", side_effect=RuntimeError("model down")):
            result = fast(state)
        assert "[FAST error:" in result["result"]
        assert "FAST" in result["agent_outputs"]

    def test_fast_passes_chat_messages(self):
        from nodes.fast import fast
        messages = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        state = make_state(task="follow up", chat_messages=messages)
        with patch("nodes.fast._call_stream", return_value="response") as mock_stream:
            fast(state)
        call_kwargs = mock_stream.call_args
        assert call_kwargs.kwargs.get("messages") == messages or \
               (call_kwargs.args and messages in call_kwargs.args)


# ---------------------------------------------------------------------------
# CODER node
# ---------------------------------------------------------------------------

class TestCoderNode:
    def test_coder_returns_result(self):
        from nodes.coder import coder
        state = make_state(task="write a hello world")
        with patch("nodes.coder._call_stream", return_value="print('hello world')"):
            result = coder(state)
        assert result["result"] == "print('hello world')"
        assert result["agent_outputs"]["CODER"] == "print('hello world')"

    def test_coder_handles_error(self):
        from nodes.coder import coder
        state = make_state(task="error")
        with patch("nodes.coder._call_stream", side_effect=RuntimeError("boom")):
            result = coder(state)
        assert "[CODER error:" in result["result"]


# ---------------------------------------------------------------------------
# EXECUTOR node
# ---------------------------------------------------------------------------

class TestExecutorNode:
    def test_executor_blocked_rm_rf(self):
        """rm -rf in a <run> block must be blocked."""
        from nodes.executor import executor
        coder_out = "<run>rm -rf /tmp/test</run>"
        state = make_state(task="run it", agent_outputs={"CODER": coder_out})
        result = executor(state)
        exec_out = result.get("agent_outputs", {}).get("EXECUTOR", "")
        assert "BLOCKED" in exec_out

    def test_executor_blocked_sudo(self):
        from nodes.executor import executor
        coder_out = "<run>sudo apt-get install curl</run>"
        state = make_state(task="run it", agent_outputs={"CODER": coder_out})
        result = executor(state)
        exec_out = result.get("agent_outputs", {}).get("EXECUTOR", "")
        assert "BLOCKED" in exec_out

    def test_executor_no_commands_found(self):
        """Coder output with no run blocks → no-op message."""
        from nodes.executor import executor
        state = make_state(task="run it", agent_outputs={"CODER": "just a comment, no commands"})
        result = executor(state)
        exec_out = result.get("agent_outputs", {}).get("EXECUTOR", "")
        assert "No commands" in exec_out or exec_out == ""


# ---------------------------------------------------------------------------
# Orchestrator state mutations
# ---------------------------------------------------------------------------

class TestOrchestratorNode:
    def test_force_route_bypasses_llm(self):
        from nodes.orchestrator import orchestrator
        state = make_state(task="any task", force_route="CLAUDE", iterations=0)
        result = orchestrator(state)
        assert result["route"] == "CLAUDE"
        assert result["iterations"] == 1

    def test_fast_path_short_task(self):
        from nodes.orchestrator import orchestrator
        state = make_state(task="what is 2+2", iterations=0)
        with patch("nodes.orchestrator._relevant_memory", return_value=""):
            result = orchestrator(state)
        # Should have fast-pathed without LLM
        assert result["route"] in ("FAST", "CODER", "RESEARCHER")
        assert "fast-path" in " ".join(result["history"]).lower() or \
               "forced" in " ".join(result["history"]).lower()

    def test_llm_route_used_for_long_task(self):
        from nodes.orchestrator import orchestrator
        # >150 chars, no multi-hop keyword → fast_route returns None → falls to LLM
        long_task = "explain how photosynthesis works in great detail including " + "a" * 120
        state = make_state(task=long_task, iterations=0)
        with patch("nodes.orchestrator._call", return_value='{"route": "RESEARCHER", "done": false}') as mock_call, \
             patch("nodes.orchestrator._relevant_memory", return_value=""):
            result = orchestrator(state)
        mock_call.assert_called_once()
        assert result["route"] == "RESEARCHER"

    def test_qwen3_think_tags_stripped(self):
        from nodes.orchestrator import orchestrator
        long_task = "a" * 200
        state = make_state(task=long_task, iterations=0)
        raw_with_think = '<think>Let me think...</think>\n{"route": "FAST", "done": false}'
        with patch("nodes.orchestrator._call", return_value=raw_with_think), \
             patch("nodes.orchestrator._relevant_memory", return_value=""):
            result = orchestrator(state)
        assert result["route"] == "FAST"

    def test_iterations_incremented(self):
        from nodes.orchestrator import orchestrator
        long_task = "a" * 200
        state = make_state(task=long_task, iterations=0)
        with patch("nodes.orchestrator._call", return_value='{"route": "FAST", "done": false}'), \
             patch("nodes.orchestrator._relevant_memory", return_value=""):
            result = orchestrator(state)
        assert result["iterations"] == 1
