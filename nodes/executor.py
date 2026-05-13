import re
import subprocess
from pathlib import Path
from state import AgentState
from ui import console, print_agent_header

_BLOCKED_PATTERNS = [
    r'\brm\s+-rf\b', r'\brm\s+-r\b', r'\bsudo\b', r'\bmkfs\b',
    r'\bdd\s+if=', r'\bchmod\s+777\b', r'\bchown\b',
    r'curl\b.*\|\s*(sh|bash)', r'wget\b.*\|\s*(sh|bash)',
    r'\b(shutdown|reboot|halt)\b', r'\bkill\s+-9\s+1\b',
    r'>\s*/dev/sd', r'>\s*/etc/',
]

def _is_dangerous(cmd: str) -> bool:
    for pattern in _BLOCKED_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return True
    return False

def executor(state: AgentState) -> AgentState:
    """Runs shell commands embedded in coder output. Retries up to 3x on failure."""
    try:
        coder_output = (state.get("agent_outputs") or {}).get("CODER", "")
        run_tags = re.findall(r'<run>(.*?)</run>', coder_output, re.DOTALL)
        if not run_tags:
            run_tags = re.findall(r'```(?:run|bash|sh)\n(.*?)```', coder_output, re.DOTALL)

        if not run_tags:
            if not state.get("agent_outputs"):
                state["agent_outputs"] = {}
            state["agent_outputs"]["EXECUTOR"] = "[No commands to run]"
            state["history"].append("Executor: no commands found")
            return state

        work_dir = state.get("output_dir") or str(Path(__file__).parent.parent / "output")
        all_results = []
        for cmd in run_tags:
            cmd = cmd.strip()

            # Security: block dangerous commands
            if _is_dangerous(cmd):
                all_results.append(f"$ {cmd}\nBLOCKED: command matched security deny-list")
                continue

            retries = 0
            while retries < 3:
                try:
                    proc = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True,
                        timeout=60, cwd=work_dir
                    )
                    stdout = proc.stdout.strip()
                    stderr = proc.stderr.strip()
                    exit_code = proc.returncode
                    result_str = f"$ {cmd}\n"
                    if stdout:
                        result_str += stdout + "\n"
                    if stderr:
                        result_str += f"STDERR: {stderr}\n"
                    result_str += f"Exit: {exit_code}"
                    all_results.append(result_str)
                    if exit_code == 0:
                        break
                    retries += 1
                except subprocess.TimeoutExpired:
                    all_results.append(f"$ {cmd}\nTIMEOUT after 60s")
                    break
                except Exception as e:
                    all_results.append(f"$ {cmd}\nERROR: {e}")
                    break

        combined = "\n\n".join(all_results)
        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["EXECUTOR"] = combined
        state["result"] = (state.get("result") or "") + f"\n\n[Execution output]\n{combined}"
        state["history"].append(f"Executor ran {len(run_tags)} command(s)")
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
