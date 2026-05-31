"""
MCP server for the multi-agent system.
Exposes run_task, search_memory, list_sessions, get_stats as tools.

Usage:
    python3 mcp_server.py           # stdio transport (default, for Claude Desktop)
    python3 mcp_server.py --sse     # SSE transport on port 8001

Add to Claude Desktop config (~/.claude/claude_desktop_config.json):
{
  "mcpServers": {
    "agents": {
      "command": "python3",
      "args": ["/path/to/agents/mcp_server.py"],
      "env": {}
    }
  }
}
"""

import argparse
import json
import pickle
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Add agents dir to path so imports work
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

from helpers.config import cfg

BASE_DIR = Path(__file__).parent
SESSIONS_DIR = BASE_DIR / "sessions"
USAGE_FILE = BASE_DIR / "usage.jsonl"

mcp = FastMCP(
    "agents",
    instructions=(
        "Multi-agent AI system. Use run_task to execute tasks with automatic routing. "
        "Use search_memory to find past results. list_sessions shows saved conversations. "
        "get_stats shows today's token usage."
    ),
)


# ---------------------------------------------------------------------------
# Tool: run_task
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Run a task through the multi-agent system. The orchestrator automatically "
        "routes to the best agent (CODER, RESEARCHER, FAST, CLAUDE, CODEX, EXECUTOR). "
        "Use route to force a specific agent. Returns the result string."
    )
)
def run_task(
    task: str,
    route: str | None = None,
    project_path: str | None = None,
) -> str:
    """
    Execute a task through the multi-agent graph.

    Args:
        task: The task or question to process.
        route: Optional agent override — CODER | RESEARCHER | FAST | CLAUDE | CODEX | EXECUTOR
        project_path: Optional path to a codebase to load as context.

    Returns:
        The agent's result as a string.
    """
    # Import lazily so server starts fast even if ollama not running
    from main import run as _run

    valid_routes = {"CODER", "RESEARCHER", "FAST", "CLAUDE", "CODEX", "EXECUTOR"}
    force_route = route.upper() if route else None
    if force_route and force_route not in valid_routes:
        return f"Error: invalid route '{route}'. Valid: {', '.join(sorted(valid_routes))}"

    try:
        result = _run(
            task=task,
            force_route=force_route,
            project_path=project_path,
        )
        return result.get("result") or "(no result)"
    except Exception as e:
        return f"Error running task: {e}"


# ---------------------------------------------------------------------------
# Tool: search_memory
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Search past task results using semantic similarity (ChromaDB). "
        "Returns the most relevant past results for a query."
    )
)
def search_memory(query: str, top_k: int = 5) -> str:
    """
    Semantic search over stored task history.

    Args:
        query: What to search for.
        top_k: Number of results to return (default 5, max 20).

    Returns:
        Formatted string of matching past results.
    """
    try:
        from helpers.memory import _relevant_memory

        results = _relevant_memory(query, k=min(top_k, 20))
        if not results:
            return "No matching memories found."
        return results
    except Exception as e:
        return f"Error searching memory: {e}"


# ---------------------------------------------------------------------------
# Tool: list_sessions
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "List all saved REPL sessions. Returns session IDs, task counts, and the most recent task in each session."
    )
)
def list_sessions() -> str:
    """
    List all saved sessions from the sessions/ directory.

    Returns:
        Formatted table of sessions.
    """
    if not SESSIONS_DIR.exists():
        return "No sessions directory found."

    session_files = sorted(SESSIONS_DIR.glob("*.pkl"), reverse=True)
    if not session_files:
        return "No saved sessions."

    lines = [f"{'Session ID':<22} {'Tasks':>5}  Last task"]
    lines.append("-" * 70)
    for path in session_files[:20]:  # cap at 20
        try:
            with open(path, "rb") as f:
                history: list[dict] = pickle.load(f)
            last = history[-1]["task"][:50] if history else "(empty)"
            lines.append(f"{path.stem:<22} {len(history):>5}  {last}")
        except Exception:
            lines.append(f"{path.stem:<22}  ????  (unreadable)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: get_stats
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Get today's token usage statistics, broken down by agent and model. "
        "Pass a date string (YYYY-MM-DD) to query a specific day."
    )
)
def get_stats(date: str | None = None) -> str:
    """
    Return token usage for a given date.

    Args:
        date: Date in YYYY-MM-DD format. Defaults to today.

    Returns:
        Formatted usage summary.
    """
    target = date or datetime.now().strftime("%Y-%m-%d")

    if not USAGE_FILE.exists():
        return f"No usage data for {target}."

    totals: dict[str, dict] = {}
    with open(USAGE_FILE) as f:
        for line in f:
            try:
                e = json.loads(line)
                if e.get("date") == target:
                    key = f"{e['agent']} ({e['model'].split('/')[-1]})"
                    totals.setdefault(key, {"prompt": 0, "completion": 0})
                    totals[key]["prompt"] += e.get("prompt_tokens", 0)
                    totals[key]["completion"] += e.get("completion_tokens", 0)
            except Exception:
                continue

    if not totals:
        return f"No usage data for {target}."

    lines = [f"Token usage — {target}", "", f"{'Agent':<30} {'Prompt':>8} {'Completion':>10} {'Total':>8}"]
    lines.append("-" * 60)
    grand = {"prompt": 0, "completion": 0}
    for agent, counts in sorted(totals.items()):
        p, c = counts["prompt"], counts["completion"]
        grand["prompt"] += p
        grand["completion"] += c
        lines.append(f"{agent:<30} {p:>8,} {c:>10,} {p + c:>8,}")
    lines.append("-" * 60)
    lines.append(
        f"{'TOTAL':<30} {grand['prompt']:>8,} {grand['completion']:>10,} {grand['prompt'] + grand['completion']:>8,}"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: list_models
# ---------------------------------------------------------------------------


@mcp.tool(description="List all currently configured models for each agent node.")
def list_models() -> str:
    """Return current model assignments for all nodes."""
    models = cfg.list_models()
    lines = [f"{'Node':<15} Model"]
    lines.append("-" * 50)
    for node, model in sorted(models.items()):
        lines.append(f"{node:<15} {model}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-agent MCP server")
    parser.add_argument(
        "--sse",
        action="store_true",
        help="Use SSE transport instead of stdio (runs on port 8001)",
    )
    parser.add_argument("--port", type=int, default=8001, help="SSE port (default 8001)")
    args = parser.parse_args()

    if args.sse:
        print(f"Starting MCP server (SSE) on port {args.port}...", file=sys.stderr)
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
