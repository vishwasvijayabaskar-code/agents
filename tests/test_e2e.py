"""End-to-end smoke tests — full graph.invoke through real routing, mocked LLM.

No Ollama. Exercises the actual StateGraph wiring (orchestrator → worker →
loop-back → end) rather than individual nodes in isolation.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from graph import build_graph
from tests.conftest import make_state


def _invoke(task, force_route=None, **state_over):
    graph = build_graph()
    state = make_state(task=task, force_route=force_route, output_dir="/tmp/e2e_out", **state_over)
    return graph.invoke(state)


class TestE2EForcedRoutes:
    def test_fast_route_end_to_end(self):
        with (
            patch("nodes.fast._call_stream", return_value="4"),
            patch("nodes.orchestrator._relevant_memory", return_value=""),
            patch("nodes.orchestrator._cache_lookup", return_value=None),
            patch("nodes.orchestrator._call", return_value='{"route": null, "done": true}'),
            patch("nodes.orchestrator._score_output", return_value=8),
        ):
            result = _invoke("what is 2+2", force_route="FAST")
        assert result["result"] == "4"
        assert "FAST" in result["agent_outputs"]
        assert result["done"] is True

    def test_coder_route_end_to_end(self):
        code = "```python\ndef add(a, b):\n    return a + b\n```"
        with (
            patch("nodes.coder._call_stream", return_value=code),
            patch("nodes.orchestrator._relevant_memory", return_value=""),
            patch("nodes.orchestrator._cache_lookup", return_value=None),
            patch("nodes.orchestrator._call", return_value='{"route": null, "done": true}'),
            patch("nodes.orchestrator._score_output", return_value=8),
        ):
            result = _invoke("write an add function", force_route="CODER")
        assert "def add" in result["result"]
        assert "CODER" in result["agent_outputs"]


class TestE2EAutoRoute:
    def test_cache_hit_short_circuits(self):
        """A cache hit returns immediately without invoking any worker."""
        with (
            patch("nodes.orchestrator._cache_lookup", return_value="cached answer"),
            patch("nodes.fast._call_stream") as mock_fast,
            patch("nodes.coder._call_stream") as mock_coder,
        ):
            result = _invoke("a previously seen question")
        assert result["result"] == "cached answer"
        mock_fast.assert_not_called()
        mock_coder.assert_not_called()


class TestE2EGraphShape:
    def test_graph_builds_and_has_workers(self):
        graph = build_graph()
        assert graph is not None

    def test_history_records_routing(self):
        with (
            patch("nodes.fast._call_stream", return_value="hi"),
            patch("nodes.orchestrator._relevant_memory", return_value=""),
            patch("nodes.orchestrator._cache_lookup", return_value=None),
            patch("nodes.orchestrator._call", return_value='{"route": null, "done": true}'),
            patch("nodes.orchestrator._score_output", return_value=8),
        ):
            result = _invoke("hello", force_route="FAST")
        assert any("forced route" in h for h in result["history"])
