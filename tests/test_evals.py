"""Tests for eval harness (Option E)."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from evals.checkers import (
    all_passed,
    check_contains_any,
    check_contains_code,
    check_min_length,
    check_no_error,
    run_checks,
)
from evals.suite import SUITE

# ---------------------------------------------------------------------------
# Checker unit tests
# ---------------------------------------------------------------------------

class TestContainsCode:
    def test_detects_fenced_block(self):
        passed, _ = check_contains_code("Here is code:\n```python\nprint('hi')\n```", {})
        assert passed

    def test_detects_indented_code(self):
        passed, _ = check_contains_code("    def foo():\n        return 1", {})
        assert passed

    def test_fails_on_plain_text(self):
        passed, _ = check_contains_code("No code here, just words.", {})
        assert not passed

    def test_empty_fails(self):
        passed, _ = check_contains_code("", {})
        assert not passed


class TestContainsAny:
    def test_finds_value(self):
        passed, reason = check_contains_any("The answer is 42", {"values": ["42", "43"]})
        assert passed
        assert "42" in reason

    def test_fails_if_none_present(self):
        passed, _ = check_contains_any("Hello world", {"values": ["foo", "bar"]})
        assert not passed

    def test_empty_values(self):
        passed, _ = check_contains_any("anything", {"values": []})
        assert not passed

    def test_case_sensitive(self):
        passed, _ = check_contains_any("Paris", {"values": ["paris"]})
        assert not passed


class TestNoError:
    def test_clean_output_passes(self):
        passed, _ = check_no_error("The answer is 42. Here is how it works.", {})
        assert passed

    def test_sorry_cant_fails(self):
        passed, _ = check_no_error("Sorry, I can't help with that request.", {})
        assert not passed

    def test_error_prefix_fails(self):
        passed, _ = check_no_error("[Error: something went wrong]", {})
        assert not passed

    def test_case_insensitive(self):
        passed, _ = check_no_error("SORRY, I CANNOT HELP WITH THIS.", {})
        assert not passed


class TestMinLength:
    def test_long_enough(self):
        passed, _ = check_min_length("a" * 100, {"value": 50})
        assert passed

    def test_too_short(self):
        passed, _ = check_min_length("hi", {"value": 50})
        assert not passed

    def test_default_threshold(self):
        passed, _ = check_min_length("x" * 49, {})
        assert not passed

    def test_exact_threshold(self):
        passed, _ = check_min_length("x" * 50, {"value": 50})
        assert passed


class TestRunChecks:
    def test_all_pass(self):
        output = "```python\ndef foo(): return 42\n```"
        checks = [{"type": "contains_code"}, {"type": "no_error"}]
        results = run_checks(output, checks)
        assert all(r["passed"] for r in results)

    def test_one_fails(self):
        output = "short"
        checks = [{"type": "no_error"}, {"type": "min_length", "value": 100}]
        results = run_checks(output, checks)
        assert results[0]["passed"]  # no_error passes
        assert not results[1]["passed"]  # min_length fails

    def test_unknown_checker(self):
        results = run_checks("anything", [{"type": "nonexistent_check"}])
        assert not results[0]["passed"]
        assert "unknown checker" in results[0]["reason"]

    def test_all_passed_helper_true(self):
        results = [{"passed": True}, {"passed": True}]
        assert all_passed(results)

    def test_all_passed_helper_false(self):
        results = [{"passed": True}, {"passed": False}]
        assert not all_passed(results)


# ---------------------------------------------------------------------------
# Suite validation
# ---------------------------------------------------------------------------

class TestSuite:
    def test_suite_is_list(self):
        assert isinstance(SUITE, list)
        assert len(SUITE) > 0

    def test_all_tasks_have_required_fields(self):
        for task in SUITE:
            assert "id" in task, f"Missing 'id' in {task}"
            assert "task" in task, f"Missing 'task' in {task}"
            assert "checks" in task, f"Missing 'checks' in {task}"

    def test_all_ids_unique(self):
        ids = [t["id"] for t in SUITE]
        assert len(ids) == len(set(ids)), "Duplicate IDs in SUITE"

    def test_all_check_types_valid(self):
        from evals.checkers import _CHECKER_MAP
        for task in SUITE:
            for check in task["checks"]:
                assert check["type"] in _CHECKER_MAP, \
                    f"Unknown checker '{check['type']}' in task '{task['id']}'"

    def test_routes_are_valid_or_none(self):
        valid = {"CODER", "RESEARCHER", "FAST", "CLAUDE", "CODEX", "EXECUTOR", "CODEBASE", None}
        for task in SUITE:
            assert task.get("route") in valid, f"Invalid route in '{task['id']}'"


# ---------------------------------------------------------------------------
# Runner (dry-run mode — no agents invoked)
# ---------------------------------------------------------------------------

class TestRunnerDryRun:
    def test_dry_run_runs_without_agents(self):
        from evals.runner import run_suite
        summary = run_suite(dry_run=True)
        assert "total" in summary
        assert "passed" in summary
        assert "results" in summary

    def test_dry_run_all_fail_no_output(self):
        """Dry run: output is empty → all check types that require content fail."""
        from evals.runner import run_suite
        summary = run_suite(dry_run=True)
        # In dry-run, output is "" so contains_code, contains_any, min_length all fail
        # Only no_error might pass on empty string (no error signals in "")
        # We just validate structure
        for r in summary["results"]:
            assert "id" in r
            assert "passed" in r
            assert "checks" in r

    def test_dry_run_tag_filter(self):
        from evals.runner import run_suite
        summary = run_suite(tags=["fast"], dry_run=True)
        for r in summary["results"]:
            assert "fast" in r["tags"]

    def test_dry_run_id_filter(self):
        from evals.runner import run_suite
        summary = run_suite(task_id="fast_math", dry_run=True)
        assert summary["total"] == 1
        assert summary["results"][0]["id"] == "fast_math"

    def test_dry_run_invalid_id_returns_empty(self):
        from evals.runner import run_suite
        # No tasks match → run_suite prints warning and returns {}
        summary = run_suite(task_id="nonexistent_task_xyz", dry_run=True)
        assert summary == {}


class TestCompareRuns:
    def test_compare_needs_two_runs(self, tmp_path):
        """compare_runs returns early if < 2 runs."""
        from evals import runner as r_mod
        orig = r_mod.RESULTS_DIR
        r_mod.RESULTS_DIR = tmp_path
        try:
            result = r_mod.compare_runs()
            assert result is None  # function returns None when not enough runs
        finally:
            r_mod.RESULTS_DIR = orig

    def test_compare_detects_regression(self, tmp_path):
        from evals import runner as r_mod
        orig = r_mod.RESULTS_DIR
        r_mod.RESULTS_DIR = tmp_path

        # Create two fake run files
        prev = {
            "timestamp": "20260101_000000",
            "total": 2, "passed": 2, "failed": 0, "pass_rate": 100,
            "results": [
                {"id": "task_a", "passed": True, "checks": [], "tags": []},
                {"id": "task_b", "passed": True, "checks": [], "tags": []},
            ]
        }
        curr = {
            "timestamp": "20260102_000000",
            "total": 2, "passed": 1, "failed": 1, "pass_rate": 50,
            "results": [
                {"id": "task_a", "passed": False, "checks": [{"passed": False, "reason": "no code"}], "tags": []},
                {"id": "task_b", "passed": True, "checks": [], "tags": []},
            ]
        }
        (tmp_path / "20260101_000000.json").write_text(json.dumps(prev))
        (tmp_path / "20260102_000000.json").write_text(json.dumps(curr))

        try:
            result = r_mod.compare_runs()
            assert result is not None
            assert "task_a" in result["regressions"]
            assert result["improvements"] == []
        finally:
            r_mod.RESULTS_DIR = orig
