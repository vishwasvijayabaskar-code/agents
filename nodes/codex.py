import subprocess
from pathlib import Path
from state import AgentState
from ui import console, print_agent_header

def codex(state: AgentState) -> AgentState:
    """Runs OpenAI Codex CLI non-interactively for autonomous code tasks."""
    try:
        work_dir = state.get("output_dir") or str(Path(__file__).parent.parent / "output" / "codex")
        Path(work_dir).mkdir(parents=True, exist_ok=True)

        context = ""
        if (state.get("agent_outputs") or {}).get("RESEARCHER"):
            context = f"\n\nContext from research:\n{state['agent_outputs']['RESEARCHER'][:1000]}"

        prompt = state["task"] + context
        print_agent_header("CODEX", "codex-cli")
        console.print("[info]Running autonomous code agent...[/info]")

        try:
            proc = subprocess.run(
                ["codex", "exec", prompt],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=work_dir,
            )
            result = proc.stdout or proc.stderr or "[Codex returned no output]"
        except subprocess.TimeoutExpired:
            result = "[Codex timed out after 5 minutes]"
        except Exception as e:
            result = f"[Codex error: {e}]"

        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["CODEX"] = result
        state["result"] = result
        state["history"].append("Codex agent completed")
    except Exception as e:
        error_msg = f"[CODEX error: {e}]"
        console.print(f"[bold red]{error_msg}[/bold red]")
        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["CODEX"] = error_msg
        state["result"] = error_msg
    return state
