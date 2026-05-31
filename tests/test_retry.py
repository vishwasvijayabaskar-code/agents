"""Tests for LLM retry/backoff (Task 8)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.llm import (
    TokenBudgetExceeded,
    _completion_with_retry,
    _is_transient,
    _retry_count,
)


class TestIsTransient:
    def test_connection_error_transient(self):
        assert _is_transient(Exception("Connection refused"))

    def test_timeout_transient(self):
        assert _is_transient(Exception("Request timed out"))

    def test_503_transient(self):
        assert _is_transient(Exception("503 Service Unavailable"))

    def test_apiconnection_classname_transient(self):
        class APIConnectionError(Exception):
            pass
        assert _is_transient(APIConnectionError("boom"))

    def test_value_error_not_transient(self):
        assert not _is_transient(ValueError("bad input"))

    def test_budget_exceeded_not_transient(self):
        assert not _is_transient(TokenBudgetExceeded("over budget"))


class TestRetryCount:
    def test_default_is_int(self):
        assert isinstance(_retry_count(), int)
        assert _retry_count() >= 0

    def test_reads_config(self):
        with patch("helpers.config.cfg.get", return_value=5):
            assert _retry_count() == 5

    def test_negative_clamped_to_zero(self):
        with patch("helpers.config.cfg.get", return_value=-3):
            assert _retry_count() == 0


class TestCompletionWithRetry:
    def test_succeeds_first_try(self):
        with patch("helpers.llm.completion", return_value="ok") as mock_c, \
             patch("helpers.llm._retry_count", return_value=2):
            result = _completion_with_retry(model="x")
        assert result == "ok"
        assert mock_c.call_count == 1

    def test_retries_then_succeeds(self):
        calls = [Exception("connection refused"), "recovered"]

        def side_effect(**kwargs):
            r = calls.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with patch("helpers.llm.completion", side_effect=side_effect), \
             patch("helpers.llm._retry_count", return_value=2), \
             patch("helpers.llm.time.sleep"):
            result = _completion_with_retry(model="x")
        assert result == "recovered"

    def test_exhausts_retries_and_raises(self):
        with patch("helpers.llm.completion", side_effect=Exception("connection refused")) as mock_c, \
             patch("helpers.llm._retry_count", return_value=2), \
             patch("helpers.llm.time.sleep"):
            with pytest.raises(Exception, match="connection refused"):
                _completion_with_retry(model="x")
        # initial + 2 retries = 3 attempts
        assert mock_c.call_count == 3

    def test_non_transient_no_retry(self):
        with patch("helpers.llm.completion", side_effect=ValueError("bad")) as mock_c, \
             patch("helpers.llm._retry_count", return_value=3), \
             patch("helpers.llm.time.sleep"):
            with pytest.raises(ValueError):
                _completion_with_retry(model="x")
        assert mock_c.call_count == 1  # no retry on non-transient

    def test_zero_retries_single_attempt(self):
        with patch("helpers.llm.completion", side_effect=TimeoutError("timeout")) as mock_c, \
             patch("helpers.llm._retry_count", return_value=0), \
             patch("helpers.llm.time.sleep"):
            with pytest.raises(TimeoutError):
                _completion_with_retry(model="x")
        assert mock_c.call_count == 1
