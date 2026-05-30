"""
FastAPI web UI for the multi-agent system.
Features: task input, SSE streaming output, history view, stats,
          cookie-based session auth, per-session task history.

Run:
    python3 web/app.py              # http://localhost:8000
    uvicorn web.app:app --reload    # dev mode with auto-reload
"""
import os
import sys
import json
import secrets
import asyncio
import pickle
from pathlib import Path
from datetime import datetime
from typing import AsyncIterator

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# Add agents root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.config import cfg

BASE_DIR = Path(__file__).parent.parent
SESSIONS_DIR = BASE_DIR / "sessions"
USAGE_FILE = BASE_DIR / "usage.jsonl"
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

# Per-session in-memory task history: {session_id: [{"task", "result", "agents", "ts"}]}
_web_sessions: dict[str, list[dict]] = {}

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _auth_token() -> str:
    """Return configured auth token (empty = no auth)."""
    return cfg.get("web", "auth_token", "") or os.getenv("WEB_AUTH_TOKEN", "")

def _is_authenticated(request: Request) -> bool:
    token = _auth_token()
    if not token:
        return True  # no auth configured
    return request.session.get("authenticated") is True

def _require_auth(request: Request):
    """Raise redirect to /login if auth required and not authenticated."""
    if not _is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")


def _get_web_session_id(request: Request) -> str:
    """Get or create a stable session ID for this browser session."""
    sid = request.session.get("session_id")
    if not sid:
        sid = secrets.token_hex(16)
        request.session["session_id"] = sid
    return sid


app = FastAPI(title="agents", docs_url=None, redoc_url=None)

# Session middleware — use configured secret or generate one
_secret = cfg.get("web", "secret_key", "") or os.getenv("WEB_SECRET_KEY", "") or secrets.token_hex(32)
app.add_middleware(SessionMiddleware, secret_key=_secret, session_cookie="agents_session")

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
    """Run task in thread, stream tokens live via asyncio.Queue → SSE."""
    loop = asyncio.get_event_loop()
    token_queue: asyncio.Queue = asyncio.Queue()
    result_holder: dict = {}

    def _token_cb(delta: str):
        """Called from worker thread — safely push token to async queue."""
        loop.call_soon_threadsafe(token_queue.put_nowait, delta)

    def _run_in_thread():
        from main import run as _run
        from helpers.llm import stream_callback
        try:
            force_route = route.upper() if route else None
            with stream_callback(_token_cb):
                result = _run(task=task, force_route=force_route)
            result_holder["result"] = result.get("result") or ""
            result_holder["agents"] = list((result.get("agent_outputs") or {}).keys())
        except Exception as e:
            result_holder["error"] = str(e)
        finally:
            # Signal queue consumer that task is done
            loop.call_soon_threadsafe(token_queue.put_nowait, None)

    # Start task in thread pool
    loop.run_in_executor(None, _run_in_thread)

    yield "event: start\ndata: {}\n\n"

    # Drain tokens from queue as they arrive
    while True:
        token = await token_queue.get()
        if token is None:
            break  # thread finished
        payload = json.dumps({"token": token})
        yield f"event: token\ndata: {payload}\n\n"

    # Send final result with agents list
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

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    if _is_authenticated(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        request=request, name="login.html",
        context={"error": error, "auth_required": bool(_auth_token())},
    )


