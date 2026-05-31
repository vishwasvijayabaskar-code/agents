"""Tests for web UI endpoints (Tasks 13-14)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from web.app import _health_status, _session_to_markdown, app

client = TestClient(app)


class TestSessionMarkdown:
    def test_empty_session(self):
        md = _session_to_markdown([])
        assert "session export" in md
        assert "0 task" in md

    def test_renders_tasks(self):
        tasks = [
            {"task": "explain X", "result": "X is...", "agents": ["FAST"], "ts": "2026-05-31T01:00:00"},
            {"task": "build Y", "result": "code", "agents": ["CODER"], "ts": "2026-05-31T01:05:00"},
        ]
        md = _session_to_markdown(tasks)
        assert "explain X" in md
        assert "build Y" in md
        assert "FAST" in md
        assert "CODER" in md
        assert "2 task" in md


class TestHealthStatus:
    def test_ollama_reachable(self):
        fake = MagicMock()
        fake.read.return_value = b'{"models": [{"name": "qwen2.5:7b"}]}'
        fake.__enter__ = lambda s: fake
        fake.__exit__ = lambda s, *a: None
        with (
            patch("urllib.request.urlopen", return_value=fake),
            patch("web.app.cfg.list_models", return_value={"fast": "ollama/qwen2.5:7b", "claude": "claude-sonnet-4-6"}),
        ):
            status = _health_status()
        assert status["ollama_reachable"] is True
        assert status["models"]["fast"]["present"] is True
        # non-ollama model assumed present
        assert status["models"]["claude"]["present"] is True

    def test_ollama_unreachable(self):
        with (
            patch("urllib.request.urlopen", side_effect=OSError("refused")),
            patch("web.app.cfg.list_models", return_value={"fast": "ollama/qwen2.5:7b"}),
        ):
            status = _health_status()
        assert status["ollama_reachable"] is False
        assert status["models"]["fast"]["present"] is False

    def test_missing_model_flagged(self):
        fake = MagicMock()
        fake.read.return_value = b'{"models": [{"name": "other:latest"}]}'
        fake.__enter__ = lambda s: fake
        fake.__exit__ = lambda s, *a: None
        with (
            patch("urllib.request.urlopen", return_value=fake),
            patch("web.app.cfg.list_models", return_value={"fast": "ollama/qwen2.5:7b"}),
        ):
            status = _health_status()
        assert status["models"]["fast"]["present"] is False


class TestEndpoints:
    def test_health_api(self):
        with patch("web.app._health_status", return_value={"ollama_reachable": True, "base": "x", "models": {}}):
            r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["ollama_reachable"] is True

    def test_session_export_no_auth_configured(self):
        # No auth_token set → accessible, returns markdown
        with patch("web.app._auth_token", return_value=""):
            r = client.get("/api/session/export")
        assert r.status_code == 200
        assert "session export" in r.text
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_session_export_blocked_when_auth_required(self):
        with patch("web.app._auth_token", return_value="secret"):
            r = client.get("/api/session/export")
        assert r.status_code == 401

    def test_models_api(self):
        r = client.get("/api/models")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_graph_includes_codebase(self):
        r = client.get("/api/graph")
        assert r.status_code == 200
        assert "CODEBASE" in r.json()["mermaid"]
