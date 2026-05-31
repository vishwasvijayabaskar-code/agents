"""Tests for synthesizer node."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from nodes.synthesizer import synthesizer
from tests.conftest import make_state


class TestSynthesizer:
    def test_skips_when_single_output(self):
        state = make_state(agent_outputs={"CODER": "some code"}, result="some code")
        result = synthesizer(state)
        # No change — nothing to synthesize
        assert result["result"] == "some code"
        assert "SYNTHESIZE" not in result["agent_outputs"]

    def test_skips_when_no_outputs(self):
        state = make_state(agent_outputs={}, result=None)
        result = synthesizer(state)
        assert result["result"] is None

    def test_synthesizes_multiple_outputs(self):
        state = make_state(
            task="research and build a Flask app",
            agent_outputs={
                "RESEARCHER": "Flask is a lightweight Python web framework.",
                "CODER": "```python\nfrom flask import Flask\napp = Flask(__name__)\n```",
            },
        )
        with patch("nodes.synthesizer._call_stream", return_value="merged result"):
            result = synthesizer(state)

        assert result["result"] == "merged result"
        assert result["agent_outputs"]["SYNTHESIZE"] == "merged result"
        assert "Synthesizer combined outputs" in result["history"]

    def test_fallback_on_llm_error(self):
        state = make_state(
            task="some task",
            agent_outputs={
                "RESEARCHER": "research output",
                "CODER": "code output",
            },
        )
        with patch("nodes.synthesizer._call_stream", side_effect=RuntimeError("LLM down")):
            result = synthesizer(state)

        # Falls back to last agent output
        assert result["result"] == "code output"

    def test_history_appended(self):
        state = make_state(
            task="t",
            agent_outputs={"FAST": "a", "CODER": "b"},
        )
        with patch("nodes.synthesizer._call_stream", return_value="merged"):
            result = synthesizer(state)

        assert any("Synthesizer" in h for h in result["history"])
