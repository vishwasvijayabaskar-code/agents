import os
from state import AgentState
from ui import console, print_agent_header

def claude(state: AgentState) -> AgentState:
    """Claude API node — strong reasoning, writing, and analysis."""
    try:
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            state["result"] = "[Claude node: set ANTHROPIC_API_KEY in .env to enable]"
            if not state.get("agent_outputs"):
                state["agent_outputs"] = {}
            state["agent_outputs"]["CLAUDE"] = state["result"]
            return state

        model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

        context = ""
        for agent, output in (state.get("agent_outputs") or {}).items():
            context += f"\n\n[{agent} output]:\n{output[:800]}"

        client = anthropic.Anthropic(api_key=api_key)
        print_agent_header("CLAUDE", model)
        result = ""
        with client.messages.stream(
            model=model,
            max_tokens=4096,
            system="You are an expert assistant. Think carefully and produce high-quality, detailed output.",
            messages=[{"role": "user", "content": state["task"] + context}],
        ) as stream:
            for text in stream.text_stream:
                console.print(text, end="", markup=False)
                result += text
        console.print()

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
