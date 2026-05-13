"""
Central config loader. config.yaml sets defaults; env vars always take precedence.
Usage:
    from helpers.config import cfg
    model = cfg.model("coder")
    timeout = cfg.get("executor", "timeout", 60)
"""
import os
import yaml
from pathlib import Path

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
            "coder":        "CODER_MODEL",
            "researcher":   "RESEARCHER_MODEL",
            "fast":         "FAST_MODEL",
            "claude":       "CLAUDE_MODEL",
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
            "coder":        "CODER_MODEL",
            "researcher":   "RESEARCHER_MODEL",
            "fast":         "FAST_MODEL",
            "claude":       "CLAUDE_MODEL",
        }
        env_key = env_map.get(key)
        if env_key:
            os.environ[env_key] = value

    def list_models(self) -> dict:
        env_map = {
            "orchestrator": "ORCHESTRATOR_MODEL",
            "coder":        "CODER_MODEL",
            "researcher":   "RESEARCHER_MODEL",
            "fast":         "FAST_MODEL",
            "claude":       "CLAUDE_MODEL",
        }
        result = {}
        for key, env_key in env_map.items():
            result[key] = os.getenv(env_key) or self.get("models", key) or "ollama/llama3.2"
        return result

cfg = _Config()
