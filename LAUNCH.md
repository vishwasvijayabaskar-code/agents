# Launch notes

Repo: https://github.com/vishwasvijayabaskar-code/agents

## r/LocalLLaMA post

**Title:**
> I built a local multi-agent system where agents delegate to each other mid-task — fully offline on Ollama

**Body:**

Been hacking on this for a few weeks. It's a multi-agent orchestrator that runs entirely on local Ollama models — no API keys, no cloud, nothing leaves your machine (unless you opt into a Claude fallback node).

The part I'm most happy with: **agents can delegate to each other mid-task.** If the CODER agent needs API docs, it emits a `<delegate agent="RESEARCHER">...</delegate>` tag, the orchestrator runs the researcher inline, injects the result back, and the coder keeps going. No manual chaining.

What it does:
- **Orchestrator** routes each task to the right agent (FAST / CODER / RESEARCHER / CLAUDE / EXECUTOR)
- **Task decomposition** — "research X then build Y" auto-splits into subtasks, pipes output between them
- **Confidence escalation** — weak FAST answer auto-escalates to a bigger model
- **Fast-path** — short/simple tasks skip the orchestrator LLM entirely (no 10s routing latency)
- **Codebase agent** — index a repo into ChromaDB, ask questions about it semantically
- **File-watcher** — drop a file into `watch/`, agents process it automatically
- **Token budgets** — hard cap per task so a runaway chain can't burn your machine for 20 min
- **Result caching** — semantically similar queries return cached answers
- **Web UI** with live token streaming + an MCP server so you can plug it into Claude Desktop

Stack: LangGraph (state graph) + LiteLLM (model abstraction) + ChromaDB (memory/cache). ~3k lines, 210 tests, all mocked so they run without Ollama.

Default model setup:
- orchestrator: qwen3:32b
- coder: qwen2.5-coder:32b
- researcher: deepseek-r1:14b
- fast: qwen2.5:7b

All swappable at runtime (`/model coder ...`) or in `config.yaml`.

Repo (MIT): https://github.com/vishwasvijayabaskar-code/agents

Feedback welcome — especially on the delegation protocol and what agent types you'd want added.

---

## Subreddit checklist
- [ ] r/LocalLLaMA — primary, best fit
- [ ] r/selfhosted — angle: "self-hosted AI agent runner, no cloud"
- [ ] r/Python — angle: clean LangGraph architecture, hackable
- [ ] Hacker News "Show HN" — title: "Show HN: Local multi-agent AI that delegates between agents, offline on Ollama"

## Pre-post checklist
- [x] Repo public
- [x] README with demo GIF
- [x] LICENSE (MIT)
- [x] CI green badge
- [ ] Add repo topics/tags on GitHub (ai-agents, ollama, langgraph, local-llm, multi-agent)
- [ ] Add repo description + website field on GitHub
