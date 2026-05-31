import re
from pathlib import Path


def _safe_target(output_dir: str, filename: str) -> Path | None:
    """Resolve filename under output_dir, rejecting path traversal.
    Returns a safe absolute Path inside output_dir, or None if the name
    escapes the directory (e.g. ``../etc/passwd`` or an absolute path)."""
    base = Path(output_dir).resolve()
    candidate = (base / filename).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None  # escapes output_dir — reject
    return candidate


def _write_files(content: str, output_dir: str) -> list[str]:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    written = []

    # Try filename headers: **filename.ext** or ### filename.ext
    named_pattern = re.compile(r"(?:\*\*([^*\n]+\.\w+)\*\*|###\s+([^\n]+\.\w+))\s*\n```(?:\w+)?\n(.*?)```", re.DOTALL)
    matches = list(named_pattern.finditer(content))

    if matches:
        for m in matches:
            filename = (m.group(1) or m.group(2)).strip()
            code = m.group(3)
            path = _safe_target(output_dir, filename)
            if path is None:
                continue  # skip path-traversal attempts
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                f.write(code)
            written.append(filename)
    else:
        lang_map = {
            "html": "index.html",
            "css": "styles.css",
            "javascript": "script.js",
            "js": "script.js",
            "python": "output.py",
            "py": "output.py",
            "typescript": "output.ts",
            "ts": "output.ts",
        }
        lang_pattern = re.compile(r"```(\w+)\n(.*?)```", re.DOTALL)
        seen = set()
        for m in lang_pattern.finditer(content):
            lang = m.group(1).lower()
            filename = lang_map.get(lang, f"output.{lang}")
            if filename in seen:
                continue
            seen.add(filename)
            path = _safe_target(output_dir, filename)
            if path is None:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                f.write(m.group(2))
            written.append(filename)

    return written
