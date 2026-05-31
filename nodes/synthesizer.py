"""SYNTHESIZE node — merges outputs from parallel fan-out into one result."""

from helpers.config import cfg
from helpers.llm import _call_stream
from state import AgentState
from ui import console, print_agent_header


def synthesizer(state: AgentState) -> AgentState:
    """Combine multiple agent outputs into a unified result."""
    try:
        agent_outputs = state.get("agent_outputs") or {}
        if len(agent_outputs) <= 1:
            # Nothing to synthesize
            return state

        model = cfg.model("fast")  # Use fast model for synthesis

        parts = []
        for agent, output in agent_outputs.items():
            parts.append(f"=== {agent} ===\n{output[:2000]}")
        combined = "\n\n".join(parts)

        original_task = state.get("task", "")
        system = "You are a synthesis expert. Combine and reconcile multiple agent outputs into a single coherent, well-structured response. Eliminate redundancy. Preserve all unique insights."
        user = f"Original task: {original_task}\n\nAgent outputs to synthesize:\n{combined}"

        print_agent_header("SYNTHESIZE", model)
        result = _call_stream(model, system, user, agent="SYNTHESIZE")

        state["agent_outputs"]["SYNTHESIZE"] = result
        state["result"] = result
        state["history"].append("Synthesizer combined outputs")
    except Exception as e:
        error_msg = f"[SYNTHESIZE error: {e}]"
        console.print(f"[bold red]{error_msg}[/bold red]")
        # Fall back to last agent output on error
        outputs = state.get("agent_outputs") or {}
        if outputs:
            state["result"] = list(outputs.values())[-1]
    return state
