"""Tests for helpers/config.py — cfg singleton."""
import sys
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


SAMPLE_DATA = {
    "models": {
        "orchestrator": "ollama/qwen3:32b",
        "coder": "ollama/qwen2.5-coder:32b",
        "fast": "ollama/qwen2.5:7b",
        "claude": "claude-sonnet-4-6",
    },
    "limits": {
        "max_iterations": 3,
        "max_task_chars": 10000,
        "session_result_chars": 3000,
    },
    "executor": {
        "enabled": True,
        "timeout": 60,
        "blocked_patterns": ["rm -rf", "sudo"],
    },
    "researcher": {
        "max_search_results": 5,
        "max_page_fetches": 2,
        "max_page_chars": 5000,
    },
}


def _make_cfg(data: dict = None) -> object:
    """Return a fresh _Config instance with pre-loaded data (no file I/O)."""
    import copy
    from helpers.config import _Config
    instance = _Config.__new__(_Config)
    instance._data = copy.deepcopy(data or SAMPLE_DATA)
    return instance


class TestConfig:
    def test_get_limit(self):
        cfg = _make_cfg()
        assert cfg.get("limits", "max_iterations") == 3

    def test_get_default(self):
        cfg = _make_cfg()
        assert cfg.get("limits", "nonexistent_key", 99) == 99

    def test_model_returns_yaml_value(self):
        cfg = _make_cfg()
        # No env var set for coder → should return yaml value
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODER_MODEL", None)
            assert cfg.model("coder") == "ollama/qwen2.5-coder:32b"

    def test_model_env_overrides_yaml(self):
        cfg = _make_cfg()
        with patch.dict(os.environ, {"CODER_MODEL": "ollama/custom:latest"}):
            assert cfg.model("coder") == "ollama/custom:latest"

    def test_set_model_updates_runtime(self):
        cfg = _make_cfg()
        cfg.set_model("fast", "ollama/llama3.2:latest")
        # set_model writes to _data["models"]
        assert cfg._data["models"]["fast"] == "ollama/llama3.2:latest"

    def test_list_models_returns_dict(self):
        cfg = _make_cfg()
        models = cfg.list_models()
        assert isinstance(models, dict)
        assert "coder" in models
        assert "fast" in models

    def test_executor_blocked_patterns(self):
        cfg = _make_cfg()
        patterns = cfg.get("executor", "blocked_patterns", [])
        assert "rm -rf" in patterns

    def test_missing_yaml_falls_back_gracefully(self):
        """_Config with empty _data should not crash."""
        from helpers.config import _Config
        instance = _Config.__new__(_Config)
        instance._data = {}
        result = instance.model("fast")
        assert isinstance(result, str)
