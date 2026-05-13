import json
from datetime import datetime
from pathlib import Path

_USAGE_FILE = Path(__file__).parent.parent / "usage.jsonl"

def _log_usage(agent: str, model: str, prompt_tokens: int, completion_tokens: int):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "agent": agent,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }
    try:
        with open(_USAGE_FILE, 'a') as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
