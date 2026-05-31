"""Tests for file-watcher mode (Option B)."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the internal detection function only (no watchdog daemon)
from watch import _detect_task, _save_output


class TestDetectTask:
    def test_txt_file(self, tmp_path):
        f = tmp_path / "task.txt"
        f.write_text("explain how Redis works")
        task, route, project = _detect_task(f)
        assert task == "explain how Redis works"
        assert route is None
        assert project is None

    def test_md_file(self, tmp_path):
        f = tmp_path / "research.md"
        f.write_text("compare Flask vs FastAPI")
        task, route, project = _detect_task(f)
        assert task == "compare Flask vs FastAPI"

    def test_url_file(self, tmp_path):
        f = tmp_path / "page.url"
        f.write_text("https://example.com/docs\nextra line ignored")
        task, route, project = _detect_task(f)
        assert "https://example.com/docs" in task
        assert route == "RESEARCHER"

    def test_url_file_empty(self, tmp_path):
        f = tmp_path / "empty.url"
        f.write_text("")
        task, route, project = _detect_task(f)
        assert task  # returns fallback message
        assert route is None

    def test_python_code_file(self, tmp_path):
        f = tmp_path / "buggy.py"
        f.write_text("def add(a, b):\n    return a - b  # bug\n")
        task, route, project = _detect_task(f)
        assert "review" in task.lower()
        assert "```python" in task
        assert route == "CODER"

    def test_js_code_file(self, tmp_path):
        f = tmp_path / "script.js"
        f.write_text("const x = 1;")
        task, route, project = _detect_task(f)
        assert route == "CODER"
        assert "```javascript" in task

    def test_task_yaml(self, tmp_path):
        f = tmp_path / "job.task"
        f.write_text("task: build a REST API\nroute: CODER\n")
        task, route, project = _detect_task(f)
        assert task == "build a REST API"
        assert route == "CODER"
        assert project is None

    def test_task_yaml_with_project(self, tmp_path):
        f = tmp_path / "job.task"
        f.write_text("task: explain the auth module\nroute: RESEARCHER\nproject: /myproject\n")
        task, route, project = _detect_task(f)
        assert task == "explain the auth module"
        assert route == "RESEARCHER"
        assert project == "/myproject"

    def test_task_json(self, tmp_path):
        import json
        f = tmp_path / "job.task"
        f.write_text(json.dumps({"task": "what is asyncio", "route": "FAST"}))
        task, route, project = _detect_task(f)
        assert task == "what is asyncio"
        assert route == "FAST"

    def test_task_route_uppercased(self, tmp_path):
        f = tmp_path / "job.task"
        f.write_text("task: write code\nroute: coder\n")
        task, route, project = _detect_task(f)
        assert route == "CODER"

    def test_task_malformed_falls_back(self, tmp_path):
        f = tmp_path / "bad.task"
        f.write_text("not valid yaml or json: {{{{")
        task, route, project = _detect_task(f)
        # falls back to raw content
        assert task

    def test_ts_file_detected_as_code(self, tmp_path):
        f = tmp_path / "component.ts"
        f.write_text("export const x = 1;")
        task, route, project = _detect_task(f)
        assert route == "CODER"


class TestSaveOutput:
    def test_creates_output_file(self, tmp_path):
        source = tmp_path / "input.txt"
        source.write_text("test")
        import watch
        orig_base = watch.OUTPUT_BASE
        watch.OUTPUT_BASE = tmp_path / "output"
        try:
            _save_output(source, "test task", "test result")
            # Find output file
            out_files = list((tmp_path / "output").rglob("*.md"))
            assert len(out_files) == 1
            content = out_files[0].read_text()
            assert "test result" in content
            assert "test task" in content
        finally:
            watch.OUTPUT_BASE = orig_base

    def test_output_contains_source_name(self, tmp_path):
        source = tmp_path / "myfile.txt"
        source.write_text("x")
        import watch
        orig_base = watch.OUTPUT_BASE
        watch.OUTPUT_BASE = tmp_path / "output"
        try:
            _save_output(source, "task", "output")
            out_files = list((tmp_path / "output").rglob("*.md"))
            assert "myfile" in out_files[0].name
        finally:
            watch.OUTPUT_BASE = orig_base
