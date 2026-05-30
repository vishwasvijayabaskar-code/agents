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
from helpers import _load_project_context, _embed_memory, cfg
from helpers.llm import token_budget, get_budget_used, TokenBudgetExceeded
from ui import console, print_task_header, print_separator, print_agents_used, print_files, show_stats_table

OUTPUT_BASE = Path(__file__).parent / "output"
SESSIONS_DIR = Path(__file__).parent / "sessions"
USAGE_FILE = Path(__file__).parent / "usage.jsonl"

MAX_TASK_CHARS = cfg.get("limits", "max_task_chars", 10_000)

def check_ollama_health():
    """Check if Ollama is running and required models are available."""
    import urllib.request
    try:
        base = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
        req = urllib.request.Request(f"{base}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        available = {m["name"] for m in data.get("models", [])}
        required_envs = ["ORCHESTRATOR_MODEL", "CODER_MODEL", "RESEARCHER_MODEL", "FAST_MODEL"]
        missing = []
        for env in required_envs:
            model = os.getenv(env, "")
            if model.startswith("ollama/"):
                model_name = model.replace("ollama/", "")
                if model_name not in available and f"{model_name}:latest" not in available:
                    missing.append(model_name)
        if missing:
            console.print(f"[bold yellow]Warning: models not pulled: {', '.join(missing)}[/bold yellow]")
            console.print(f"[info]Run: ollama pull {'  &&  ollama pull '.join(missing)}[/info]")
    except Exception:
        console.print(f"[bold red]Ollama not reachable at {base}[/bold red]")
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
        console.print(f"[bold yellow]Session '{session_id}' not found.[/bold yellow]")
        return []
    with open(path, 'rb') as f:
        return pickle.load(f)

def notify(message: str):
    try:
        os.system(f'osascript -e \'display notification "{message}" with title "Agent"\' 2>/dev/null')
    except Exception:
        pass

def run(
    task: str,
    session_history: list[dict] = None,
    project_path: str = None,
    notify_done: bool = False,
    force_route: str = None,
    chat_messages: list[dict] = None,
):
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

    max_tokens = cfg.get("limits", "max_tokens_per_task", 0)

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
        "chat_messages": chat_messages or [],
        "tokens_used": 0,
        "subtasks": None,
        "current_subtask": 0,
        "project_context_path": str(Path(project_path).resolve()) if project_path else None,
    }

    print_task_header(task)
    with token_budget(max_tokens):
        try:
            result = graph.invoke(state)
        except TokenBudgetExceeded:
            console.print("[bold yellow][Budget exceeded — returning partial result][/bold yellow]")
            result = state
            if not result.get("result"):
                # Grab whatever output exists
                outputs = result.get("agent_outputs") or {}
                result["result"] = list(outputs.values())[-1] if outputs else "[Budget exceeded before any agent completed]"
            result["result"] = (result.get("result") or "") + "\n\n[Token budget exceeded]"
        result["tokens_used"] = get_budget_used()

    agents_used = list(result.get("agent_outputs", {}).keys())
    print_separator()
    print_agents_used(agents_used)
    if max_tokens > 0:
        console.print(f"[info]Tokens: {result['tokens_used']}/{max_tokens}[/info]")

    ts = datetime.now().isoformat()
    _embed_memory(task, result["result"] or "", agents_used, ts)

    out_path = Path(output_dir)
    if out_path.exists() and any(out_path.iterdir()):
        print_files(output_dir)

    if notify_done:
        notify(f"Done: {task[:60]}")

    return result


def chat_mode(
    initial_task: str,
    session_history: list[dict] = None,
    project_path: str = None,
    force_route: str = None,
):
    """Multi-turn conversation with a single agent. /done to exit."""
    console.print("[info]Chat mode — follow-ups stay with same agent. '/done' to exit.[/info]")
    messages = []  # conversation history: [{"role": "user"|"assistant", "content": "..."}]

    task = initial_task
    while True:
        result = run(
            task,
            session_history=session_history,
            project_path=project_path,
            force_route=force_route,
            chat_messages=messages,
        )
        assistant_reply = result.get("result") or ""
        # Append turn to messages history
        messages.append({"role": "user", "content": task})
        messages.append({"role": "assistant", "content": assistant_reply})

        try:
            follow_up = input("\n[chat]>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[info]Chat ended.[/info]")
            break
        if not follow_up or follow_up.lower() in ("/done", "exit", "quit"):
            console.print("[info]Chat ended.[/info]")
            break
        task = follow_up

    return messages


