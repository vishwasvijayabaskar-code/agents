"""Tests for task decomposition (Tier 8B)."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from nodes.orchestrator import (
    _decompose_task,
    _is_multi_hop,
    orchestrator,
)
from tests.conftest import make_state


class TestIsMultiHop:
    def test_short_task_not_multi_hop(self):
        assert _is_multi_hop("what is 2+2") is False

    def test_long_task_with_keyword(self):
        assert _is_multi_hop("research the latest React patterns and then build a todo app using them") is True

    def test_long_task_without_keyword(self):
        assert _is_multi_hop("write a very detailed comprehensive essay about quantum mechanics") is False

    def test_with_first_keyword(self):
        assert (
            _is_multi_hop("first research Python best practices, then write a web scraper using those patterns") is True
        )

    def test_with_step_keywords(self):
        assert _is_multi_hop("step 1: research the API documentation, step 2: build a client library for it") is True


class TestDecomposeTask:
    def test_valid_decomposition(self):
        mock_response = '[{"route": "RESEARCHER", "task": "research React"}, {"route": "CODER", "task": "build app"}]'
        with patch("nodes.orchestrator._call", return_value=mock_response):
            result = _decompose_task("research React then build app", "model")
        assert result is not None
        assert len(result) == 2
        assert result[0]["route"] == "RESEARCHER"
        assert result[1]["route"] == "CODER"

    def test_single_subtask_returns_none(self):
        """Single subtask = no decomposition needed."""
        mock_response = '[{"route": "CODER", "task": "write code"}]'
        with patch("nodes.orchestrator._call", return_value=mock_response):
            result = _decompose_task("write code", "model")
        assert result is None

    def test_invalid_json_returns_none(self):
        with patch("nodes.orchestrator._call", return_value="I'll route to CODER"):
            result = _decompose_task("task", "model")
        assert result is None

    def test_llm_error_returns_none(self):
        with patch("nodes.orchestrator._call", side_effect=RuntimeError("down")):
            result = _decompose_task("task", "model")
        assert result is None

    def test_caps_at_4_subtasks(self):
        tasks = [{"route": "FAST", "task": f"step {i}"} for i in range(6)]
        with patch("nodes.orchestrator._call", return_value=str(tasks).replace("'", '"')):
            result = _decompose_task("complex task", "model")
        assert result is not None
        assert len(result) == 4

    def test_strips_think_tags(self):
        mock_response = (
            '<think>let me think...</think>[{"route": "RESEARCHER", "task": "r"}, {"route": "CODER", "task": "c"}]'
        )
        with patch("nodes.orchestrator._call", return_value=mock_response):
            result = _decompose_task("research then code", "model")
        assert result is not None
        assert len(result) == 2


class TestSubtaskExecution:
    def test_multi_hop_triggers_decomposition(self):
        task = "research the latest Python frameworks and then build a REST API using the best one"
        state = make_state(task=task, iterations=0)
        subtasks = [
            {"route": "RESEARCHER", "task": "research Python frameworks"},
            {"route": "CODER", "task": "build REST API"},
        ]
        with (
            patch("nodes.orchestrator._decompose_task", return_value=subtasks),
            patch("nodes.orchestrator._relevant_memory", return_value=""),
        ):
            result = orchestrator(state)

        assert result["subtasks"] is not None
        assert result["route"] == "RESEARCHER"
        assert any("decomposed" in h for h in result["history"])
        assert any("subtask 1/2" in h for h in result["history"])

    def test_subtask_advances_on_reentry(self):
        """After first subtask worker completes, orchestrator routes to second."""
        state = make_state(
            task="research then build",
            iterations=1,
            subtasks=[
                {"route": "RESEARCHER", "task": "research"},
                {"route": "CODER", "task": "build"},
            ],
            current_subtask=1,
            agent_outputs={"RESEARCHER": "found stuff"},
        )
        result = orchestrator(state)
        assert result["route"] == "CODER"
        assert result["current_subtask"] == 2
        assert any("subtask 2/2" in h for h in result["history"])

    def test_all_subtasks_done_sets_done(self):
        """When all subtasks executed, orchestrator sets done=True."""
        state = make_state(
            task="research then build",
            iterations=2,
            subtasks=[
                {"route": "RESEARCHER", "task": "research"},
                {"route": "CODER", "task": "build"},
            ],
            current_subtask=2,
            agent_outputs={"RESEARCHER": "research", "CODER": "code"},
        )
        result = orchestrator(state)
        assert result["done"] is True
        assert any("all subtasks complete" in h for h in result["history"])

    def test_simple_task_no_decomposition(self):
        """Short tasks bypass decomposition entirely."""
        state = make_state(task="what is 2+2", iterations=0)
        result = orchestrator(state)
        # Should fast-path, not decompose
        assert result.get("subtasks") is None
        assert any("fast-path" in h for h in result["history"])

    def test_decomposition_failure_falls_through(self):
        """If decomposition fails, falls through to normal LLM routing."""
        task = "research the latest frameworks and then build something with them"
        state = make_state(task=task, iterations=0)
        with (
            patch("nodes.orchestrator._decompose_task", return_value=None),
            patch("nodes.orchestrator._call", return_value='{"route": "RESEARCHER", "done": false}'),
            patch("nodes.orchestrator._relevant_memory", return_value=""),
        ):
            result = orchestrator(state)

        assert result.get("subtasks") is None
        assert result["route"] == "RESEARCHER"
