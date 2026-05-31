"""Tests for cache TTL enforcement + clear_cache (Task 17)."""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.memory import _cache_lookup, _within_ttl, clear_cache


class TestWithinTTL:
    def test_recent_within_ttl(self):
        ts = datetime.now().isoformat()
        assert _within_ttl(ts, 24) is True

    def test_old_outside_ttl(self):
        ts = (datetime.now() - timedelta(hours=48)).isoformat()
        assert _within_ttl(ts, 24) is False

    def test_zero_ttl_disables_check(self):
        ts = (datetime.now() - timedelta(days=365)).isoformat()
        assert _within_ttl(ts, 0) is True

    def test_empty_timestamp_fails(self):
        assert _within_ttl("", 24) is False

    def test_garbage_timestamp_fails(self):
        assert _within_ttl("not-a-date", 24) is False

    def test_boundary_just_inside(self):
        ts = (datetime.now() - timedelta(hours=23)).isoformat()
        assert _within_ttl(ts, 24) is True


class TestCacheLookup:
    def _mock_col(self, distance, timestamp):
        col = MagicMock()
        col.count.return_value = 1
        col.query.return_value = {
            "documents": [["cached result"]],
            "distances": [[distance]],
            "metadatas": [[{"timestamp": timestamp}]],
        }
        return col

    def test_fresh_hit_returned(self):
        col = self._mock_col(0.05, datetime.now().isoformat())
        with patch("helpers.memory._get_chroma", return_value=col):
            assert _cache_lookup("task", ttl_hours=24) == "cached result"

    def test_stale_hit_rejected(self):
        col = self._mock_col(0.05, (datetime.now() - timedelta(hours=100)).isoformat())
        with patch("helpers.memory._get_chroma", return_value=col):
            assert _cache_lookup("task", ttl_hours=24) is None

    def test_distant_rejected(self):
        col = self._mock_col(0.9, datetime.now().isoformat())
        with patch("helpers.memory._get_chroma", return_value=col):
            assert _cache_lookup("task", ttl_hours=24) is None

    def test_no_chroma_returns_none(self):
        with patch("helpers.memory._get_chroma", return_value=None):
            assert _cache_lookup("task") is None

    def test_ttl_zero_ignores_age(self):
        col = self._mock_col(0.05, (datetime.now() - timedelta(days=999)).isoformat())
        with patch("helpers.memory._get_chroma", return_value=col):
            assert _cache_lookup("task", ttl_hours=0) == "cached result"


class TestClearCache:
    def test_clears_entries(self):
        col = MagicMock()
        col.count.return_value = 3
        col.get.return_value = {"ids": ["a", "b", "c"]}
        with patch("helpers.memory._get_chroma", return_value=col):
            n = clear_cache()
        assert n == 3
        col.delete.assert_called_once_with(ids=["a", "b", "c"])

    def test_empty_cache(self):
        col = MagicMock()
        col.count.return_value = 0
        with patch("helpers.memory._get_chroma", return_value=col):
            assert clear_cache() == 0

    def test_no_chroma(self):
        with patch("helpers.memory._get_chroma", return_value=None):
            assert clear_cache() == 0
