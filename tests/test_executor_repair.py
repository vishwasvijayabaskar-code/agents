"""Tests for EXECUTOR command runner + CODER repair loop (step 28)."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from nodes.executor import _extract_commands, _run_commands, executor
from tests.conftest import make_state


class TestExtractCommands:
    def test_run_tags(self):
        assert _extract_commands("<run>echo hi</run>") == ["echo hi"]

    def test_bash_fence(self):
        assert _extract_commands("```bash\nls -la\n```") == ["ls -la"]

    def test_none(self):
        assert _extract_commands("just prose") == []


class TestRunCommands:
    def test_success(self, tmp_path):
        results, failed = _run_commands(["echo hello"], str(tmp_path))
        assert not failed
        assert any("hello" in r for r in results)

    def test_failure_flagged(self, tmp_path):
        results, failed = _run_commands(["exit 1"], str(tmp_path))
        assert failed

    def test_blocked_command(self, tmp_path):
        results, failed = _run_commands(["rm -rf /"], str(tmp_path))
        assert not failed  # security block is not a repair-eligible failure
        assert any("BLOCKED" in r for r in results)


class TestRepairLoop:
    def test_repair_triggered_on_failure(self, tmp_path):
        state = make_state(
            task="run the script",
            output_dir=str(tmp_path),
            agent_outputs={"CODER": "```bash\nexit 1\n```"},
        )
        with (
            patch("nodes.executor.cfg.get", side_effect=lambda s, k, d=None: True if k in ("enabled", "repair") else d),
            patch(
                "nodes.executor._attempt_repair",
                return_value=["[repair attempt via CODER]", "$ echo fixed\nfixed\nExit: 0"],
            ) as mock_repair,
        ):
            result = executor(state)
        mock_repair.assert_called_once()
        assert "repair" in result["agent_outputs"]["EXECUTOR"]
        assert any("repair" in h for h in result["history"])

    def test_no_repair_on_success(self, tmp_path):
        state = make_state(
            task="run it",
            output_dir=str(tmp_path),
            agent_outputs={"CODER": "```bash\necho ok\n```"},
        )
        with (
            patch("nodes.executor.cfg.get", side_effect=lambda s, k, d=None: True if k in ("enabled", "repair") else d),
            patch("nodes.executor._attempt_repair") as mock_repair,
        ):
            executor(state)
        mock_repair.assert_not_called()

    def test_repair_disabled(self, tmp_path):
        state = make_state(
            task="run it",
            output_dir=str(tmp_path),
            agent_outputs={"CODER": "```bash\nexit 1\n```"},
        )

        def cfg_get(section, key, default=None):
            if key == "enabled":
                return True
            if key == "repair":
                return False
            return default

        with (
            patch("nodes.executor.cfg.get", side_effect=cfg_get),
            patch("nodes.executor._attempt_repair") as mock_repair,
        ):
            executor(state)
        mock_repair.assert_not_called()
