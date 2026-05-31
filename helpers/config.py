"""
Central config loader. config.yaml sets defaults; env vars always take precedence.
Usage:
    from helpers.config import cfg
    model = cfg.model("coder")
    timeout = cfg.get("executor", "timeout", 60)
"""

import os
from pathlib import Path

import yaml

_CONFIG_FILE = Path(__file__).parent.parent / "config.yaml"


def _load() -> dict:
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}


class _Config:
    def __init__(self):
        self._data = _load()

    def reload(self):
        self._data = _load()

    def get(self, section: str, key: str, default=None):
        return self._data.get(section, {}).get(key, default)

    def model(self, key: str) -> str:
        """Get model for a node. Env var takes precedence over config.yaml."""
        env_map = {
            "orchestrator": "ORCHESTRATOR_MODEL",
            "coder": "CODER_MODEL",
            "researcher": "RESEARCHER_MODEL",
            "fast": "FAST_MODEL",
            "claude": "CLAUDE_MODEL",
        }
        env_key = env_map.get(key)
        if env_key:
            val = os.getenv(env_key)
            if val:
                return val
        return self.get("models", key) or "ollama/llama3.2"

    def set_model(self, key: str, value: str):
        """Hot-swap model for a node at runtime."""
        if "models" not in self._data:
            self._data["models"] = {}
        self._data["models"][key] = value
        # Also update env var so all callers see the change immediately
        env_map = {
            "orchestrator": "ORCHESTRATOR_MODEL",
            "coder": "CODER_MODEL",
            "researcher": "RESEARCHER_MODEL",
            "fast": "FAST_MODEL",
            "claude": "CLAUDE_MODEL",
        }
        env_key = env_map.get(key)
        if env_key:
            os.environ[env_key] = value

    def list_models(self) -> dict:
        env_map = {
            "orchestrator": "ORCHESTRATOR_MODEL",
            "coder": "CODER_MODEL",
            "researcher": "RESEARCHER_MODEL",
            "fast": "FAST_MODEL",
            "claude": "CLAUDE_MODEL",
        }
        result = {}
        for key, env_key in env_map.items():
            result[key] = os.getenv(env_key) or self.get("models", key) or "ollama/llama3.2"
        return result

    def validate(self) -> tuple[list[str], list[str]]:
        """Validate config.yaml structure. Returns (errors, warnings).

        Errors are fatal (bad types that break runtime). Warnings are
        non-fatal (unknown keys, missing optional sections).
        """
        errors: list[str] = []
        warnings: list[str] = []
        data = self._data or {}

        # models section: values must be non-empty strings
        models = data.get("models", {})
        if models and not isinstance(models, dict):
            errors.append("'models' must be a mapping")
        elif isinstance(models, dict):
            for k, v in models.items():
                if not isinstance(v, str) or not v.strip():
                    errors.append(f"models.{k} must be a non-empty string (got {v!r})")

        # limits section: known keys must be numeric
        numeric_limits = (
            "max_iterations",
            "max_task_chars",
            "session_result_chars",
            "project_max_bytes",
            "max_tokens_per_task",
            "cache_ttl_hours",
            "llm_retries",
        )
        limits = data.get("limits", {})
        if limits and not isinstance(limits, dict):
            errors.append("'limits' must be a mapping")
        elif isinstance(limits, dict):
            for k in numeric_limits:
                if k not in limits:
                    continue
                v = limits[k]
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    errors.append(f"limits.{k} must be a number (got {v!r})")

        # executor section
        ex = data.get("executor", {})
        if isinstance(ex, dict):
            if "enabled" in ex and not isinstance(ex["enabled"], bool):
                errors.append(f"executor.enabled must be true/false (got {ex['enabled']!r})")
            if "timeout" in ex and (not isinstance(ex["timeout"], (int, float)) or isinstance(ex["timeout"], bool)):
                errors.append(f"executor.timeout must be a number (got {ex['timeout']!r})")
            if "blocked_patterns" in ex and not isinstance(ex["blocked_patterns"], list):
                errors.append("executor.blocked_patterns must be a list")
        elif ex:
            errors.append("'executor' must be a mapping")

        # Unknown top-level sections → warning
        known_sections = {"models", "limits", "executor", "researcher", "web"}
        for section in data:
            if section not in known_sections:
                warnings.append(f"unknown config section '{section}' (ignored)")

        return errors, warnings


cfg = _Config()
