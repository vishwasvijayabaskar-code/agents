"""Tests for run-trace persistence + --list-runs/--replay (steps 23-24)."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import main


class TestSaveTrace:
    def test_writes_trace(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "RUNS_DIR", tmp_path)
        result = {"result": "hi", "history": ["a", "b"], "tokens_used": 5}
        with patch("main.cfg.get", return_value=True):
            main._save_trace("my task", result, ["FAST"], "20260101_000000")
        f = tmp_path / "20260101_000000.json"
        assert f.exists()
        d = json.loads(f.read_text())
        assert d["task"] == "my task"
        assert d["agents"] == ["FAST"]
        assert d["history"] == ["a", "b"]

    def test_disabled_writes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "RUNS_DIR", tmp_path)
        with patch("main.cfg.get", return_value=False):
            main._save_trace("t", {"result": "x"}, [], "20260101_000001")
        assert not list(tmp_path.glob("*.json"))

    def test_never_raises(self, tmp_path, monkeypatch):
        # Point RUNS_DIR at a file to force a write error; must be swallowed
        bad = tmp_path / "afile"
        bad.write_text("x")
        monkeypatch.setattr(main, "RUNS_DIR", bad / "sub")
        with patch("main.cfg.get", return_value=True):
            main._save_trace("t", {"result": "x"}, [], "id")  # no exception


class TestReplay:
    def test_replay_missing_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "RUNS_DIR", tmp_path)
        assert main.replay_run("nope") == 1

    def test_replay_existing_returns_0(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "RUNS_DIR", tmp_path)
        (tmp_path / "r1.json").write_text(
            json.dumps({"task": "t", "result": "res", "agents": ["FAST"], "history": ["h1"], "tokens_used": 1})
        )
        assert main.replay_run("r1") == 0

    def test_list_runs_no_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "RUNS_DIR", tmp_path / "missing")
        main.list_runs()  # no crash on missing dir
