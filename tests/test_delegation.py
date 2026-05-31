"""Tests for agent-to-agent delegation (Tier 8D)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.delegation import execute_delegation, parse_delegation, strip_delegation_tags
from tests.conftest import make_state


class TestParseDelegation:
    def test_valid_delegation(self):
        output = 'I need more info. <delegate agent="RESEARCHER">look up Python asyncio docs</delegate> Let me continue.'
        result = parse_delegation(output)
        assert result is not None
        agent, query = result
        assert agent == "RESEARCHER"
        assert query == "look up Python asyncio docs"

    def test_no_delegation_tag(self):
        assert parse_delegation("Just regular code output here.") is None

    def test_case_insensitive(self):
        output = '<Delegate Agent="researcher">query here</Delegate>'
        result = parse_delegation(output)
        assert result is not None
        assert result[0] == "RESEARCHER"

    def test_empty_query_returns_none(self):
        output = '<delegate agent="RESEARCHER"></delegate>'
        result = parse_delegation(output)
        assert result is None

    def test_multiline_query(self):
        output = '<delegate agent="FAST">what is\nthe meaning of life</delegate>'
        result = parse_delegation(output)
        assert result is not None
        assert "meaning of life" in result[1]


class TestStripDelegationTags:
    def test_strips_tags(self):
        output = 'Before <delegate agent="RESEARCHER">query</delegate> After'
        assert strip_delegation_tags(output) == "Before  After"

    def test_no_tags(self):
        assert strip_delegation_tags("plain text") == "plain text"

    def test_multiple_tags(self):
        output = '<delegate agent="A">q1</delegate> middle <delegate agent="B">q2</delegate>'
        result = strip_delegation_tags(output)
        assert "q1" not in result
        assert "q2" not in result
        assert "middle" in result


class TestExecuteDelegation:
    def test_runs_node_function(self):
        def mock_node(state):
            state["result"] = "delegated result"
            return state

        state = make_state(task="main task")
        result = execute_delegation("RESEARCHER", "lookup query", mock_node, state)
        assert result == "delegated result"

    def test_returns_empty_on_no_result(self):
        def mock_node(state):
            return state

        state = make_state(task="main task")
        result = execute_delegation("FAST", "query", mock_node, state)
        assert result == ""


class TestDelegationIntegration:
    def test_delegation_detected_and_executed(self):
        """Orchestrator detects delegation tag, runs delegate, injects result."""
        from nodes.orchestrator import orchestrator

        coder_output = 'Here is code.\n<delegate agent="RESEARCHER">look up Flask API docs</delegate>\nMore code.'
        state = make_state(
            task="build a Flask API",
            iterations=1,
            agent_outputs={"CODER": coder_output},
        )

        mock_researcher = MagicMock(return_value={
            "result": "Flask docs: use @app.route to define endpoints",
            "agent_outputs": {"RESEARCHER": "Flask docs info"},
        })

        with patch("nodes.orchestrator._get_delegation_targets", return_value={"RESEARCHER": mock_researcher}), \
             patch("nodes.orchestrator._score_output", return_value=7), \
             patch("nodes.orchestrator._call", return_value='{"route": null, "done": true}'), \
             patch("nodes.orchestrator._relevant_memory", return_value=""), \
             patch("nodes.orchestrator._cache_lookup", return_value=None):
            result = orchestrator(state)

        assert any("delegation" in h for h in result["history"])
        assert "Delegated from RESEARCHER" in result["agent_outputs"]["CODER"]
        mock_researcher.assert_called_once()

    def test_no_double_delegation(self):
        """If delegation already happened, don't delegate again."""
        from nodes.orchestrator import orchestrator

        coder_output = '<delegate agent="FAST">query</delegate>'
        state = make_state(
            task="build something",
            iterations=2,
            agent_outputs={"CODER": coder_output},
            history=["Orchestrator → delegation CODER→RESEARCHER: look up docs"],
        )

        with patch("nodes.orchestrator._score_output", return_value=7), \
             patch("nodes.orchestrator._call", return_value='{"route": null, "done": true}'), \
             patch("nodes.orchestrator._relevant_memory", return_value=""), \
             patch("nodes.orchestrator._cache_lookup", return_value=None):
            result = orchestrator(state)

        # Should NOT have a second delegation
        new_entries = result["history"][1:]  # skip the pre-existing one
        assert not any("delegation CODER→FAST" in h for h in new_entries)
