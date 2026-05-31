"""
Example plugin: TRANSLATOR agent.
Translates text into a target language using the fast model.

To activate: this file just needs to exist in plugins/.
The orchestrator will learn about TRANSLATOR automatically.

Usage:
    ./run "translate 'hello world' to Spanish"
    ./run --route TRANSLATOR "bonjour le monde → English"
"""
from helpers.config import cfg
from helpers.llm import _call_stream
from helpers.plugins import PluginDefinition
from state import AgentState
from ui import console, print_agent_header


def translator(state: AgentState) -> AgentState:
    """Translate text. The task should specify source text and target language."""
    try:
        model = cfg.model("fast")
        system = (
            "You are a professional translator. "
            "Detect the source language automatically. "
            "Translate accurately, preserving tone and formatting. "
            "Output ONLY the translated text — no explanations, no labels."
        )
        print_agent_header("TRANSLATOR", model)
        result = _call_stream(model, system, state["task"], agent="TRANSLATOR")

        state.setdefault("agent_outputs", {})["TRANSLATOR"] = result
        state["result"] = result
        state["history"].append("Translator agent completed")
    except Exception as e:
        err = f"[TRANSLATOR error: {e}]"
        console.print(f"[bold red]{err}[/bold red]")
        state.setdefault("agent_outputs", {})["TRANSLATOR"] = err
        state["result"] = err
    return state


def register() -> PluginDefinition:
    return PluginDefinition(
        name="TRANSLATOR",
        node_fn=translator,
        description="Translates text between languages. Use when task asks to translate.",
    )
