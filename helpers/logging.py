"""Lightweight verbose logging (Task 12).

Off by default. Enable with `enable_verbose()` (the --verbose CLI flag) or by
setting AGENTS_VERBOSE=1. When on, `vlog()` writes structured, timestamped
diagnostics to stderr so they never pollute normal stdout output.
"""

import os
import sys
import time

_state = {"enabled": os.getenv("AGENTS_VERBOSE", "") not in ("", "0", "false", "False")}


def enable_verbose(on: bool = True):
    """Turn verbose logging on/off for this process."""
    _state["enabled"] = on


def is_verbose() -> bool:
    return _state["enabled"]


def vlog(msg: str, *, tag: str = "agents"):
    """Write a diagnostic line to stderr when verbose is enabled. No-op otherwise."""
    if not _state["enabled"]:
        return
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [{tag}] {msg}", file=sys.stderr, flush=True)
