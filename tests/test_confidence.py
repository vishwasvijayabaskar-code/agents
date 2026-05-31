"""Tests for confidence routing (Tier 3.4)."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from nodes.orchestrator import _confidence_escalation_done, _heuristic_score, _score_output, orchestrator
from tests.conftest import make_state

# Ambiguous output that heuristic returns None for (forces LLM scoring)
_AMBIGUOUS_OUTPUT = "The answer to your question involves several considerations. First, we need to understand the underlying principles. Then we can apply them systematically to reach a conclusion."


class TestHeuristicScore:
    def test_short_output_scores_low(self):
        assert _heuristic_score("short") == 2

    def test_empty_output_scores_low(self):
        assert _heuristic_score("") == 2

    def test_error_output_scores_low(self):
        assert _heuristic_score("sorry, I can't help with that request") == 3

    def test_code_output_scores_high(self):
        output = "Here is the implementation:\n```python\ndef sort(arr):\n    return sorted(arr)\n```\nThis handles all edge cases."
        assert _heuristic_score(output) == 7

    def test_ambiguous_returns_none(self):
        assert _heuristic_score(_AMBIGUOUS_OUTPUT) is None


class TestScoreOutput:
    def test_returns_integer(self):
        with patch("nodes.orchestrator._call", return_value="7"):
            score = _score_output("task", _AMBIGUOUS_OUTPUT)
        assert isinstance(score, int)
        assert 1 <= score <= 10

    def test_parses_score_from_noisy_output(self):
        with patch("nodes.orchestrator._call", return_value="I'd rate this 8 out of 10."):
            score = _score_output("task", _AMBIGUOUS_OUTPUT)
        assert score == 8

    def test_strips_think_tags(self):
        with patch("nodes.orchestrator._call", return_value="<think>analyzing...</think>6"):
            score = _score_output("task", _AMBIGUOUS_OUTPUT)
        assert score == 6

    def test_defaults_to_5_on_parse_fail(self):
        with patch("nodes.orchestrator._call", return_value="excellent work!"):
            score = _score_output("task", _AMBIGUOUS_OUTPUT)
        assert score == 5

    def test_defaults_to_5_on_error(self):
        with patch("nodes.orchestrator._call", side_effect=RuntimeError("down")):
            score = _score_output("task", _AMBIGUOUS_OUTPUT)
        assert score == 5

    def test_heuristic_skips_llm_for_code(self):
        """Output with code blocks should get score=7 without calling LLM."""
        code_output = "Here is the code:\n```python\ndef hello():\n    print('hi')\n```\nDone! This works well and handles edge cases properly."
        with patch("nodes.orchestrator._call") as mock_call:
            score = _score_output("task", code_output)
        mock_call.assert_not_called()
        assert score == 7


class TestConfidenceEscalationDone:
    def test_false_when_no_history(self):
        state = make_state(history=[])
        assert _confidence_escalation_done(state) is False

    def test_false_when_no_escalation_in_history(self):
        state = make_state(history=["Orchestrator → fast-path route=FAST", "Fast agent completed"])
        assert _confidence_escalation_done(state) is False

    def test_true_when_escalation_in_history(self):
        state = make_state(history=["Orchestrator → confidence escalation FAST→CODER (score=3/10)"])
        assert _confidence_escalation_done(state) is True


class TestConfidenceEscalationIntegration:
    def test_low_score_escalates_fast_to_coder(self):
        state = make_state(
            task="write a sorting algorithm",
            iterations=1,
            agent_outputs={"FAST": "Bubble sort compares adjacent elements."},
        )
        with (
            patch("nodes.orchestrator._score_output", return_value=3),
            patch("nodes.orchestrator._relevant_memory", return_value=""),
            patch("nodes.orchestrator._cache_lookup", return_value=None),
        ):
            result = orchestrator(state)

        assert result["route"] == "CODER"
        assert any("confidence escalation" in h for h in result["history"])

    def test_high_score_no_escalation(self):
        state = make_state(
            task="what is 2+2",
            iterations=1,
            agent_outputs={"FAST": "2+2 = 4"},
        )
        with (
            patch("nodes.orchestrator._score_output", return_value=9),
            patch("nodes.orchestrator._call", return_value='{"route": null, "done": true}'),
            patch("nodes.orchestrator._relevant_memory", return_value=""),
        ):
            result = orchestrator(state)

        assert not any("confidence escalation" in h for h in result["history"])

    def test_no_double_escalation(self):
        """Already escalated once → no second escalation even on low score."""
        prior_history = ["Orchestrator → confidence escalation FAST→CODER (score=2/10)"]
        state = make_state(
            task="write code",
            iterations=2,
            agent_outputs={"FAST": "short answer", "CODER": "some code"},
            history=list(prior_history),
        )
        with (
            patch("nodes.orchestrator._score_output", return_value=2),
            patch("nodes.orchestrator._call", return_value='{"route": null, "done": true}'),
            patch("nodes.orchestrator._relevant_memory", return_value=""),
        ):
            result = orchestrator(state)

        # Count only history entries added THIS call (after the prior ones)
        new_entries = result["history"][len(prior_history) :]
        new_escalations = [h for h in new_entries if "confidence escalation" in h]
        assert len(new_escalations) == 0

    def test_fast_pathed_task_skips_confidence_scoring(self):
        """Fast-pathed tasks shouldn't waste time on confidence scoring."""
        state = make_state(
            task="hello",
            iterations=1,
            agent_outputs={"FAST": "Hi there!"},
            history=["Orchestrator → fast-path route=FAST"],
        )
        with (
            patch("nodes.orchestrator._score_output") as mock_score,
            patch("nodes.orchestrator._call", return_value='{"route": null, "done": true}'),
            patch("nodes.orchestrator._relevant_memory", return_value=""),
        ):
            orchestrator(state)

        # _score_output should NOT have been called
        mock_score.assert_not_called()

    def test_forced_route_skips_confidence_scoring(self):
        """--route forced tasks shouldn't auto-escalate — user chose the agent."""
        state = make_state(
            task="explain hash maps",
            iterations=1,
            agent_outputs={"FAST": "A hash map stores key-value pairs."},
            history=["Orchestrator → forced route=FAST"],
        )
        with (
            patch("nodes.orchestrator._score_output") as mock_score,
            patch("nodes.orchestrator._call", return_value='{"route": null, "done": true}'),
            patch("nodes.orchestrator._relevant_memory", return_value=""),
            patch("nodes.orchestrator._cache_lookup", return_value=None),
        ):
            result = orchestrator(state)

        mock_score.assert_not_called()
        assert not any("confidence escalation" in h for h in result["history"])

    def test_escalation_skipped_if_target_already_ran(self):
        """FAST score=2 but CODER already ran → skip escalation."""
        state = make_state(
            task="write code",
            iterations=2,
            agent_outputs={"FAST": "meh", "CODER": "existing code"},
        )
        with (
            patch("nodes.orchestrator._score_output", return_value=2),
            patch("nodes.orchestrator._call", return_value='{"route": null, "done": true}'),
            patch("nodes.orchestrator._relevant_memory", return_value=""),
        ):
            result = orchestrator(state)

        assert not any("confidence escalation" in h for h in result["history"])
