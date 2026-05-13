import warnings
import os
warnings.simplefilter("ignore")
# Must suppress before langgraph import — LangChainPendingDeprecationWarning bypasses -W ignore
try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
    warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
except ImportError:
    pass

import json
import sys
import argparse
import pickle
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from graph import build_graph
from helpers import _load_project_context, _embed_memory
from ui import console, print_task_header, print_separator, print_agents_used, print_files, show_stats_table

OUTPUT_BASE = Path(__file__).parent / "output"
SESSIONS_DIR = Path(__file__).parent / "sessions"
USAGE_FILE = Path(__file__).parent / "usage.jsonl"

MAX_TASK_CHARS = 10_000

def check_ollama_health():
    """Check if Ollama is running and required models are available."""
    import urllib.request
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        available = {m["name"] for m in data.get("models", [])}
        required_envs = ["ORCHESTRATOR_MODEL", "CODER_MODEL", "RESEARCHER_MODEL", "FAST_MODEL"]
        missing = []
        for env in required_envs:
            model = os.getenv(env, "")
            if model.startswith("ollama/"):
                model_name = model.replace("ollama/", "")
                # Check both exact and with :latest suffix
                if model_name not in available and f"{model_name}:latest" not in available:
                    missing.append(model_name)
        if missing:
            console.print(f"[bold yellow]Warning: models not pulled: {', '.join(missing)}[/bold yellow]")
            console.print(f"[info]Run: ollama pull {'  &&  ollama pull '.join(missing)}[/info]")
    except Exception:
        console.print("[bold red]Ollama not reachable at localhost:11434[/bold red]")
        console.print("[info]Start with: ollama serve[/info]")
        sys.exit(1)

def show_stats():
    if not USAGE_FILE.exists():
        console.print("[info]No usage data yet.[/info]")
        return
    today = datetime.now().strftime("%Y-%m-%d")
    totals = {}
    with open(USAGE_FILE) as f:
        for line in f:
            try:
                e = json.loads(line)
                if e.get("date") == today:
                    key = f"{e['agent']} ({e['model'].split('/')[-1]})"
                    totals[key] = totals.get(key, {"prompt": 0, "completion": 0})
                    totals[key]["prompt"] += e.get("prompt_tokens", 0)
                    totals[key]["completion"] += e.get("completion_tokens", 0)
            except Exception:
                continue
    show_stats_table(totals, today)

def save_session(session_id: str, session_history: list[dict]):
    SESSIONS_DIR.mkdir(exist_ok=True)
    path = SESSIONS_DIR / f"{session_id}.pkl"
    with open(path, 'wb') as f:
        pickle.dump(session_history, f)
    return path

def load_session(session_id: str) -> list[dict]:
    path = SESSIONS_DIR / f"{session_id}.pkl"
    if not path.exists():
        print(f"Session '{session_id}' not found.")
        return []
    with open(path, 'rb') as f:
        return pickle.load(f)

def notify(message: str):
    try:
        os.system(f'osascript -e \'display notification "{message}" with title "Agent"\' 2>/dev/null')
    except Exception:
        pass

def run(task: str, session_history: list[dict] = None, project_path: str = None, notify_done: bool = False, force_route: str = None):
    # Input validation
    if len(task) > MAX_TASK_CHARS:
        console.print(f"[bold yellow]Task truncated from {len(task)} to {MAX_TASK_CHARS} chars[/bold yellow]")
        task = task[:MAX_TASK_CHARS]

    graph = build_graph()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = str(OUTPUT_BASE / timestamp)

    project_ctx = None
    if project_path:
        console.print(f"[info]Loading project context from {project_path}...[/info]")
        project_ctx = _load_project_context(project_path, task)

    state = {
        "task": task,
        "route": None,
        "result": None,
        "history": [],
        "iterations": 0,
        "done": False,
        "agent_outputs": {},
        "output_dir": output_dir,
        "memory": [],
        "session_history": session_history or [],
        "project_context": project_ctx,
        "force_route": force_route,
    }

    print_task_header(task)
    result = graph.invoke(state)

    agents_used = list(result.get("agent_outputs", {}).keys())
    print_separator()
    print_agents_used(agents_used)

    ts = datetime.now().isoformat()
    _embed_memory(task, result["result"] or "", agents_used, ts)

    out_path = Path(output_dir)
    if out_path.exists() and any(out_path.iterdir()):
        print_files(output_dir)

    if notify_done:
        notify(f"Done: {task[:60]}")

    return result

def repl(project_path: str = None, session_id: str = None, notify_done: bool = False):
    if session_id:
        session_history = load_session(session_id)
        print(f"Resumed session '{session_id}' ({len(session_history)} past tasks)")
    else:
        session_history = []
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("Agent REPL — 'exit' to quit, 'history' for past tasks, 'save' to save session")
    if project_path:
        print(f"Project: {project_path}")
    print("─" * 50)

    while True:
        try:
            task = input("\n>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            save_session(session_id, session_history)
            break

        if not task:
            continue
        if task.lower() in ("exit", "quit", "q"):
            save_session(session_id, session_history)
            print(f"Session saved: {session_id}")
            break
        if task.lower() == "history":
            if not session_history:
                print("No tasks this session.")
            for i, h in enumerate(session_history):
                print(f"{i+1}. [{' → '.join(h['agents'])}] {h['task']}")
            continue
        if task.lower() == "save":
            save_session(session_id, session_history)
            print(f"Saved: {session_id}")
            continue
        if task.lower() == "stats":
            show_stats()
            continue

        result = run(task, session_history=session_history, project_path=project_path, notify_done=notify_done)
        session_history.append({
            "task": task,
            "result": (result.get("result") or "")[:3000],
            "agents": list(result.get("agent_outputs", {}).keys()),
        })

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-agent AI system")
    parser.add_argument("task", nargs="*", help="Task to run (omit for REPL)")
    parser.add_argument("--project", "-p", help="Path to project for codebase context")
    parser.add_argument("--resume", "-r", help="Resume a saved session by ID")
    parser.add_argument("--notify", "-n", action="store_true", help="macOS notification on completion")
    parser.add_argument("--route", help="Force route to agent: CODER, RESEARCHER, FAST, CLAUDE, CODEX, EXECUTOR")
    parser.add_argument("--stats", "-s", action="store_true", help="Show today's token usage")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        sys.exit(0)

    check_ollama_health()

    # Validate --route if provided
    force_route = None
    if args.route:
        force_route = args.route.upper()
        valid_routes = {"CODER", "RESEARCHER", "FAST", "CLAUDE", "CODEX", "EXECUTOR"}
        if force_route not in valid_routes:
            console.print(f"[bold red]Invalid route: {args.route}. Valid: {', '.join(sorted(valid_routes))}[/bold red]")
            sys.exit(1)

    if args.task:
        run(" ".join(args.task), project_path=args.project, notify_done=args.notify, force_route=force_route)
    else:
        repl(project_path=args.project, session_id=args.resume, notify_done=args.notify)