@app.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    token = _auth_token()
    if not token:
        # Auth not configured — just mark authenticated
        request.session["authenticated"] = True
        return RedirectResponse(url="/", status_code=302)
    if secrets.compare_digest(password, token):
        request.session["authenticated"] = True
        return RedirectResponse(url="/", status_code=302)
    return RedirectResponse(url="/login?error=Invalid+password", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not _is_authenticated(request):
        if _auth_token():
            return RedirectResponse(url="/login", status_code=302)
    sid = _get_web_session_id(request)
    session_tasks = _web_sessions.get(sid, [])
    models = cfg.list_models()
    return templates.TemplateResponse(
        request=request, name="index.html",
        context={"models": models, "session_tasks": session_tasks, "auth_enabled": bool(_auth_token())},
    )


@app.post("/run")
async def run_task(
    request: Request,
    task: str = Form(...),
    route: str = Form(default=""),
):
    """Run a task and stream back SSE events."""
    if not _is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")

    route_val = route.strip().upper() if route.strip() else None
    valid_routes = {"CODER", "RESEARCHER", "FAST", "CLAUDE", "CODEX", "EXECUTOR", "CODEBASE", ""}
    if route_val and route_val not in valid_routes:
        return HTMLResponse(f"Invalid route: {route}", status_code=400)

    sid = _get_web_session_id(request)

    async def _sse_with_history():
        result_captured = {"result": "", "agents": []}
        async for chunk in _run_task_sse(task, route_val):
            yield chunk
            # Capture result event
            if chunk.startswith("event: result"):
                try:
                    data_line = chunk.split("data: ", 1)[1].strip()
                    payload = json.loads(data_line)
                    result_captured["result"] = payload.get("result", "")
                    result_captured["agents"] = payload.get("agents", [])
                except Exception:
                    pass
        # Record in web session history
        if task:
            _web_sessions.setdefault(sid, []).append({
                "task": task,
                "result": result_captured["result"][:500],
                "agents": result_captured["agents"],
                "ts": datetime.now().isoformat(),
            })
            # Keep last 50 tasks per session
            _web_sessions[sid] = _web_sessions[sid][-50:]

    return StreamingResponse(
        _sse_with_history(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    sessions = _load_history()
    return templates.TemplateResponse(request=request, name="history.html", context={"sessions": sessions})


@app.get("/stats", response_class=HTMLResponse)
async def stats(request: Request, date: str | None = None):
    if not _is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    target = date or datetime.now().strftime("%Y-%m-%d")
    rows = _load_stats(target)
    total_tokens = sum(r["prompt"] + r["completion"] for r in rows)
    return templates.TemplateResponse(
        request=request,
        name="stats.html",
        context={"rows": rows, "date": target, "total_tokens": total_tokens},
    )


@app.get("/api/session-history")
async def api_session_history(request: Request):
    """Return current browser session's task history."""
    if not _is_authenticated(request):
        raise HTTPException(status_code=401)
    sid = _get_web_session_id(request)
    return {"tasks": _web_sessions.get(sid, [])}


@app.get("/api/models")
async def api_models():
    return cfg.list_models()


@app.post("/api/model")
async def api_set_model(request: Request):
    """Hot-swap a model: {"node": "coder", "model": "ollama/deepseek-coder:33b"}"""
    body = await request.json()
    node = body.get("node", "").lower()
    model = body.get("model", "").strip()
    valid_nodes = set(cfg.list_models().keys())
    if node not in valid_nodes:
        return {"error": f"Unknown node '{node}'. Valid: {', '.join(sorted(valid_nodes))}"}
    if not model:
        return {"error": "model is required"}
    cfg.set_model(node, model)
    return {"ok": True, "node": node, "model": model}


@app.get("/models", response_class=HTMLResponse)
async def models_page(request: Request):
    models = cfg.list_models()
    return templates.TemplateResponse(request=request, name="models.html", context={"models": models})


@app.get("/api/graph")
async def api_graph():
    """Return mermaid diagram string for the agent graph."""
    from helpers.plugins import load_plugins, get_plugin_routes
    load_plugins()
    plugin_routes = get_plugin_routes()

    lines = ["graph TD"]
    lines.append("    START([Start]) --> orchestrator")
    workers = ["CODER", "RESEARCHER", "FAST", "CODEX", "CLAUDE", "EXECUTOR"]
    for w in workers:
        lines.append(f"    orchestrator -->|route={w}| {w}")
        lines.append(f"    {w} --> orchestrator")
    for p in plugin_routes:
        lines.append(f"    orchestrator -->|route={p}| {p}")
        lines.append(f"    {p} --> orchestrator")
    lines.append("    orchestrator -->|done| SYNTHESIZE")
    lines.append("    orchestrator -->|done| END([End])")
    lines.append("    SYNTHESIZE --> END")
    # Styling
    lines.append("    style orchestrator fill:#58a6ff,color:#0d1117")
    lines.append("    style SYNTHESIZE fill:#7ee787,color:#0d1117")
    return {"mermaid": "\n".join(lines)}


@app.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request):
    return templates.TemplateResponse(request=request, name="graph.html", context={})


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
