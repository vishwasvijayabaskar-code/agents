from langgraph.graph import StateGraph, END
from nodes import orchestrator, coder, researcher, fast, codex, claude, executor, route_decision
from state import AgentState

def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("orchestrator", orchestrator)
    graph.add_node("CODER", coder)
    graph.add_node("RESEARCHER", researcher)
    graph.add_node("FAST", fast)
    graph.add_node("CODEX", codex)
    graph.add_node("CLAUDE", claude)
    graph.add_node("EXECUTOR", executor)

    graph.set_entry_point("orchestrator")

    graph.add_conditional_edges("orchestrator", route_decision, {
        "CODER": "CODER",
        "RESEARCHER": "RESEARCHER",
        "FAST": "FAST",
        "CODEX": "CODEX",
        "CLAUDE": "CLAUDE",
        "EXECUTOR": "EXECUTOR",
        "__end__": END,
    })

    # All agents loop back for multi-hop decisions
    for node in ("CODER", "RESEARCHER", "FAST", "CODEX", "CLAUDE", "EXECUTOR"):
        graph.add_edge(node, "orchestrator")

    return graph.compile()
