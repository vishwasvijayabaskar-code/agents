# Architecture

How **agents** works under the hood. ~3k lines, built on [LangGraph](https://github.com/langchain-ai/langgraph) (state graph) + [LiteLLM](https://github.com/BerriAI/litellm) (model abstraction) + [ChromaDB](https://www.trychroma.com/) (memory/cache).

## High level

```
                          ┌──────────────────┐
   task ───────────────►  │   ORCHESTRATOR   │ ◄──────────────┐
                          │  (routing brain) │                │
                          └────────┬─────────┘                │
                                   │ route                    │ loop back
                 ┌─────────┬───────┼────────┬─────────┐       │ (multi-hop)
                 ▼         ▼       ▼        ▼         ▼        │
              FAST     CODER  RESEARCHER  CLAUDE   EXECUTOR ───┘
                 │         │       │        │         │
                 └─────────┴───┬───┴────────┴─────────┘
                               ▼
                          SYNTHESIZE (merge multi-agent outputs)
                               ▼
                              END
```

Built-in worker nodes: `FAST`, `CODER`, `RESEARCHER`, `CLAUDE`, `EXECUTOR`, `CODEX`, `CODEBASE`. Plus `SYNTHESIZE` (merger) and any plugins in `plugins/`.

## Request lifecycle

1. **Entry** — `main.run()` builds the graph (`graph.build_graph()`), constructs the initial `AgentState`, and invokes it inside a `token_budget()` context.
2. **Orchestrator** (`nodes/orchestrator.py`) decides the next move on each entry. It runs through these tiers in order:
   - **Cache check** — `helpers/memory._cache_lookup()`; near-identical recent task short-circuits with the cached result.
   - **Forced route** — `--route AGENT` bypasses all routing logic.
   - **Subtask execution** — if a decomposition exists, dispatch the next subtask.
   - **Fast-path** — short/simple tasks (`_fast_route`) skip the orchestrator LLM entirely (saves ~10s of model load + inference).
   - **Multi-hop decomposition** — tasks like "research X then build Y" (`_is_multi_hop`) are decomposed into a subtask list and executed in sequence, piping each output into the next.
   - **Delegation post-processing** — if a worker's output contains a `<delegate agent="...">` tag, run that agent inline and inject the result back (`helpers/delegation.py`).
   - **Confidence escalation** — a single weak worker output (`_score_output` < 5) escalates FAST→CODER→CLAUDE. Skipped for fast-pathed or forced-route tasks.
   - **LLM routing** — anything ambiguous goes to the orchestrator model for a JSON routing decision.
3. **Worker node** runs, streams tokens (`helpers/llm._call_stream`), writes to `state["agent_outputs"][NAME]` and `state["result"]`, appends a `history` entry.
4. **Loop back** — every worker edge returns to the orchestrator (`graph.py`), enabling multi-hop chains. `route_decision()` decides whether to continue, synthesize, or end. Hard iteration cap prevents runaway loops.
5. **Synthesize** — if more than one worker ran, `SYNTHESIZE` merges their outputs into one coherent result.
6. **Exit** — `main.run()` records the result into vector memory (`_embed_memory`), writes any generated files (`output/`), and returns.

## State shape

`AgentState` (`state.py`) is the single dict threaded through every node:

| Field | Purpose |
|-------|---------|
| `task` | The user prompt |
| `route` | Next agent to run (set by orchestrator) |
| `result` | Latest / final output |
| `history` | Human-readable trace of every routing decision |
| `iterations` | Loop counter (drives the iteration cap) |
| `done` | Terminate flag |
| `agent_outputs` | `{AGENT_NAME: output}` for every worker that ran |
| `output_dir` | Where generated files are written |
| `memory` / `session_history` | Vector + session context injected into prompts |
| `project_context` / `project_context_path` | Codebase context (`--project`) for CODEBASE agent |
| `force_route` | `--route` override |
| `chat_messages` | Multi-turn conversation history (`--chat`) |
| `tokens_used` | Cumulative spend (budget enforcement) |
| `subtasks` / `current_subtask` | Decomposition state |

## Key subsystems

- **LLM layer** (`helpers/llm.py`) — `_call` (blocking) and `_call_stream` (token streaming). Thread-local context managers provide `stream_callback()` (for web SSE) and `token_budget()` (for spend enforcement) without threading state through every signature. `TokenBudgetExceeded` is raised when a task exceeds `limits.max_tokens_per_task`.
- **Memory + cache** (`helpers/memory.py`) — ChromaDB stores every completed task. `_relevant_memory()` injects semantically similar past tasks as context; `_cache_lookup()` short-circuits near-duplicate queries (cosine distance ≤ 0.15).
- **Codebase index** (`helpers/codebase.py`) — one ChromaDB collection per project, chunked by function/class for Python and fixed-size for others. Powers the CODEBASE agent.
- **Config** (`helpers/config.py`) — `config.yaml` singleton with env-var override. Models hot-swappable at runtime via `cfg.set_model()`.
- **Plugins** (`helpers/plugins.py`) — scans `plugins/`, calls each module's `register()`, registers the node + its routing description with the graph and orchestrator.

## Surfaces

The same core is exposed three ways:
- **CLI / REPL** — `main.py` (`./run`)
- **Web UI** — `web/app.py` (FastAPI + SSE token streaming, cookie auth, per-session history)
- **MCP server** — `mcp_server.py` (exposes `run_task`, `search_memory`, etc. to Claude Desktop / MCP clients)

## Where to extend

- **New agent** → add a plugin in `plugins/` (no core changes). See `plugins/translator.py`.
- **New routing rule** → `nodes/orchestrator.py` (`_fast_route`, `_is_multi_hop`, or the LLM routing prompt).
- **New config knob** → `config.yaml` + read via `cfg.get(section, key, default)`.
- **New surface** → reuse `main.run()` / `graph.build_graph()`; both web and MCP servers do exactly this.
