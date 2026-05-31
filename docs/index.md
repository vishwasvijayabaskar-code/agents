# agents

> Local multi-agent AI orchestration. Research → code → execute — fully automated, fully offline.

Built on LangGraph + LiteLLM + Ollama. No API keys required for local models.

## Quickstart

```bash
git clone https://github.com/vishwasvijayabaskar-code/agents.git
cd agents && ./install.sh
./run --doctor
./run "explain how a hash map works"
```

## What it does

Give it a task; the orchestrator routes to the right agent(s), chains them, and
returns a result. Agents can decompose multi-hop tasks, delegate to each other
mid-task, and escalate weak answers to stronger models — all on local models.

- **Agents:** FAST, CODER, RESEARCHER, EXECUTOR, CLAUDE, CODEX, CODEBASE, SYNTHESIZE
- **Surfaces:** CLI/REPL, Web UI (live streaming), MCP server
- **Safety:** token budgets, EXECUTOR deny-list, result caching

See the [Architecture](architecture.md) page for how it works, the
[Configuration](config.md) reference for settings, and
[Contributing](contributing.md) to hack on it.

## Links

- Source: [github.com/vishwasvijayabaskar-code/agents](https://github.com/vishwasvijayabaskar-code/agents)
- License: MIT
