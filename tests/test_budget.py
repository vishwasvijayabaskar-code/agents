"""Tests for token budget enforcement (Tier 8A)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.llm import (
    TokenBudgetExceeded,
    _check_budget,
    _stream_ctx,
    _track_tokens,
    get_budget_used,
    token_budget,
)


class TestTokenBudget:
    def test_budget_context_manager_sets_and_clears(self):
        assert getattr(_stream_ctx, "budget", 0) == 0
        with token_budget(10000):
            assert _stream_ctx.budget == 10000
            assert _stream_ctx.budget_used == 0
        assert _stream_ctx.budget == 0

    def test_track_tokens_increments(self):
        with token_budget(50000):
            _track_tokens(100, 50)
            assert get_budget_used() == 150
            _track_tokens(200, 100)
            assert get_budget_used() == 450

    def test_check_budget_passes_under_limit(self):
        with token_budget(1000):
            _track_tokens(500, 200)
            _check_budget()  # should not raise

    def test_check_budget_raises_when_exceeded(self):
        with token_budget(100):
            _track_tokens(80, 30)  # 110 > 100
            with pytest.raises(TokenBudgetExceeded):
                _check_budget()

    def test_no_budget_means_no_limit(self):
        with token_budget(0):
            _track_tokens(999999, 999999)
            _check_budget()  # should not raise (budget=0 means unlimited)

    def test_call_checks_budget_before_llm(self):
        """_call should raise TokenBudgetExceeded if budget exhausted."""
        with token_budget(10):
            _track_tokens(10, 5)  # over budget
            with pytest.raises(TokenBudgetExceeded):
                from helpers.llm import _call

                _call("model", "sys", "usr")

    def test_call_stream_checks_budget_before_llm(self):
        """_call_stream should raise TokenBudgetExceeded if budget exhausted."""
        with token_budget(10):
            _track_tokens(10, 5)
            with pytest.raises(TokenBudgetExceeded):
                from helpers.llm import _call_stream

                _call_stream("model", "sys", "usr")

    def test_call_tracks_tokens_after_success(self):
        """After successful _call, budget_used should increase."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "hello"
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 10

        with (
            token_budget(10000),
            patch("helpers.llm.completion", return_value=mock_response),
            patch("helpers.llm._log_usage"),
        ):
            from helpers.llm import _call

            _call("model", "sys", "usr")
            assert get_budget_used() == 60
