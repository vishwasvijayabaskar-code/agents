from langgraph.graph import END, StateGraph

from helpers.plugins import get_plugin_nodes, get_plugin_routes, load_plugins
from nodes import (
    claude,
    codebase_agent,
    coder,
    codex,
    executor,
    fast,
    orchestrator,
    researcher,
    route_decision,
    synthesizer,
)
from state import AgentState

_BUILTIN_WORKERS = ("CODER", "RESEARCHER", "FAST", "CODEX", "CLAUDE", "EXECUTOR", "CODEBASE")


def build_graph():
    # Load plugins before building graph so their nodes are registered
    load_plugins()
    plugin_nodes = get_plugin_nodes()
    plugin_routes = get_plugin_routes()

    graph = StateGraph(AgentState)

    # Built-in nodes
    graph.add_node("orchestrator", orchestrator)
    graph.add_node("CODER", coder)
    graph.add_node("RESEARCHER", researcher)
    graph.add_node("FAST", fast)
    graph.add_node("CODEX", codex)
    graph.add_node("CLAUDE", claude)
    graph.add_node("EXECUTOR", executor)
    graph.add_node("CODEBASE", codebase_agent)
    graph.add_node("SYNTHESIZE", synthesizer)

    # Plugin nodes (dynamic)
    for name, fn in plugin_nodes.items():
        graph.add_node(name, fn)

    graph.set_entry_point("orchestrator")

    # Build route map
    route_map = {
        "CODER": "CODER",
        "RESEARCHER": "RESEARCHER",
        "FAST": "FAST",
        "CODEX": "CODEX",
        "CLAUDE": "CLAUDE",
        "EXECUTOR": "EXECUTOR",
        "CODEBASE": "CODEBASE",
        "SYNTHESIZE": "SYNTHESIZE",
        "__end__": END,
    }
    for name in plugin_routes:
        route_map[name] = name

    graph.add_conditional_edges("orchestrator", route_decision, route_map)

    # All worker agents loop back for multi-hop decisions
    for node in _BUILTIN_WORKERS:
        graph.add_edge(node, "orchestrator")

    for name in plugin_routes:
        graph.add_edge(name, "orchestrator")

    # SYNTHESIZE always terminates
    graph.add_edge("SYNTHESIZE", END)

    return graph.compile()
