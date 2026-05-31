"""CODEBASE agent — answers questions about an indexed code repository.

Semantically searches the ChromaDB-indexed codebase for relevant chunks,
then uses an LLM to answer questions, explain code, or suggest changes.
"""

from helpers.config import cfg
from helpers.llm import _call_stream
from state import AgentState
from ui import console, print_agent_header


def codebase_agent(state: AgentState) -> AgentState:
    try:
        project_path = state.get("project_context_path") or state.get("project_path")
        task = state["task"]
        model = cfg.model("coder")  # code-capable model

        # Get relevant code context from index
        code_context = ""
        if project_path:
            from helpers.codebase import CodebaseIndex

            idx = CodebaseIndex(project_path)
            if not idx.is_indexed():
                console.print(f"[bold yellow]CODEBASE: indexing {project_path} (first run)...[/bold yellow]")
                n = idx.index()
                console.print(f"[info]CODEBASE: indexed {n} chunks[/info]")
            code_context = idx.query(task)
        else:
            # Fallback: use project_context string from state if available
            code_context = state.get("project_context") or ""
            if code_context:
                code_context = f"Project context:\n{code_context}"

        context_section = f"\n\n{code_context}" if code_context else ""

        system = (
            "You are an expert software engineer analyzing a codebase. "
            "Answer questions about the code precisely — reference specific files and line numbers when relevant. "
            "For bug reports, provide exact fixes. For architecture questions, explain the design clearly. "
            "For 'how does X work' questions, trace the execution path through the relevant code. "
            "If asked to write a PR or patch, produce a complete diff or updated file."
        )

        print_agent_header("CODEBASE", model)
        result = _call_stream(
            model,
            system,
            task + context_section,
            agent="CODEBASE",
            messages=state.get("chat_messages") or None,
        )

        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["CODEBASE"] = result
        state["result"] = result
        state["history"].append("Codebase agent completed")

    except Exception as e:
        error_msg = f"[CODEBASE error: {e}]"
        console.print(f"[bold red]{error_msg}[/bold red]")
        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["CODEBASE"] = error_msg
        state["result"] = error_msg

    return state
