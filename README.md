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

pip install langgraph litellm rich chromadb sentence-transformers ddgs python-dotenv anthropic
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

## Files

| File | Purpose |
|------|---------|
| `agents.py` | All agent node implementations + helpers |
| `graph.py` | LangGraph wiring, conditional routing |
| `main.py` | Entry point, REPL, memory, CLI flags |
| `state.py` | Shared TypedDict state |
| `ui.py` | Rich TUI helpers |
| `run` | Bash wrapper (`./run <task>`) |
