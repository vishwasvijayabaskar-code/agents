"""
FastAPI web UI for the multi-agent system.
Features: task input, SSE streaming output, history view, stats.

Run:
    python3 web/app.py              # http://localhost:8000
    uvicorn web.app:app --reload    # dev mode with auto-reload
"""
import sys
import json
import asyncio
import pickle
from pathlib import Path
from datetime import datetime
from typing import AsyncIterator

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Add agents root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.config import cfg

BASE_DIR = Path(__file__).parent.parent
SESSIONS_DIR = BASE_DIR / "sessions"
USAGE_FILE = BASE_DIR / "usage.jsonl"
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="agents", docs_url=None, redoc_url=None)

# Static files (CSS, JS)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_history() -> list[dict]:
    """Load all sessions, most recent first."""
    if not SESSIONS_DIR.exists():
        return []
    sessions = []
    for path in sorted(SESSIONS_DIR.glob("*.pkl"), reverse=True)[:20]:
        try:
            with open(path, "rb") as f:
                history: list[dict] = pickle.load(f)
            sessions.append({"id": path.stem, "tasks": history})
        except Exception:
            pass
    return sessions


def _load_stats(date: str | None = None) -> list[dict]:
    """Return list of {agent, model, prompt, completion} for given date."""
    target = date or datetime.now().strftime("%Y-%m-%d")
    if not USAGE_FILE.exists():
        return []
    totals: dict[str, dict] = {}
    with open(USAGE_FILE) as f:
        for line in f:
            try:
                e = json.loads(line)
                if e.get("date") == target:
                    key = f"{e['agent']} ({e['model'].split('/')[-1]})"
                    totals.setdefault(key, {"agent_model": key, "prompt": 0, "completion": 0})
                    totals[key]["prompt"] += e.get("prompt_tokens", 0)
                    totals[key]["completion"] += e.get("completion_tokens", 0)
            except Exception:
                pass
    rows = [{"agent_model": k, **v} for k, v in totals.items()]
    return sorted(rows, key=lambda r: r["prompt"] + r["completion"], reverse=True)


# ---------------------------------------------------------------------------
# SSE task runner
# ---------------------------------------------------------------------------

async def _run_task_sse(task: str, route: str | None) -> AsyncIterator[str]:
    """Run task in thread, yield SSE events as results arrive."""
    loop = asyncio.get_event_loop()

    # Patch _call_stream to yield tokens via queue
    token_queue: asyncio.Queue = asyncio.Queue()
    result_holder = {}

    def _run_in_thread():
        import threading
        from main import run as _run
        # Capture stdout tokens via LLM stream — run in thread pool
        try:
            force_route = route.upper() if route else None
            result = _run(task=task, force_route=force_route)
            result_holder["result"] = result.get("result") or ""
            result_holder["agents"] = list((result.get("agent_outputs") or {}).keys())
        except Exception as e:
            result_holder["error"] = str(e)
        finally:
            result_holder["done"] = True

    # Run in thread so we don't block the event loop
    thread_future = loop.run_in_executor(None, _run_in_thread)

    # Stream a "working" indicator while waiting
    agents_header_sent = set()
    yield "event: start\ndata: {}\n\n"

    while not result_holder.get("done"):
        await asyncio.sleep(0.3)
        yield f"event: ping\ndata: {{}}\n\n"

    await thread_future

    if "error" in result_holder:
        err = json.dumps({"error": result_holder["error"]})
        yield f"event: error\ndata: {err}\n\n"
    else:
        payload = {
            "result": result_holder.get("result", ""),
            "agents": result_holder.get("agents", []),
        }
        yield f"event: result\ndata: {json.dumps(payload)}\n\n"

    yield "event: done\ndata: {}\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    models = cfg.list_models()
    return templates.TemplateResponse(request=request, name="index.html", context={"models": models})


@app.post("/run")
async def run_task(
    task: str = Form(...),
    route: str = Form(default=""),
):
    """Run a task and stream back SSE events."""
    route_val = route.strip().upper() if route.strip() else None

    valid_routes = {"CODER", "RESEARCHER", "FAST", "CLAUDE", "CODEX", "EXECUTOR", ""}
    if route_val and route_val not in valid_routes:
        return HTMLResponse(f"Invalid route: {route}", status_code=400)

    return StreamingResponse(
        _run_task_sse(task, route_val),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    sessions = _load_history()
    return templates.TemplateResponse(request=request, name="history.html", context={"sessions": sessions})


@app.get("/stats", response_class=HTMLResponse)
async def stats(request: Request, date: str | None = None):
    target = date or datetime.now().strftime("%Y-%m-%d")
    rows = _load_stats(target)
    total_tokens = sum(r["prompt"] + r["completion"] for r in rows)
    return templates.TemplateResponse(
        request=request,
        name="stats.html",
        context={"rows": rows, "date": target, "total_tokens": total_tokens},
    )


@app.get("/api/models")
async def api_models():
    return cfg.list_models()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="agents web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    print(f"Starting agents web UI at http://{args.host}:{args.port}")
    uvicorn.run(
        "web.app:app" if args.reload else app,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
