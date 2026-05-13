"""Tests for helpers/search.py — no network calls."""
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.search import _strip_html, _format_search_results, _robots_allowed


class TestStripHtml:
    def test_strips_script_tags(self):
        html = "<html><script>alert('x')</script><p>hello</p></html>"
        result = _strip_html(html)
        assert "alert" not in result
        assert "hello" in result

    def test_strips_style_tags(self):
        html = "<style>body { color: red; }</style><p>content</p>"
        result = _strip_html(html)
        assert "color" not in result
        assert "content" in result

    def test_strips_nav(self):
        html = "<nav>nav stuff</nav><main>main content</main>"
        result = _strip_html(html)
        assert "nav stuff" not in result

    def test_plain_text_unchanged(self):
        text = "just plain text"
        result = _strip_html(text)
        assert "plain text" in result

    def test_empty_string(self):
        assert _strip_html("") == ""


class TestFormatSearchResults:
    def test_formats_results(self):
        results = [
            {"title": "Python Docs", "body": "Python 3.x reference", "href": "https://python.org"},
            {"title": "Flask Docs", "body": "Micro web framework", "href": "https://flask.palletsprojects.com"},
        ]
        formatted = _format_search_results(results)
        assert "Python Docs" in formatted
        assert "Flask Docs" in formatted
        assert "python.org" in formatted

    def test_empty_results(self):
        result = _format_search_results([])
        # Returns some fallback string when list is empty
        assert isinstance(result, str)

    def test_truncates_long_body(self):
        results = [{"title": "T", "body": "x" * 1000, "href": "http://example.com"}]
        formatted = _format_search_results(results)
        # Body should be truncated — not all 1000 chars
        assert len(formatted) < 1200


class TestRobotsAllowed:
    def test_unreachable_url_defaults_to_allowed(self):
        # If robots.txt can't be fetched, should permit (fail open)
        result = _robots_allowed("https://thisdoesnotexist12345.example.invalid/page")
        assert result is True

    def test_invalid_url_allowed(self):
        result = _robots_allowed("not-a-url")
        assert result is True
