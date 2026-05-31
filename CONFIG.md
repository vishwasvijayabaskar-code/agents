# Configuration reference

_Auto-generated from `config.yaml` by `scripts/gen_config_docs.py`. Do not edit by hand._

Settings live in `config.yaml`. Secrets go in `.env`. Environment variables override config.yaml.

## `models`

| Key | Default | Description |
|-----|---------|-------------|
| `orchestrator` | `'ollama/qwen3:32b'` | LLM for this node. `ollama/<model>` for local, or a hosted model id. |
| `coder` | `'ollama/qwen2.5-coder:32b'` | LLM for this node. `ollama/<model>` for local, or a hosted model id. |
| `researcher` | `'ollama/deepseek-r1:14b'` | LLM for this node. `ollama/<model>` for local, or a hosted model id. |
| `fast` | `'ollama/qwen2.5:7b'` | LLM for this node. `ollama/<model>` for local, or a hosted model id. |
| `claude` | `'claude-sonnet-4-6'` | LLM for this node. `ollama/<model>` for local, or a hosted model id. |

## `limits`

| Key | Default | Description |
|-----|---------|-------------|
| `max_iterations` | `3` | Max orchestrator loops before forcing done. |
| `max_task_chars` | `10000` | Tasks longer than this are truncated. |
| `session_result_chars` | `3000` | Per-task result length kept in session history. |
| `project_max_bytes` | `150000` | Cap on codebase context bytes injected into prompts. |
| `max_tokens_per_task` | `0` | Token budget per task; 0 = unlimited. |
| `cache_ttl_hours` | `24` | Result-cache freshness window; 0 = disable caching. |
| `llm_retries` | `2` | Retries on transient LLM errors (connection/timeout/5xx). |
| `save_traces` | `True` | Write replayable run traces to runs/ (--list-runs, --replay). |
| `fanout_workers` | `3` | Max concurrent workers for parallel fan-out tasks. |

## `executor`

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `True` | Allow the EXECUTOR node to run shell commands. |
| `repair` | `True` | On persistent command failure, ask CODER to fix and retry once. |
| `timeout` | `60` | Per-command timeout in seconds. |
| `blocked_patterns` | `8 items` | Substrings that block a command from running. |

## `researcher`

| Key | Default | Description |
|-----|---------|-------------|
| `max_search_results` | `5` | DuckDuckGo results fetched per query. |
| `max_page_fetches` | `2` | Pages fully fetched per research task. |
| `max_page_chars` | `5000` | Chars kept per fetched page. |
| `summarize_pages` | `True` | Summarize fetched pages with the fast model before injection. |

## `web`

| Key | Default | Description |
|-----|---------|-------------|
| `auth_token` | `''` | Login password for the web UI; empty = no auth. |
| `secret_key` | `''` | Session-cookie signing key; auto-generated if empty. |

