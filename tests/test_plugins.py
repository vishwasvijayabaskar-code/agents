"""Tests for plugin loader."""

import os
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.plugins import PluginDefinition, get_plugin_nodes, get_plugin_routes, load_plugins


def _write_plugin(directory: Path, filename: str, content: str):
    path = directory / filename
    path.write_text(textwrap.dedent(content))
    return path


class TestPluginDefinition:
    def test_name_uppercased(self):
        defn = PluginDefinition(name="translator", node_fn=lambda s: s)
        assert defn.name == "TRANSLATOR"

    def test_invalid_name_raises(self):
        with pytest.raises(ValueError):
            PluginDefinition(name="my-plugin", node_fn=lambda s: s)


class TestLoadPlugins:
    def test_loads_valid_plugin(self, tmp_path):
        _write_plugin(
            tmp_path,
            "myplugin.py",
            """
            from helpers.plugins import PluginDefinition

            def my_node(state):
                return state

            def register():
                return PluginDefinition(name="MYPLUGIN", node_fn=my_node, description="test plugin")
        """,
        )

        with patch("helpers.plugins.PLUGINS_DIR", tmp_path):
            loaded = load_plugins()

        assert "MYPLUGIN" in loaded
        assert loaded["MYPLUGIN"]["description"] == "test plugin"

    def test_skips_file_without_register(self, tmp_path):
        _write_plugin(tmp_path, "noop.py", "x = 1\n")

        with patch("helpers.plugins.PLUGINS_DIR", tmp_path):
            loaded = load_plugins()

        assert "NOOP" not in loaded

    def test_skips_dunder_files(self, tmp_path):
        _write_plugin(
            tmp_path,
            "__init__.py",
            "from helpers.plugins import PluginDefinition\ndef register(): return PluginDefinition('X', lambda s: s)\n",
        )

        with patch("helpers.plugins.PLUGINS_DIR", tmp_path):
            loaded = load_plugins()

        assert len(loaded) == 0

    def test_handles_broken_plugin_gracefully(self, tmp_path):
        _write_plugin(tmp_path, "broken.py", "raise RuntimeError('oops')\n")

        with patch("helpers.plugins.PLUGINS_DIR", tmp_path):
            # Should not raise, just skip
            loaded = load_plugins()

        assert len(loaded) == 0

    def test_missing_plugins_dir_returns_empty(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist"
        with patch("helpers.plugins.PLUGINS_DIR", nonexistent):
            loaded = load_plugins()
        assert loaded == {}

    def test_register_returns_wrong_type_skipped(self, tmp_path):
        _write_plugin(tmp_path, "wrong.py", "def register(): return 'not a PluginDefinition'\n")

        with patch("helpers.plugins.PLUGINS_DIR", tmp_path):
            loaded = load_plugins()

        assert len(loaded) == 0
