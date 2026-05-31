"""Tests for helpers/config.py — cfg singleton."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

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


class TestConfigValidation:
    def test_valid_config_no_errors(self):
        cfg = _make_cfg()
        errors, warnings = cfg.validate()
        assert errors == []

    def test_empty_config_valid(self):
        cfg = _make_cfg({})
        errors, warnings = cfg.validate()
        assert errors == []

    def test_empty_model_string_errors(self):
        cfg = _make_cfg({"models": {"coder": ""}})
        errors, _ = cfg.validate()
        assert any("models.coder" in e for e in errors)

    def test_non_string_model_errors(self):
        cfg = _make_cfg({"models": {"fast": 123}})
        errors, _ = cfg.validate()
        assert any("models.fast" in e for e in errors)

    def test_non_numeric_limit_errors(self):
        cfg = _make_cfg({"limits": {"max_iterations": "three"}})
        errors, _ = cfg.validate()
        assert any("limits.max_iterations" in e for e in errors)

    def test_bool_limit_rejected(self):
        cfg = _make_cfg({"limits": {"llm_retries": True}})
        errors, _ = cfg.validate()
        assert any("limits.llm_retries" in e for e in errors)

    def test_numeric_limit_ok(self):
        cfg = _make_cfg({"limits": {"max_tokens_per_task": 50000}})
        errors, _ = cfg.validate()
        assert errors == []

    def test_executor_enabled_must_be_bool(self):
        cfg = _make_cfg({"executor": {"enabled": "yes"}})
        errors, _ = cfg.validate()
        assert any("executor.enabled" in e for e in errors)

    def test_executor_timeout_must_be_numeric(self):
        cfg = _make_cfg({"executor": {"timeout": "60s"}})
        errors, _ = cfg.validate()
        assert any("executor.timeout" in e for e in errors)

    def test_blocked_patterns_must_be_list(self):
        cfg = _make_cfg({"executor": {"blocked_patterns": "rm -rf"}})
        errors, _ = cfg.validate()
        assert any("blocked_patterns" in e for e in errors)

    def test_unknown_section_warns_not_errors(self):
        cfg = _make_cfg({"bogus_section": {"x": 1}})
        errors, warnings = cfg.validate()
        assert errors == []
        assert any("bogus_section" in w for w in warnings)

    def test_web_section_known(self):
        cfg = _make_cfg({"web": {"auth_token": "secret"}})
        errors, warnings = cfg.validate()
        assert errors == []
        assert not any("web" in w for w in warnings)
