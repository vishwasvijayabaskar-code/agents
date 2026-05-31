# Changelog

All notable changes to this project. Format based on
[Keep a Changelog](https://keepachangelog.com/); this project aims for
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Type checking with **mypy** (CI-enforced) and a **55% coverage** gate (pytest-cov).
- **ruff format** + **pre-commit** config for consistent style.
- Fuzz/property tests for parsers and **end-to-end** graph tests.
- `--doctor` (environment diagnostics) and `--init` (scaffold `.env` + model pulls).
- One-liner `install.sh`; optional shell completion (argcomplete).
- **Docs site** (mkdocs-material) with auto-generated `CONFIG.md`; GitHub Pages deploy.
- Advisory Docker lint CI (hadolint + compose validate).
- Wheel now bundles `web/templates` + `config.yaml` (sdist) — pip-installed web UI works.

### Fixed
- **mcp_server** crashed at import (`FastMCP(version=...)` unsupported) — the entire
  MCP server was broken.
- `search_memory` passed `n_results=` to `_relevant_memory` (expects `k=`) — guaranteed
  TypeError when the MCP search tool ran.
- **Path traversal** in `_write_files`: model output like `**../x**` could write outside
  `output_dir`; filenames are now confined to the output directory.
- `--route` forced tasks no longer auto-escalate via confidence scoring.
- CLAUDE node degrades gracefully (CLI → API → clear message) instead of crashing on a
  CLI 401.
- Eval runner persists results per-task and isolates per-task crashes.

## [0.1.0]

### Added
- Core multi-agent orchestration on LangGraph + LiteLLM + Ollama: orchestrator routing,
  FAST / CODER / RESEARCHER / EXECUTOR / CODEX / CLAUDE / SYNTHESIZE agents.
- Fast-path routing, multi-hop task decomposition, agent-to-agent delegation, confidence
  escalation, token budgets, ChromaDB vector memory + result caching.
- CODEBASE agent (semantic codebase index) and `--index`.
- File-watcher mode (`--watch`), eval harness (`--eval`), cache TTL + `--clear-cache`.
- Web UI (FastAPI + SSE token streaming, cookie auth, per-session history, health page,
  session export), MCP server, plugin system.
- Docker + docker-compose, CLI/REPL, multi-turn chat, `--stats`, `--version`,
  `--list-agents`, `--verbose`.

[Unreleased]: https://github.com/vishwasvijayabaskar-code/agents/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/vishwasvijayabaskar-code/agents/releases/tag/v0.1.0