def repl(project_path: str = None, session_id: str = None, notify_done: bool = False):
    if session_id:
        session_history = load_session(session_id)
        console.print(f"[info]Resumed session '{session_id}' ({len(session_history)} past tasks)[/info]")
    else:
        session_history = []
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    console.print("[info]Agent REPL — commands: exit, history, save, stats, models, /model <node> <model>, /chat[/info]")
    if project_path:
        console.print(f"[info]Project: {project_path}[/info]")
    console.rule(style="separator")

    while True:
        try:
            task = input("\n>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[info]Exiting.[/info]")
            save_session(session_id, session_history)
            break

        if not task:
            continue

        # Built-in commands
        if task.lower() in ("exit", "quit", "q"):
            save_session(session_id, session_history)
            console.print(f"[info]Session saved: {session_id}[/info]")
            break

        if task.lower() == "history":
            if not session_history:
                console.print("[info]No tasks this session.[/info]")
            for i, h in enumerate(session_history):
                console.print(f"[info]{i+1}. [{' → '.join(h['agents'])}] {h['task']}[/info]")
            continue

        if task.lower() == "save":
            save_session(session_id, session_history)
            console.print(f"[info]Saved: {session_id}[/info]")
            continue

        if task.lower() == "stats":
            show_stats()
            continue

        # Memory search: memory <query>
        if task.lower().startswith("memory "):
            query = task[7:].strip()
            if query:
                from helpers.memory import _relevant_memory
                results = _relevant_memory(query)
                if results:
                    console.print(f"[info]{results}[/info]")
                else:
                    console.print("[info]No matching memories found.[/info]")
            else:
                console.print("[bold yellow]Usage: memory <query>[/bold yellow]")
            continue

        # Model listing: /models or models
        if task.lower() in ("models", "/models"):
            for node, model in cfg.list_models().items():
                console.print(f"[info]  {node:15} {model}[/info]")
            continue

        # Model hot-swap: /model <node> <model>
        if task.lower().startswith("/model "):
            parts = task.split(None, 2)
            if len(parts) != 3:
                console.print("[bold yellow]Usage: /model <node> <model>  e.g. /model coder ollama/deepseek-coder-v2:33b[/bold yellow]")
            else:
                node, model = parts[1].lower(), parts[2]
                valid_nodes = set(cfg.list_models().keys())
                if node not in valid_nodes:
                    console.print(f"[bold yellow]Unknown node '{node}'. Valid: {', '.join(sorted(valid_nodes))}[/bold yellow]")
                else:
                    cfg.set_model(node, model)
                    console.print(f"[info]{node} → {model}[/info]")
            continue

        # Chat mode: /chat [task]
        if task.lower().startswith("/chat"):
            remainder = task[5:].strip()
            initial = remainder or input("First message: ").strip()
            if initial:
                chat_mode(initial, session_history=session_history, project_path=project_path)
            continue

        result = run(task, session_history=session_history, project_path=project_path, notify_done=notify_done)
        session_history.append({
            "task": task,
            "result": (result.get("result") or "")[:cfg.get("limits", "session_result_chars", 3000)],
            "agents": list(result.get("agent_outputs", {}).keys()),
        })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-agent AI system")
    parser.add_argument("task", nargs="*", help="Task to run (omit for REPL)")
    parser.add_argument("--project", "-p", help="Path to project for codebase context")
    parser.add_argument("--resume", "-r", help="Resume a saved session by ID")
    parser.add_argument("--notify", "-n", action="store_true", help="macOS notification on completion")
    parser.add_argument("--route", help="Force route to agent: CODER, RESEARCHER, FAST, CLAUDE, CODEX, EXECUTOR")
    parser.add_argument("--chat", action="store_true", help="Multi-turn chat mode with same agent")
    parser.add_argument("--stats", "-s", action="store_true", help="Show today's token usage")
    parser.add_argument("--no-exec", action="store_true", help="Disable EXECUTOR node (shell commands won't run)")
    parser.add_argument("--watch", "-w", nargs="?", const="watch", metavar="DIR",
                        help="File-watcher mode: process files dropped into DIR (default: ./watch/)")
    parser.add_argument("--index", metavar="PATH",
                        help="Index a codebase for semantic search (use with --project)")
    parser.add_argument("--eval", nargs="*", metavar="TAG",
                        help="Run eval suite (optionally filter by tags: --eval coder fast)")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        sys.exit(0)

    if args.watch is not None:
        from watch import watch as _watch
        _watch(directory=args.watch if args.watch != "watch" else None)
        sys.exit(0)

    if args.index:
        from helpers.codebase import CodebaseIndex
        path = args.index
        console.print(f"[info]Indexing {path}...[/info]")
        idx = CodebaseIndex(path)
        n = idx.index(force=True)
        console.print(f"[bold green]Indexed {n} chunks from {path}[/bold green]")
        sys.exit(0)

    if args.eval is not None:
        from evals.runner import run_suite
        tags = args.eval if args.eval else None
        summary = run_suite(tags=tags)
        sys.exit(0 if summary.get("failed", 0) == 0 else 1)

    # Disable EXECUTOR if --no-exec flag is set
    if getattr(args, "no_exec", False):
        from helpers.config import cfg as _cfg
        if "executor" not in _cfg._data:
            _cfg._data["executor"] = {}
        _cfg._data["executor"]["enabled"] = False
        console.print("[bold yellow]EXECUTOR disabled (--no-exec)[/bold yellow]")

    check_ollama_health()

    # Validate --route if provided
    force_route = None
    if args.route:
        force_route = args.route.upper()
        valid_routes = {"CODER", "RESEARCHER", "FAST", "CLAUDE", "CODEX", "EXECUTOR", "CODEBASE"}
        if force_route not in valid_routes:
            console.print(f"[bold red]Invalid route: {args.route}. Valid: {', '.join(sorted(valid_routes))}[/bold red]")
            sys.exit(1)

    if args.task:
        task = " ".join(args.task)
        if args.chat:
            chat_mode(task, project_path=args.project, force_route=force_route)
        else:
            run(task, project_path=args.project, notify_done=args.notify, force_route=force_route)
    else:
        repl(project_path=args.project, session_id=args.resume, notify_done=args.notify)
