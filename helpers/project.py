import fnmatch
import re
from pathlib import Path

_BINARY_EXTS = {'.png','.jpg','.jpeg','.gif','.ico','.svg','.woff','.ttf','.eot','.mp4','.mp3','.zip','.tar','.gz','.pdf','.pyc','.pyo','.so','.dylib','.lock'}
_SKIP_DIRS = {'.git','node_modules','__pycache__','.venv','venv','env','.env','dist','build','.next','coverage'}

def _load_project_context(project_path: str, task: str, max_total_bytes: int = 150_000, max_file_bytes: int = 40_000) -> str:
    """Walk project dir, return relevant files as formatted context block."""
    root = Path(project_path).expanduser().resolve()
    if not root.exists():
        return f"[Project path not found: {project_path}]"

    # Load .gitignore patterns
    gitignore_patterns = []
    gi = root / ".gitignore"
    if gi.exists():
        gitignore_patterns = [ln.strip() for ln in gi.read_text().splitlines() if ln.strip() and not ln.startswith("#")]

    def is_ignored(p: Path) -> bool:
        rel = str(p.relative_to(root))
        for pat in gitignore_patterns:
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(p.name, pat):
                return True
        return False

    # Score files by keyword relevance to task
    task_words = set(re.findall(r'\w+', task.lower()))
    def relevance(p: Path) -> int:
        name_words = set(re.findall(r'\w+', p.stem.lower()))
        return len(name_words & task_words)

    files = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in _BINARY_EXTS:
            continue
        if is_ignored(p):
            continue
        try:
            size = p.stat().st_size
            if size > max_file_bytes:
                continue
            files.append((relevance(p), p))
        except OSError:
            continue

    # Sort: relevant first, then by path
    files.sort(key=lambda x: (-x[0], str(x[1])))

    blocks = []
    total = 0
    for _, p in files:
        try:
            content = p.read_text(errors="replace")
            rel = p.relative_to(root)
            block = f"### {rel}\n```\n{content}\n```"
            if total + len(block) > max_total_bytes:
                break
            blocks.append(block)
            total += len(block)
        except OSError:
            continue

    if not blocks:
        return "[No readable files found in project]"
    return f"<project_files path=\"{root}\">\n" + "\n\n".join(blocks) + "\n</project_files>"
