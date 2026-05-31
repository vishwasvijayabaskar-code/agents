#!/usr/bin/env python3
"""Generate CONFIG.md from config.yaml defaults + inline comments.

Run: python3 scripts/gen_config_docs.py
Keeps the settings reference in sync with the shipped config.yaml.
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
CONFIG = ROOT / "config.yaml"
OUT = ROOT / "CONFIG.md"

# Short human descriptions per key (kept here so the doc stays useful).
DESCRIPTIONS = {
    ("models", "*"): "LLM for this node. `ollama/<model>` for local, or a hosted model id.",
    ("limits", "max_iterations"): "Max orchestrator loops before forcing done.",
    ("limits", "max_task_chars"): "Tasks longer than this are truncated.",
    ("limits", "session_result_chars"): "Per-task result length kept in session history.",
    ("limits", "project_max_bytes"): "Cap on codebase context bytes injected into prompts.",
    ("limits", "max_tokens_per_task"): "Token budget per task; 0 = unlimited.",
    ("limits", "cache_ttl_hours"): "Result-cache freshness window; 0 = disable caching.",
    ("limits", "llm_retries"): "Retries on transient LLM errors (connection/timeout/5xx).",
    ("executor", "enabled"): "Allow the EXECUTOR node to run shell commands.",
    ("executor", "timeout"): "Per-command timeout in seconds.",
    ("executor", "blocked_patterns"): "Substrings that block a command from running.",
    ("researcher", "max_search_results"): "DuckDuckGo results fetched per query.",
    ("researcher", "max_page_fetches"): "Pages fully fetched per research task.",
    ("researcher", "max_page_chars"): "Chars kept per fetched page.",
    ("researcher", "summarize_pages"): "Summarize fetched pages with the fast model before injection.",
    ("web", "auth_token"): "Login password for the web UI; empty = no auth.",
    ("web", "secret_key"): "Session-cookie signing key; auto-generated if empty.",
}


def _describe(section: str, key: str) -> str:
    return DESCRIPTIONS.get((section, key)) or DESCRIPTIONS.get((section, "*")) or ""


def generate() -> str:
    data = yaml.safe_load(CONFIG.read_text()) or {}
    lines = [
        "# Configuration reference",
        "",
        "_Auto-generated from `config.yaml` by `scripts/gen_config_docs.py`. Do not edit by hand._",
        "",
        "Settings live in `config.yaml`. Secrets go in `.env`. Environment variables override config.yaml.",
        "",
    ]
    for section, body in data.items():
        lines.append(f"## `{section}`")
        lines.append("")
        if isinstance(body, dict):
            lines.append("| Key | Default | Description |")
            lines.append("|-----|---------|-------------|")
            for key, val in body.items():
                desc = _describe(section, key)
                shown = repr(val) if not isinstance(val, list) else f"{len(val)} items"
                lines.append(f"| `{key}` | `{shown}` | {desc} |")
        else:
            lines.append(f"`{body!r}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    new = generate()
    if "--check" in sys.argv:
        current = OUT.read_text() if OUT.exists() else ""
        if current.strip() != new.strip():
            print("CONFIG.md is out of date. Run: python3 scripts/gen_config_docs.py")
            return 1
        print("CONFIG.md up to date.")
        return 0
    OUT.write_text(new + "\n")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
