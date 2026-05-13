import os
import json
import shutil
import subprocess
from pathlib import Path
from state import AgentState
from helpers.session import _session_ctx
from ui import console, print_agent_header


def _build_prompt(state: AgentState) -> str:
    """Build full prompt with task + context for Claude."""
    parts = [state["task"]]

    ctx = _session_ctx(state)
    if ctx:
        parts.append(ctx)

    if state.get("project_context"):
        parts.append(state["project_context"])

    for agent, output in (state.get("agent_outputs") or {}).items():
        parts.append(f"\n[{agent} output]:\n{output[:800]}")

    return "\n".join(parts)


def _claude_cli(state: AgentState) -> str:
    """Run Claude Code CLI in non-interactive mode."""
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
        if proc.returncode != 0 and proc.stderr:
            result += f"\nSTDERR: {proc.stderr.strip()}"
        if not result:
            result = "[Claude Code CLI returned no output]"
    except subprocess.TimeoutExpired:
        result = "[Claude Code CLI timed out after 5 minutes]"
    except Exception as e:
        result = f"[Claude Code CLI error: {e}]"

    console.print(result, markup=False)
    return result


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
    """Claude node — uses Claude Code CLI if available, falls back to API."""
    try:
        if shutil.which("claude"):
            result = _claude_cli(state)
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
