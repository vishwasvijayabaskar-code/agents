# agents

Local multi-agent AI orchestration system built on LangGraph + LiteLLM + Ollama.

## Architecture

```
ORCHESTRATOR (qwen3:32b)
    ├── CODER        — code generation, web design         (qwen2.5-coder:32b)
    ├── RESEARCHER   — research + DuckDuckGo web search    (deepseek-r1:14b)
    ├── FAST         — quick answers, summaries            (qwen2.5:7b)
    ├── EXECUTOR     — runs shell commands, self-fixes     (qwen2.5-coder:32b)
    ├── CODEX        — autonomous multi-file builds        (Codex CLI subprocess)
    └── CLAUDE       — deep reasoning                      (claude-sonnet-4-6)
```

Every worker loops back to the orchestrator. Router forces `__end__` once a worker has produced output — no double-firing.

## Features

- **Streaming output** — tokens stream live to terminal
- **REPL mode** — persistent multi-turn session with `history` / `save` commands
- **Codebase context** — `--project <path>` loads your files into agent prompts
- **Vector memory** — ChromaDB semantic search over past tasks
- **Session memory** — anaphora detection ("add to it", "fix this") injects prior result
- **Shell execution** — EXECUTOR node runs code, captures stdout/stderr, retries on failure
- **Token tracker** — logs usage per agent/model to `usage.jsonl`, view with `--stats`
- **macOS notifications** — `--notify` pings when long tasks finish
- **Session save/resume** — `--resume <id>` restores a previous REPL session
- **Rich TUI** — colored agent headers, syntax-highlighted code blocks, stats table

## Setup

### Prerequisites

```bash
brew install ollama
ollama pull qwen3:32b
ollama pull qwen2.5-coder:32b
ollama pull deepseek-r1:14b
ollama pull qwen2.5:7b

pip install -r requirements.txt
```

### Config

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

```env
ORCHESTRATOR_MODEL=ollama/qwen3:32b
CODER_MODEL=ollama/qwen2.5-coder:32b
RESEARCHER_MODEL=ollama/deepseek-r1:14b
FAST_MODEL=ollama/qwen2.5:7b
OLLAMA_API_BASE=http://localhost:11434
CLAUDE_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...   # optional — only needed for CLAUDE node
```

## Usage

```bash
# One-shot task
./run "explain how bubble sort works"

# Force a specific agent (skip orchestrator)
./run --route CODER "build a login page"
./run --route CLAUDE "design a scalable auth system"
./run --route RESEARCHER "compare React vs Vue in 2026"

# REPL (multi-turn session)
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

### Routing

Short tasks (<150 chars) with no multi-hop keywords are fast-routed without calling the orchestrator LLM — eliminating 10-15s of latency. Complex code tasks are auto-escalated from CODER to CLAUDE. Use `--route` to override.

## Project Structure

```
agents/
├── nodes/               # Agent node implementations
│   ├── orchestrator.py  # Task routing + route_decision logic
│   ├── coder.py         # Code generation
│   ├── researcher.py    # Research + web search
│   ├── fast.py          # Quick answers
│   ├── executor.py      # Shell command execution (sandboxed)
│   ├── codex.py         # Codex CLI subprocess
│   └── claude.py        # Claude API integration
├── helpers/             # Shared utilities
│   ├── llm.py           # LLM call + streaming
│   ├── memory.py        # ChromaDB vector memory
│   ├── search.py        # DuckDuckGo web search
│   ├── files.py         # Code block file extraction
│   ├── session.py       # Session context + anaphora detection
│   ├── project.py       # Codebase context loader
│   └── usage.py         # Token usage logging
├── graph.py             # LangGraph wiring
├── main.py              # Entry point, REPL, CLI
├── state.py             # Shared TypedDict state
├── ui.py                # Rich TUI helpers
├── run                  # Bash wrapper (./run <task>)
└── requirements.txt     # Pinned dependencies
```
