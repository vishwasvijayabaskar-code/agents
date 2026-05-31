"""Tests for CLI helpers: --version, --list-agents, --verbose (Tasks 10-12)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.logging import enable_verbose, is_verbose, vlog
from main import doctor, get_version, init_project, list_agents


class TestVersion:
    def test_returns_string(self):
        assert isinstance(get_version(), str)
        assert get_version()

    def test_fallback_constant(self):
        # When importlib.metadata can't find the package, falls back to __version__
        with patch("importlib.metadata.version", side_effect=Exception("not installed")):
            import main

            assert get_version() == main.__version__


class TestListAgents:
    def test_includes_builtins(self):
        out = list_agents()
        for agent in ("FAST", "CODER", "RESEARCHER", "CLAUDE", "EXECUTOR", "CODEBASE", "CODEX", "SYNTHESIZE"):
            assert agent in out

    def test_has_descriptions(self):
        out = list_agents()
        assert "code generation" in out
        assert "web search" in out

    def test_is_string(self):
        assert isinstance(list_agents(), str)


class TestVerboseLogging:
    def teardown_method(self):
        enable_verbose(False)  # reset global state between tests

    def test_off_by_default_after_disable(self):
        enable_verbose(False)
        assert is_verbose() is False

    def test_enable(self):
        enable_verbose(True)
        assert is_verbose() is True

    def test_vlog_silent_when_off(self, capsys):
        enable_verbose(False)
        vlog("should not appear")
        captured = capsys.readouterr()
        assert "should not appear" not in captured.err
        assert "should not appear" not in captured.out

    def test_vlog_writes_stderr_when_on(self, capsys):
        enable_verbose(True)
        vlog("hello trace", tag="test")
        captured = capsys.readouterr()
        assert "hello trace" in captured.err
        assert "test" in captured.err
        # Must NOT pollute stdout
        assert "hello trace" not in captured.out

    def test_vlog_includes_tag(self, capsys):
        enable_verbose(True)
        vlog("msg", tag="orchestrator")
        assert "orchestrator" in capsys.readouterr().err


class TestDoctor:
    def test_healthy_returns_zero(self):
        fake = MagicMock()
        fake.read.return_value = b'{"models": [{"name": "qwen2.5:7b"}]}'
        fake.__enter__ = lambda s: fake
        fake.__exit__ = lambda s, *a: None
        with (
            patch("urllib.request.urlopen", return_value=fake),
            patch("main.cfg.validate", return_value=([], [])),
            patch("main.cfg.list_models", return_value={"fast": "ollama/qwen2.5:7b"}),
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "x"}),
        ):
            assert doctor() == 0

    def test_unreachable_ollama_flags_problem(self):
        with (
            patch("urllib.request.urlopen", side_effect=OSError("refused")),
            patch("main.cfg.validate", return_value=([], [])),
            patch("main.cfg.list_models", return_value={"fast": "ollama/qwen2.5:7b"}),
        ):
            assert doctor() >= 1

    def test_config_errors_counted(self):
        fake = MagicMock()
        fake.read.return_value = b'{"models": []}'
        fake.__enter__ = lambda s: fake
        fake.__exit__ = lambda s, *a: None
        with (
            patch("urllib.request.urlopen", return_value=fake),
            patch("main.cfg.validate", return_value=(["bad key"], [])),
            patch("main.cfg.list_models", return_value={}),
        ):
            assert doctor() >= 1


class TestInitProject:
    def test_creates_env_from_example(self, tmp_path, monkeypatch):
        import main

        monkeypatch.setattr(main, "__file__", str(tmp_path / "main.py"))
        (tmp_path / ".env.example").write_text("ANTHROPIC_API_KEY=sk-...\n")
        with patch("main.cfg.list_models", return_value={"fast": "ollama/qwen2.5:7b"}):
            init_project()
        assert (tmp_path / ".env").exists()
        assert "ANTHROPIC_API_KEY" in (tmp_path / ".env").read_text()

    def test_does_not_clobber_existing_env(self, tmp_path, monkeypatch):
        import main

        monkeypatch.setattr(main, "__file__", str(tmp_path / "main.py"))
        (tmp_path / ".env.example").write_text("X=1\n")
        (tmp_path / ".env").write_text("KEEP=me\n")
        with patch("main.cfg.list_models", return_value={}):
            init_project()
        assert (tmp_path / ".env").read_text() == "KEEP=me\n"
