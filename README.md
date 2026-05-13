# agents

Local multi-agent AI orchestration system built on LangGraph + LiteLLM + Ollama.

## Architecture

```
ORCHESTRATOR (qwen3:32b)
    ├── CODER        — code generation, web design         (qwen2.5-coder:32b)
    ├── RESEARCHER   — research + web search + page fetch  (deepseek-r1:14b)
    ├── FAST         — quick answers, summaries            (qwen2.5:7b)
    ├── EXECUTOR     — runs shell commands, self-fixes     (qwen2.5-coder:32b)
    ├── CODEX        — autonomous multi-file builds        (Codex CLI subprocess)
    ├── CLAUDE       — deep reasoning, large code tasks    (claude-sonnet-4-6)
    └── SYNTHESIZE   — merges outputs from multi-agent chains
```

Plugins in `plugins/` register additional agents automatically.

## Features

- **Streaming output** — tokens stream live to terminal via Rich TUI
- **Fast-path routing** — tasks <150 chars skip the orchestrator LLM entirely (saves 10-15s latency)
- **Auto-escalation** — complex code tasks escalate CODER → CLAUDE automatically
- **Multi-turn chat** — `--chat` / `/chat` keeps conversation history across turns with the same agent
- **Web page fetcher** — RESEARCHER fetches and reads full article content (robots.txt aware)
- **REPL mode** — persistent sessions with `history`, `save`, `/model`, `/chat` commands
- **Model hot-swap** — change any agent's model at runtime: `/model coder ollama/deepseek-coder-v2:33b`
- **Codebase context** — `--project <path>` embeds relevant source files into agent prompts
- **Vector memory** — ChromaDB semantic search over all past tasks
- **Session memory** — anaphora detection ("add to it", "fix this") injects prior context
- **Shell execution** — EXECUTOR runs code, captures stdout/stderr, retries on failure
- **Security** — EXECUTOR blocks dangerous patterns (`rm -rf`, `sudo`, pipe-to-shell, etc.)
- **Plugin system** — drop a `.py` file in `plugins/`, implement `register()` — agent auto-loads
- **MCP server** — expose agents as an MCP tool server for Claude Desktop / other clients
- **Token tracker** — per-agent usage logged to `usage.jsonl`, view with `--stats`
- **macOS notifications** — `--notify` pings when long tasks finish
- **Session save/resume** — `--resume <id>` restores a previous REPL session
- **config.yaml** — non-secret settings in repo; `.env` holds only API keys

## Setup

### Prerequisites

```bash
brew install ollama
ollama serve                  # must be running

ollama pull qwen3:32b
ollama pull qwen2.5-coder:32b
ollama pull deepseek-r1:14b
ollama pull qwen2.5:7b

pip install -r requirements.txt
```

### Config

Non-secret settings live in `config.yaml` (already in repo). Only secrets go in `.env`:

```bash
cp .env.example .env
```

```env
# Only required entries — all else configured in config.yaml
ANTHROPIC_API_KEY=sk-ant-...   # required for CLAUDE node
OLLAMA_API_BASE=http://localhost:11434
```

Model overrides (optional — config.yaml defaults are used otherwise):
```env
CODER_MODEL=ollama/qwen2.5-coder:32b
RESEARCHER_MODEL=ollama/deepseek-r1:14b
FAST_MODEL=ollama/qwen2.5:7b
ORCHESTRATOR_MODEL=ollama/qwen3:32b
CLAUDE_MODEL=claude-sonnet-4-6
```

## Usage

```bash
# One-shot task (orchestrator auto-routes)
./run "explain how bubble sort works"

# Force a specific agent (skip orchestrator)
./run --route CODER "build a login page in Flask"
./run --route CLAUDE "architect a scalable microservices auth system"
./run --route RESEARCHER "compare React vs Vue in 2026"

# Multi-turn chat mode (follow-ups stay with same agent)
./run --chat "explain quicksort"
# then type follow-ups, /done to exit

# REPL (interactive multi-turn session)
./run

# With codebase context
./run --project ~/myproject "how does auth work here?"

# Resume saved session
./run --resume 20240511_223000

# macOS notification on finish
./run --notify "build me a flask todo app"

# Today's token usage
./run --stats
```

### REPL Commands

Inside the REPL (`./run` with no task):

