import os
from state import AgentState
from helpers.llm import _call_stream
from helpers.search import _search
from helpers.session import _session_ctx
from ui import console, print_agent_header

def researcher(state: AgentState) -> AgentState:
    try:
        model = os.getenv("RESEARCHER_MODEL", "ollama/llama3.2")

        console.print("[info]Searching web...[/info]")
        search_results = _search(state["task"])

        system = "You are a deep research and analysis expert. Think step by step. Use the web search results as grounding. Give structured, detailed output."
        proj = f"\n\n{state['project_context']}" if state.get("project_context") else ""
        user = f"Task: {state['task']}{_session_ctx(state)}{proj}\n\nWeb search results:\n{search_results}"
        print_agent_header("RESEARCHER", model)
        result = _call_stream(model, system, user, agent="RESEARCHER")

        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["RESEARCHER"] = result
        state["result"] = result
        state["history"].append("Researcher completed")
    except Exception as e:
        error_msg = f"[RESEARCHER error: {e}]"
        console.print(f"[bold red]{error_msg}[/bold red]")
        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["RESEARCHER"] = error_msg
        state["result"] = error_msg
    return state
