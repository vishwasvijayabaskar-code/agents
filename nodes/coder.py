import os
from state import AgentState
from helpers.llm import _call_stream
from helpers.files import _write_files
from helpers.session import _session_ctx
from ui import console, print_agent_header

def coder(state: AgentState) -> AgentState:
    try:
        model = os.getenv("CODER_MODEL", "ollama/llama3.2")

        context = _session_ctx(state)
        if state.get("project_context"):
            context += f"\n\n{state['project_context']}"
        if (state.get("agent_outputs") or {}).get("RESEARCHER"):
            context += f"\n\nResearch context:\n{state['agent_outputs']['RESEARCHER']}"

        system = "You are an expert software engineer. Write clean, production-quality code. Always prefix each code block with its filename like **app.py** or **styles.css** on its own line. CRITICAL: If session context or project_files describe existing code or a project already built, you MUST extend/modify that exact project — do NOT start fresh, do NOT switch languages or frameworks, do NOT invent a new stack."
        print_agent_header("CODER", model)
        result = _call_stream(model, system, state["task"] + context, agent="CODER")

        if state.get("output_dir"):
            written = _write_files(result, state["output_dir"])
            if written:
                result += f"\n\n[Files written to {state['output_dir']}: {', '.join(written)}]"
                state["history"].append(f"Coder wrote: {written}")

        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["CODER"] = result
        state["result"] = result
        state["history"].append("Coder completed")
    except Exception as e:
        error_msg = f"[CODER error: {e}]"
        console.print(f"[bold red]{error_msg}[/bold red]")
        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["CODER"] = error_msg
        state["result"] = error_msg
    return state
