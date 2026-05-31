# Contributing

Thanks for your interest in improving **agents**. This is a small, hackable codebase — you can read the whole thing in an afternoon. PRs welcome.

## Dev setup

```bash
git clone https://github.com/vishwasvijayabaskar-code/agents.git
cd agents
pip install -r requirements.txt

# Install Ollama + pull at least the fast + coder models
brew install ollama        # or https://ollama.com
ollama serve
ollama pull qwen2.5:7b
ollama pull qwen2.5-coder:32b
```

Optional: copy `.env.example` to `.env` if you want the CLAUDE node (needs `ANTHROPIC_API_KEY`).

## Running

```bash
./run "explain how a hash map works"   # one-shot
./run                                  # REPL
python3 web.py                         # web UI at :8000
```

## Tests

All LLM calls are mocked — **tests run without Ollama**.

```bash
pip install pytest pytest-mock
python3 -m pytest tests/ -q
```

Every PR must keep the full suite green. New code needs new tests.

## Linting

```bash
pip install ruff
ruff check .
ruff check --fix .   # autofix
```

CI runs both tests and ruff on every push/PR.

## Code style

- Standard library + the deps already in `requirements.txt`. Don't add heavy deps without discussion.
- Worker nodes follow one shape: take `AgentState`, write to `state["agent_outputs"][NAME]` and `state["result"]`, append a `history` entry, wrap the body in `try/except` that writes an `[NAME error: ...]` message. See `nodes/fast.py` for the minimal pattern.
- Stream output via `helpers.llm._call_stream` (not silent `_call`) so the TUI and web UI show live tokens.
- Keep secrets in `.env`. Non-secret settings go in `config.yaml`.

## Adding an agent (plugin)

Drop a `.py` file in `plugins/` with a `register()` returning a `PluginDefinition`. The orchestrator learns its description and routes to it automatically — no core changes needed. Full example in the README "Plugin system" section and `plugins/translator.py`.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the request lifecycle, state shape, and routing tiers.

## PR checklist

- [ ] `python3 -m pytest tests/ -q` passes
- [ ] `ruff check .` clean
- [ ] New behavior has tests
- [ ] Docs updated if you changed CLI flags, config keys, or agent behavior
- [ ] Commit messages are descriptive

## Reporting bugs / requesting features

Use the issue templates. Include your OS, Python version, Ollama version, and the models configured in `config.yaml`.
