import os
import shutil
import subprocess
from pathlib import Path

from helpers.session import _session_ctx
from state import AgentState
from ui import console, print_agent_header


def _build_prompt(state: AgentState) -> str:
    """Build full prompt with task + context for Claude."""
    parts = [state["task"]]

    ctx = _session_ctx(state)
    if ctx:
        parts.append(ctx)

    if state.get("project_context"):
        parts.append(state["project_context"] or "")

    for agent, output in (state.get("agent_outputs") or {}).items():
        parts.append(f"\n[{agent} output]:\n{output[:800]}")

    return "\n".join(parts)


def _claude_cli(state: AgentState) -> tuple[str, bool]:
    """Run Claude Code CLI in non-interactive mode.
    Returns (output, success). success=False signals the caller to try the API fallback."""
    prompt = _build_prompt(state)
    work_dir = state.get("output_dir") or str(Path(__file__).parent.parent / "output")
    Path(work_dir).mkdir(parents=True, exist_ok=True)

    print_agent_header("CLAUDE", "claude-code-cli")
    console.print("[info]Running Claude Code CLI...[/info]")

    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=work_dir,
        )
        result = proc.stdout.strip()
        if proc.returncode != 0:
            # CLI failed (often auth: "401 Invalid authentication credentials").
            # Signal failure so caller can fall back to the API path.
            err = (proc.stderr or "").strip()
            console.print(f"[yellow]Claude CLI failed (exit {proc.returncode}); trying API fallback[/yellow]")
            return (f"[Claude CLI error: {err[:200]}]", False)
        if not result:
            return ("[Claude Code CLI returned no output]", False)
    except subprocess.TimeoutExpired:
        return ("[Claude Code CLI timed out after 5 minutes]", False)
    except Exception as e:
        return (f"[Claude Code CLI error: {e}]", False)

    console.print(result, markup=False)
    return (result, True)


def _claude_api_fallback(state: AgentState) -> str:
    """Fallback: raw Anthropic API streaming call."""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return "[Claude node: set ANTHROPIC_API_KEY in .env or install claude CLI]"

    model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    prompt = _build_prompt(state)

    client = anthropic.Anthropic(api_key=api_key)
    print_agent_header("CLAUDE", model)
    result = ""
    with client.messages.stream(
        model=model,
        max_tokens=4096,
        system="You are an expert assistant. Think carefully and produce high-quality, detailed output.",
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            console.print(text, end="", markup=False)
            result += text
    console.print()
    return result


def claude(state: AgentState) -> AgentState:
    """Claude node — uses Claude Code CLI if available, falls back to API.
    If the CLI is present but fails (e.g. unauthenticated 401), degrade to the
    API path; if that also can't run (no key), return a clear message."""
    try:
        if shutil.which("claude"):
            result, ok = _claude_cli(state)
            if not ok:
                api_result = _claude_api_fallback(state)
                # Only replace CLI error if the API path actually produced something
                if api_result and not api_result.startswith("[Claude node:"):
                    result = api_result
                else:
                    result = api_result or result
        else:
            result = _claude_api_fallback(state)

        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["CLAUDE"] = result
        state["result"] = result
        state["history"].append("Claude completed")
    except Exception as e:
        error_msg = f"[CLAUDE error: {e}]"
        console.print(f"[bold red]{error_msg}[/bold red]")
        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["CLAUDE"] = error_msg
        state["result"] = error_msg
    return state