| Command | Action |
|---------|--------|
| `exit` / `quit` | Save and exit |
| `history` | Show tasks this session |
| `save` | Save session now |
| `stats` | Today's token usage |
| `models` | List current model for each agent |
| `/model <node> <model>` | Hot-swap model for a node |
| `/chat [task]` | Start multi-turn chat mode |

**Model hot-swap example:**
```
>>> /model coder ollama/deepseek-coder-v2:33b
coder → ollama/deepseek-coder-v2:33b
```

### Routing

| Trigger | Agent |
|---------|-------|
| Short task (<150 chars), no multi-hop signal | Fast-pathed to FAST/CODER/RESEARCHER without LLM |
| Code task with "complex", "scalable", "production", "architect" | Auto-escalated CODER → CLAUDE |
| Multi-hop ("research and build", "then", "step 1 / step 2") | Full orchestrator LLM |
| `--route <AGENT>` | Forced, no orchestrator |

## Plugin System

Drop a `.py` file in `plugins/`. It auto-loads on startup — no config needed.

```python
# plugins/my_agent.py
from helpers.plugins import PluginDefinition
from helpers.llm import _call_stream
from helpers.config import cfg
from ui import print_agent_header

def my_node(state):
    model = cfg.model("fast")
    print_agent_header("MY_AGENT", model)
    result = _call_stream(model, "You are a specialist.", state["task"], agent="MY_AGENT")
    state["agent_outputs"]["MY_AGENT"] = result
    state["result"] = result
    return state

def register():
    return PluginDefinition(
        name="MY_AGENT",
        node_fn=my_node,
        description="Does something specialized. Use when task involves X.",
    )
```

The orchestrator LLM automatically learns the plugin description and can route to it.

## MCP Server

Expose agents as an MCP tool server for Claude Desktop or other MCP clients:

```bash
# stdio (for Claude Desktop)
python3 mcp_server.py

# SSE on port 8001
python3 mcp_server.py --sse
```

**Claude Desktop config** (`~/.claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "agents": {
      "command": "python3",
      "args": ["/path/to/agents/mcp_server.py"]
    }
  }
}
```

**Available tools:** `run_task`, `search_memory`, `list_sessions`, `get_stats`, `list_models`

## Tests

```bash
pip install pytest pytest-mock
python3 -m pytest tests/ -v
```

80 tests — covers routing logic, fast-path heuristics, escalation, synthesizer, plugin loader, config, executor security, and HTML stripping. No Ollama required (all LLM calls mocked).

## Project Structure

```
agents/
├── nodes/
│   ├── orchestrator.py  # Fast-path routing + LLM orchestration + escalation
│   ├── coder.py         # Code generation
│   ├── researcher.py    # Research + DuckDuckGo + full-page fetch
│   ├── fast.py          # Quick answers
│   ├── executor.py      # Shell execution (deny-listed, sandboxed to output/)
│   ├── codex.py         # Codex CLI subprocess
│   ├── claude.py        # Claude Code CLI or Anthropic API fallback
│   └── synthesizer.py   # Merges multi-agent outputs into unified result
├── helpers/
│   ├── llm.py           # LiteLLM streaming + token logging + multi-turn messages
│   ├── memory.py        # ChromaDB vector memory
│   ├── search.py        # DuckDuckGo search + page fetch + HTML stripper
│   ├── files.py         # Code block extraction → file output
│   ├── session.py       # Session context + anaphora detection
│   ├── project.py       # Codebase context loader
│   ├── usage.py         # Token usage JSONL logger
│   ├── config.py        # config.yaml loader + env-var override singleton
│   └── plugins.py       # Plugin loader (scan plugins/, call register())
├── plugins/
│   └── translator.py    # Example plugin: TRANSLATOR agent
├── tests/
│   ├── test_routing.py  # fast-path, escalation, route_decision, synthesize trigger
│   ├── test_agents.py   # fast, coder, executor, orchestrator node tests
│   ├── test_synthesizer.py
│   ├── test_plugins.py
│   ├── test_config.py
│   └── test_search.py
├── config.yaml          # Non-secret settings (models, limits, executor, researcher)
├── mcp_server.py        # FastMCP server — run_task, search_memory, etc.
├── graph.py             # LangGraph StateGraph wiring + plugin node registration
├── main.py              # Entry point, REPL, CLI, chat mode
├── state.py             # Shared AgentState TypedDict
├── ui.py                # Rich TUI helpers
├── run                  # ./run <task> bash wrapper
└── requirements.txt
```
