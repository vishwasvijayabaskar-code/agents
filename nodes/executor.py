import re
import subprocess
from pathlib import Path

from helpers.config import cfg
from state import AgentState
from ui import console, print_agent_header

_BLOCKED_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\brm\s+-r\b",
    r"\bsudo\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bchmod\s+777\b",
    r"\bchown\b",
    r"curl\b.*\|\s*(sh|bash)",
    r"wget\b.*\|\s*(sh|bash)",
    r"\b(shutdown|reboot|halt)\b",
    r"\bkill\s+-9\s+1\b",
    r">\s*/dev/sd",
    r">\s*/etc/",
]


def _is_dangerous(cmd: str) -> bool:
    for pattern in _BLOCKED_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return True
    return False


def _extract_commands(text: str) -> list[str]:
    """Pull runnable commands from agent output (<run> tags or run/bash/sh fences)."""
    tags = re.findall(r"<run>(.*?)</run>", text, re.DOTALL)
    if not tags:
        tags = re.findall(r"```(?:run|bash|sh)\n(.*?)```", text, re.DOTALL)
    return [t.strip() for t in tags if t.strip()]


def _run_commands(cmds: list[str], work_dir: str) -> tuple[list[str], bool]:
    """Run commands (each retried up to 3x). Returns (result_strings, had_failure)."""
    results: list[str] = []
    had_failure = False
    for cmd in cmds:
        if _is_dangerous(cmd):
            # Security block is a policy decision, not a fixable failure —
            # do NOT trigger the CODER repair loop (it would just rephrase it).
            results.append(f"$ {cmd}\nBLOCKED: command matched security deny-list")
            continue
        retries = 0
        while retries < 3:
            try:
                proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=work_dir)
                stdout = proc.stdout.strip()
                stderr = proc.stderr.strip()
                exit_code = proc.returncode
                result_str = f"$ {cmd}\n"
                if stdout:
                    result_str += stdout + "\n"
                if stderr:
                    result_str += f"STDERR: {stderr}\n"
                result_str += f"Exit: {exit_code}"
                results.append(result_str)
                if exit_code == 0:
                    break
                retries += 1
                if retries >= 3:
                    had_failure = True
            except subprocess.TimeoutExpired:
                results.append(f"$ {cmd}\nTIMEOUT after 60s")
                had_failure = True
                break
            except Exception as e:
                results.append(f"$ {cmd}\nERROR: {e}")
                had_failure = True
                break
    return results, had_failure


def _attempt_repair(state: AgentState, failing_output: str, work_dir: str) -> list[str]:
    """On persistent failure, ask CODER to fix, then run its commands once.
    Returns extra result strings (empty if no repair happened)."""
    from helpers.delegation import execute_delegation
    from nodes.coder import coder

    query = (
        "The following shell commands failed. Fix the underlying code or commands and "
        "return corrected commands in a ```bash block.\n\n"
        f"Original task: {state.get('task', '')}\n\nFailing output:\n{failing_output[:1500]}"
    )
    try:
        fixed = execute_delegation("CODER", query, coder, state)  # type: ignore[arg-type]
    except Exception as e:
        return [f"[repair failed: {e}]"]
    cmds = _extract_commands(fixed)
    if not cmds:
        return ["[repair: CODER proposed no runnable commands]"]
    console.print("[yellow]EXECUTOR → CODER repair attempt[/yellow]")
    results, _ = _run_commands(cmds, work_dir)
    return ["[repair attempt via CODER]"] + results


def executor(state: AgentState) -> AgentState:
    """Runs shell commands embedded in coder output. Retries up to 3x on failure."""
    # Check if EXECUTOR is disabled via config or --no-exec flag
    if not cfg.get("executor", "enabled", True):
        msg = "[EXECUTOR disabled — run with executor.enabled=true in config.yaml or remove --no-exec]"
        console.print(f"[bold yellow]{msg}[/bold yellow]")
        state.setdefault("agent_outputs", {})["EXECUTOR"] = msg
        state["history"].append("Executor: disabled")
        return state

    try:
        coder_output = (state.get("agent_outputs") or {}).get("CODER", "")
        run_tags = _extract_commands(coder_output)

        if not run_tags:
            if not state.get("agent_outputs"):
                state["agent_outputs"] = {}
            state["agent_outputs"]["EXECUTOR"] = "[No commands to run]"
            state["history"].append("Executor: no commands found")
            return state

        work_dir = state.get("output_dir") or str(Path(__file__).parent.parent / "output")
        all_results, had_failure = _run_commands(run_tags, work_dir)
        state["history"].append(f"Executor ran {len(run_tags)} command(s)")

        # Cross-agent repair: on persistent failure, ask CODER to fix (once).
        repair_enabled = cfg.get("executor", "repair", True)
        already_repaired = any("repair" in h for h in (state.get("history") or []))
        if had_failure and repair_enabled and not already_repaired:
            extra = _attempt_repair(state, "\n\n".join(all_results), work_dir)
            if extra:
                all_results.extend(extra)
                state["history"].append("Executor → CODER repair attempted")

        combined = "\n\n".join(all_results)
        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["EXECUTOR"] = combined
        state["result"] = (state.get("result") or "") + f"\n\n[Execution output]\n{combined}"
        print_agent_header("EXECUTOR")
        console.print(combined, style="info")
    except Exception as e:
        error_msg = f"[EXECUTOR error: {e}]"
        console.print(f"[bold red]{error_msg}[/bold red]")
        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["EXECUTOR"] = error_msg
        state["result"] = error_msg
    return state
