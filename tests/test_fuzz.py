"""Property/fuzz tests for parsers — random + adversarial inputs must never crash."""
import json
import random
import string
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.delegation import parse_delegation, strip_delegation_tags
from helpers.files import _write_files
from watch import _detect_task

random.seed(1337)


def _rand_text(n=200):
    alphabet = string.printable + "<>{}[]`\"'\\/\n\t"
    return "".join(random.choice(alphabet) for _ in range(random.randint(0, n)))


_EDGE_INPUTS = [
    "",
    " ",
    "\n\n\n",
    "<delegate>",
    "<delegate agent=>",
    '<delegate agent="">',
    '<delegate agent="X">',
    '<delegate agent="X"></delegate>',
    "```",
    "```python",
    "```python\n",
    "**a.py**",
    "**a.py**\n```\n",
    "### .py\n```\n```",
    "{",
    "{}",
    '{"route":}',
    '{"route": "CODER"',
    "null",
    "\x00\x01\x02",
    "𝕦𝕟𝕚𝕔𝕠𝕕𝕖 🎉",
    "a" * 10000,
]


class TestParseDelegationFuzz:
    def test_random_never_crashes(self):
        for _ in range(500):
            out = parse_delegation(_rand_text())
            assert out is None or (isinstance(out, tuple) and len(out) == 2)

    def test_edge_inputs(self):
        for s in _EDGE_INPUTS:
            out = parse_delegation(s)
            assert out is None or isinstance(out, tuple)

    def test_strip_always_returns_str(self):
        for _ in range(300):
            s = _rand_text()
            assert isinstance(strip_delegation_tags(s), str)
        for s in _EDGE_INPUTS:
            assert isinstance(strip_delegation_tags(s), str)


class TestWriteFilesFuzz:
    def test_random_never_crashes(self, tmp_path):
        for _ in range(300):
            out = _write_files(_rand_text(), str(tmp_path))
            assert isinstance(out, list)

    def test_edge_inputs(self, tmp_path):
        for s in _EDGE_INPUTS:
            out = _write_files(s, str(tmp_path))
            assert isinstance(out, list)

    def test_no_path_traversal(self, tmp_path):
        """Filenames in code blocks must not write outside output_dir."""
        outside = tmp_path / "outside.txt"
        content = "**../outside.txt**\n```\nPWNED\n```"
        _write_files(content, str(tmp_path / "work"))
        assert not outside.exists(), "path traversal: file written outside output_dir"


class TestDetectTaskFuzz:
    def test_random_content_never_crashes(self, tmp_path):
        for i in range(200):
            for ext in (".txt", ".md", ".task", ".url", ".py", ".js"):
                f = tmp_path / f"f{i}{ext}"
                try:
                    f.write_text(_rand_text())
                except (OSError, ValueError):
                    continue
                task, route, project = _detect_task(f)
                assert isinstance(task, str)
                assert route is None or isinstance(route, str)
                assert project is None or isinstance(project, str)


class TestRouteJsonParseFuzz:
    def test_orchestrator_json_extraction_robust(self):
        """The route-JSON regex+json.loads pattern in orchestrator must tolerate junk."""
        import re

        for _ in range(300):
            raw = _rand_text()
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            m = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
            if m:
                try:
                    json.loads(m.group())
                except (json.JSONDecodeError, ValueError):
                    pass  # expected for junk — must not propagate as crash
