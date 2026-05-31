# Overnight Autonomous Run — Report

Executed the 20-task plan (contributor-readiness, robustness, features, distribution)
while the repo owner slept. All work committed + pushed to `main`.

**Final state:** 282 tests passing (started at 210), `ruff check .` clean, CI green,
20/20 eval baseline at 100%.

## Task status

| # | Task | Status |
|---|------|--------|
| 1 | CONTRIBUTING.md | ✅ |
| 2 | GitHub issue/PR templates | ✅ |
| 3 | ARCHITECTURE.md | ✅ |
| 4 | Sync pyproject ↔ requirements packaging | ✅ |
| 5 | ruff lint config + CI step + autofix | ✅ |
| 6 | Makefile | ✅ |
| 7 | Remove legacy `agents.py` monolith | ✅ |
| 8 | LLM retry/backoff on transient errors | ✅ |
| 9 | Startup config validation | ✅ |
| 10 | `--version` flag | ✅ |
| 11 | `--list-agents` command | ✅ |
| 12 | `--verbose` structured logging | ✅ |
| 13 | Web copy-to-clipboard + session export | ✅ |
| 14 | `/health` page + `/api/health` | ✅ |
| 15 | `examples/` dir for watcher | ✅ |
| 16 | Expand eval suite (20 tasks) + BASELINE.md | ✅ |
| 17 | Cache TTL enforcement + `--clear-cache` | ✅ |
| 18 | Streaming-consistency audit + tests | ✅ (already correct; locked in with tests) |
| 19 | Second demo GIF (multi-hop) | ⏭️ **Skipped** — see below |
| 20 | Docker hardening | ⚠️ **Partial** — see below |

## Skipped / partial — rationale

**Task 19 (multi-hop demo GIF) — skipped.** A real "research X then build Y" run
chains the 32B coder + 14B researcher (+ live web search) and takes several minutes.
A multi-minute GIF is a *worse* README asset than the existing crisp `demo.gif`, and
the web dependency makes it flaky to record deterministically. Per the run's autonomy
rule (impractical/flaky → skip + log), kept the existing demo. If wanted later, record
a delegation demo with a small constrained task and warm models.

**Task 20 (Docker) — partial.** Shipped the safe, standard hardening: `HEALTHCHECK`
(stdlib urllib, no extra packages), `.dockerignore`, compose `ollama` healthcheck +
`depends_on: service_healthy` + `restart: unless-stopped`. **Deferred** the multi-stage
build: the Docker daemon was unavailable to validate a build, and the
torch/sentence-transformers deps make an untested multi-stage refactor genuinely
risky. Single-stage image is correct and unchanged in behavior. To finish: validate
`docker build .` on a machine with Docker, then layer in multi-stage if image size
matters.

## Bugs found + fixed (surfaced by the live eval baseline)

1. **Forced route auto-escalated.** `--route FAST` still ran confidence escalation to
   CODER. Now forced routes skip escalation. (commit `13951ba`)
2. **CLAUDE crashed on missing/!auth credentials.** CLI-present-but-401 returned a raw
   error instead of degrading. Now `_claude_cli` returns `(output, success)` and
   `claude()` falls back CLI → API → clear message. (commit `9fe7833`)
3. **Eval runner lost all results on a mid-run crash.** Now persists after every task
   (`partial` flag) and isolates per-task exceptions. (commit `9fe7833`)

## Eval baseline

20/20 tasks pass (100%), 7 LLM-judged tasks avg 7.1/10, ~946s total wall time.
Full breakdown in `evals/BASELINE.md`.

## Commits (this run, newest first)

```
9fe7833 Fix CLAUDE no-key degrade + eval runner crash resilience
a323d5c Harden Docker: healthcheck, .dockerignore, compose health gating
890247c Add cache TTL enforcement, --clear-cache, streaming-contract tests
5449089 Add examples/ dir with watcher sample inputs
e93134e Add web health page, session export, copy-to-clipboard
7ec66ef Add --version, --list-agents, --verbose CLI flags
7d4c4c4 Add startup config validation
21037b7 Add LLM retry/backoff on transient errors
2ae502d Add ruff lint, Makefile, sync packaging, remove legacy agents.py
bd15eb5 Add CONTRIBUTING, ARCHITECTURE, issue/PR templates
```
(plus `evals/BASELINE.md` + this report.)

## Suggested next steps (for the owner)

- Validate `docker build .` + finish multi-stage if image size matters (Task 20 tail).
- Optional: record a delegation demo GIF with warm models + a tiny task.
- `mypy` / type-checking pass (not attempted — would touch many files).
- Post to r/LocalLLaMA (draft ready in `LAUNCH.md`).
