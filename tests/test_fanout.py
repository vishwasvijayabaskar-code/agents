"""Tests for parallel fan-out execution (step 26)."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from nodes.orchestrator import _decompose_fanout, _is_fanout, _run_fanout, orchestrator
from tests.conftest import make_state


class TestIsFanout:
    def test_parallel_signal(self):
        assert _is_fanout("Summarize Python and also summarize Rust, separately")

    def test_simultaneously(self):
        assert _is_fanout("Research cats and dogs simultaneously in detail please")

    def test_sequential_is_not_fanout(self):
        # multi-hop ("then") must win over fan-out
        assert not _is_fanout("research React best practices and then build a todo app with them")

    def test_short_task_not_fanout(self):
        assert not _is_fanout("a and b")

    def test_plain_task_not_fanout(self):
        assert not _is_fanout("write a function to reverse a string")


class TestDecomposeFanout:
    def test_parses_valid_array(self):
        payload = '[{"route": "FAST", "task": "x"}, {"route": "FAST", "task": "y"}]'
        with patch("nodes.orchestrator._call", return_value=payload):
            out = _decompose_fanout("do x and y separately", "m")
        assert out is not None and len(out) == 2

    def test_strips_think_tags(self):
        payload = '<think>plan</think>[{"route":"FAST","task":"a"},{"route":"CODER","task":"b"}]'
        with patch("nodes.orchestrator._call", return_value=payload):
            out = _decompose_fanout("t", "m")
        assert out is not None and len(out) == 2

    def test_bad_output_returns_none(self):
        with patch("nodes.orchestrator._call", return_value="not json"):
            assert _decompose_fanout("t", "m") is None

    def test_single_item_rejected(self):
        with patch("nodes.orchestrator._call", return_value='[{"route":"FAST","task":"x"}]'):
            assert _decompose_fanout("t", "m") is None


class TestRunFanout:
    def test_runs_all_concurrently(self):
        subtasks = [{"route": "FAST", "task": "a"}, {"route": "CODER", "task": "b"}]

        def fake_exec(agent, query, node_fn, state):
            return f"out:{query}"

        state = make_state(task="t")
        with patch("helpers.delegation.execute_delegation", side_effect=fake_exec):
            results = _run_fanout(state, subtasks)
        assert len(results) == 2
        assert any("out:a" in v for v in results.values())
        assert any("out:b" in v for v in results.values())

    def test_subtask_error_isolated(self):
        subtasks = [{"route": "FAST", "task": "ok"}, {"route": "FAST", "task": "boom"}]

        def fake_exec(agent, query, node_fn, state):
            if query == "boom":
                raise RuntimeError("kaboom")
            return "fine"

        state = make_state(task="t")
        with patch("helpers.delegation.execute_delegation", side_effect=fake_exec):
            results = _run_fanout(state, subtasks)
        assert len(results) == 2
        assert any("error" in v for v in results.values())


class TestFanoutIntegration:
    def test_orchestrator_runs_fanout_and_routes_synthesize(self):
        state = make_state(task="Summarize Python and also summarize Rust, separately")
        fo = [{"route": "FAST", "task": "py"}, {"route": "FAST", "task": "rust"}]
        with (
            patch("nodes.orchestrator._cache_lookup", return_value=None),
            patch("nodes.orchestrator._decompose_fanout", return_value=fo),
            patch("nodes.orchestrator._run_fanout", return_value={"FAST#1": "Python...", "FAST#2": "Rust..."}),
        ):
            result = orchestrator(state)
        assert result["route"] == "SYNTHESIZE"
        assert "FAST#1" in result["agent_outputs"]
        assert "FAST#2" in result["agent_outputs"]
        assert any("fan-out" in h for h in result["history"])

    def test_single_fanout_result_done(self):
        state = make_state(task="Please summarize topic A and also topic B, separately and in detail")
        fo = [{"route": "FAST", "task": "a"}, {"route": "FAST", "task": "b"}]
        with (
            patch("nodes.orchestrator._cache_lookup", return_value=None),
            patch("nodes.orchestrator._decompose_fanout", return_value=fo),
            patch("nodes.orchestrator._run_fanout", return_value={"FAST#1": "only one"}),
        ):
            result = orchestrator(state)
        assert result["done"] is True
