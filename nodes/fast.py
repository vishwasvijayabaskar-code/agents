from state import AgentState
from helpers.llm import _call_stream
from helpers.session import _session_ctx
from helpers.config import cfg
from ui import console, print_agent_header

def fast(state: AgentState) -> AgentState:
    try:
        model = cfg.model("fast")
        system = "You are a fast, concise assistant. Give short, direct answers."
        print_agent_header("FAST", model)
        chat_msgs = state.get("chat_messages") or None
        result = _call_stream(model, system, state["task"] + _session_ctx(state), agent="FAST", messages=chat_msgs)

        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["FAST"] = result
        state["result"] = result
        state["history"].append("Fast agent completed")
    except Exception as e:
        error_msg = f"[FAST error: {e}]"
        console.print(f"[bold red]{error_msg}[/bold red]")
        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["FAST"] = error_msg
        state["result"] = error_msg
    return state
