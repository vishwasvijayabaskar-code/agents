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

### pre-commit (optional but recommended)

```bash
pip install pre-commit
pre-commit install      # hooks now run on every commit
pre-commit run --all-files   # run once across the repo
```

Hooks: ruff (lint+fix), ruff-format, end-of-file-fixer, trailing-whitespace,
check-yaml, large-file + merge-conflict guards.

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

## Releasing (maintainers)

```bash
python -m build              # builds wheel + sdist into dist/
twine check dist/*           # validate metadata
# twine upload dist/*        # publish to PyPI (requires credentials)
```

The wheel bundles `web/templates/*.html`; the sdist also includes `config.yaml`
(via MANIFEST.in). Bump `version` in `pyproject.toml` + `__version__` in `main.py`
and add a `CHANGELOG.md` entry before tagging.

## Reporting bugs / requesting features

Use the issue templates. Include your OS, Python version, Ollama version, and the models configured in `config.yaml`.
