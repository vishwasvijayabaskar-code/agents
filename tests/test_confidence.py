"""Tests for confidence routing (Tier 3.4)."""
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.conftest import make_state
from nodes.orchestrator import _score_output, _confidence_escalation_done, orchestrator


class TestScoreOutput:
    def test_returns_integer(self):
        with patch("nodes.orchestrator._call", return_value="7"):
            score = _score_output("task", "output")
        assert isinstance(score, int)
        assert 1 <= score <= 10

    def test_parses_score_from_noisy_output(self):
        with patch("nodes.orchestrator._call", return_value="I'd rate this 8 out of 10."):
            score = _score_output("task", "output")
        assert score == 8

    def test_strips_think_tags(self):
        with patch("nodes.orchestrator._call", return_value="<think>analyzing...</think>6"):
            score = _score_output("task", "output")
        assert score == 6

    def test_defaults_to_5_on_parse_fail(self):
        with patch("nodes.orchestrator._call", return_value="excellent work!"):
            score = _score_output("task", "output")
        assert score == 5

    def test_defaults_to_5_on_error(self):
        with patch("nodes.orchestrator._call", side_effect=RuntimeError("down")):
            score = _score_output("task", "output")
        assert score == 5


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
        with patch("nodes.orchestrator._score_output", return_value=3), \
             patch("nodes.orchestrator._relevant_memory", return_value=""):
            result = orchestrator(state)

        assert result["route"] == "CODER"
        assert any("confidence escalation" in h for h in result["history"])

    def test_high_score_no_escalation(self):
        state = make_state(
            task="what is 2+2",
            iterations=1,
            agent_outputs={"FAST": "2+2 = 4"},
        )
        with patch("nodes.orchestrator._score_output", return_value=9), \
             patch("nodes.orchestrator._call", return_value='{"route": null, "done": true}'), \
             patch("nodes.orchestrator._relevant_memory", return_value=""):
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
        with patch("nodes.orchestrator._score_output", return_value=2), \
             patch("nodes.orchestrator._call", return_value='{"route": null, "done": true}'), \
             patch("nodes.orchestrator._relevant_memory", return_value=""):
            result = orchestrator(state)

        # Count only history entries added THIS call (after the prior ones)
        new_entries = result["history"][len(prior_history):]
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
        with patch("nodes.orchestrator._score_output") as mock_score, \
             patch("nodes.orchestrator._call", return_value='{"route": null, "done": true}'), \
             patch("nodes.orchestrator._relevant_memory", return_value=""):
            orchestrator(state)

        # _score_output should NOT have been called
        mock_score.assert_not_called()

    def test_escalation_skipped_if_target_already_ran(self):
        """FAST score=2 but CODER already ran → skip escalation."""
        state = make_state(
            task="write code",
            iterations=2,
            agent_outputs={"FAST": "meh", "CODER": "existing code"},
        )
        with patch("nodes.orchestrator._score_output", return_value=2), \
             patch("nodes.orchestrator._call", return_value='{"route": null, "done": true}'), \
             patch("nodes.orchestrator._relevant_memory", return_value=""):
            result = orchestrator(state)

        assert not any("confidence escalation" in h for h in result["history"])
