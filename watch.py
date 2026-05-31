"""File-watcher mode (Option B).

Drop files into watch/ — agents process them automatically.

File formats:
  .txt / .md       Plain task text. Route auto-selected.
  .task            YAML/JSON: {task: "...", route: "CODER", project: "/path"}
  .py .js .ts .rs  Code review. Sent to CODER for review/improvements.
  .url             Single URL on line 1. RESEARCHER fetches + summarizes.

Processed files → watch/done/
Output → output/watched_<timestamp>/
"""

import shutil
import sys
import time
import warnings

warnings.simplefilter("ignore")
try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
    warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
except ImportError:
    pass

from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    print("watchdog not installed. Run: pip install watchdog")
    sys.exit(1)

from rich.console import Console
from rich.panel import Panel

console = Console()

WATCH_DIR = Path(__file__).parent / "watch"
DONE_DIR = WATCH_DIR / "done"
OUTPUT_BASE = Path(__file__).parent / "output"

# Extensions treated as code files → review task
_CODE_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go", ".java",
              ".cpp", ".c", ".rb", ".php", ".swift", ".kt"}

# Debounce: ignore files modified within N seconds of creation (partial writes)
_DEBOUNCE_SECS = 1.0

# Track files we've already queued (avoid duplicate events)
_seen: set[str] = set()


def _detect_task(path: Path) -> tuple[str, str | None, str | None]:
    """Parse file → (task_text, route, project_path). route/project may be None."""
    ext = path.suffix.lower()
    content = path.read_text(errors="replace").strip()

    # .task → YAML or JSON with explicit fields
    if ext == ".task":
        try:
            import yaml
            data = yaml.safe_load(content)
        except Exception:
            try:
                import json
                data = json.loads(content)
            except Exception:
                data = {}
        if isinstance(data, dict):
            task = data.get("task") or data.get("prompt") or content
            route = (data.get("route") or "").upper() or None
            project = data.get("project") or None
            return task, route, project
        return content, None, None

    # .url → research the URL
    if ext == ".url":
        url = content.split("\n")[0].strip()
        if not url:
            return "Summarize content at this URL (file was empty)", None, None
        return f"Fetch and summarize this URL: {url}", "RESEARCHER", None

    # Code files → review
    if ext in _CODE_EXTS:
        _LANG_NAMES = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".jsx": "jsx", ".tsx": "tsx", ".rs": "rust", ".go": "go",
            ".java": "java", ".cpp": "cpp", ".c": "c", ".rb": "ruby",
            ".php": "php", ".swift": "swift", ".kt": "kotlin",
        }
        lang = _LANG_NAMES.get(ext, ext.lstrip("."))
        return (
            f"Review this {lang} code. Identify bugs, improvements, and security issues. "
            f"Provide specific fixes.\n\n```{lang}\n{content}\n```"
        ), "CODER", None

    # .txt / .md / anything else → raw task text
    return content, None, None


def _process_file(path: Path):
    """Process one dropped file."""
    if not path.exists():
        return
    if path.stat().st_size == 0:
        console.print(f"[yellow]Skipping empty file: {path.name}[/yellow]")
        return

    console.print(Panel(f"[bold cyan]Watcher: processing {path.name}[/bold cyan]", expand=False))

    try:
        task, route, project = _detect_task(path)
    except Exception as e:
        console.print(f"[red]Failed to read {path.name}: {e}[/red]")
        _move_to_done(path, failed=True)
        return

    if not task:
        console.print(f"[yellow]No task found in {path.name}, skipping[/yellow]")
        _move_to_done(path, failed=True)
        return

    console.print(f"[info]Task: {task[:100]}{'...' if len(task) > 100 else ''}[/info]")
    if route:
        console.print(f"[info]Route: {route}[/info]")

    # Lazy import to avoid heavy startup cost when watchdog fires
    from main import run

    try:
        result = run(
            task=task,
            project_path=project,
            force_route=route,
        )
        output_text = result.get("result") or ""
        _save_output(path, task, output_text)
        console.print(f"[green]Done: {path.name}[/green]")
    except Exception as e:
        console.print(f"[red]Error processing {path.name}: {e}[/red]")
        _save_output(path, task, f"[Error: {e}]")

    _move_to_done(path)


def _save_output(source: Path, task: str, output: str):
    """Write result to output/watched_<timestamp>/<stem>.md"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_BASE / f"watched_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{source.stem}_result.md"
    out_file.write_text(
        f"# Task: {source.name}\n\n"
        f"**Input:** {task[:200]}{'...' if len(task) > 200 else ''}\n\n"
        f"**Generated:** {datetime.now().isoformat()}\n\n"
        f"---\n\n{output}\n"
    )
    try:
        display = out_file.relative_to(Path.cwd())
    except ValueError:
        display = out_file
    console.print(f"[info]Output → {display}[/info]")


def _move_to_done(path: Path, failed: bool = False):
    """Move processed file to watch/done/ (or watch/failed/)."""
    dest_dir = DONE_DIR / ("failed" if failed else "")
    if failed:
        dest_dir = WATCH_DIR / "failed"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{path.name}"
    try:
        shutil.move(str(path), str(dest))
    except Exception:
        pass  # file may have been deleted already


class _WatchHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        p = Path(event.src_path)
        # Skip hidden files, temp files, done/failed dirs
        if p.name.startswith(".") or p.name.startswith("~"):
            return
        if "done" in p.parts or "failed" in p.parts:
            return
        key = str(p.resolve())
        if key in _seen:
            return
        _seen.add(key)
        # Debounce — wait for file write to complete
        time.sleep(_DEBOUNCE_SECS)
        _process_file(p)


def watch(directory: Path | None = None, once: bool = False):
    """Start watching. Ctrl+C to stop."""
    watch_dir = Path(directory) if directory else WATCH_DIR
    watch_dir.mkdir(parents=True, exist_ok=True)
    DONE_DIR.mkdir(parents=True, exist_ok=True)

    # Process any files already sitting in watch/ on startup
    existing = [f for f in watch_dir.iterdir()
                if f.is_file() and not f.name.startswith(".")]
    if existing:
        console.print(f"[info]Processing {len(existing)} existing file(s)...[/info]")
        for f in existing:
            _process_file(f)
        if once:
            return

    console.print(Panel(
        f"[bold green]Watching {watch_dir}[/bold green]\n"
        "Drop files to process:\n"
        "  .txt / .md    → plain task text\n"
        "  .task         → YAML: {task, route, project}\n"
        "  .url          → fetch + summarize URL\n"
        "  .py .js .ts   → code review\n"
        "\nCtrl+C to stop",
        title="agents / watch mode",
        expand=False,
    ))

    handler = _WatchHandler()
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        observer.stop()
        console.print("\n[info]Watcher stopped.[/info]")
    observer.join()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="File-watcher mode — drop files, agents process them")
    parser.add_argument("--dir", "-d", help="Directory to watch (default: ./watch/)")
    parser.add_argument("--once", action="store_true", help="Process existing files and exit (no daemon)")
    args = parser.parse_args()
    watch(directory=args.dir, once=args.once)
