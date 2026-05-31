from state import AgentState

_ANAPHORA = (
    "it",
    "this",
    "that",
    "them",
    "the app",
    "the project",
    "the code",
    "add to",
    "extend",
    "update",
    "modify",
    "fix it",
    "improve it",
)


def _references_previous(task: str) -> bool:
    t = task.lower()
    return any(t.startswith(w) or f" {w}" in t for w in _ANAPHORA)


def _session_ctx(state: AgentState) -> str:
    history = state.get("session_history") or []
    if not history:
        return ""
    task = state.get("task", "")
    # If task references previous work, include full last result
    if _references_previous(task) and history:
        last = history[-1]
        full_last = f"IMPORTANT: The user is referring to work from the previous task.\nPrevious task: {last['task']}\nAgents used: {last['agents']}\nFull output:\n{last['result']}"
        prior = history[-4:-1]
    else:
        full_last = ""
        prior = history[-3:]

    lines = "\n".join([f"- [{' → '.join(h['agents'])}] {h['task']}: {h['result'][:800]}" for h in prior])
    ctx = "\n\nSession context (this session's history):\n" + lines
    if full_last:
        ctx += f"\n\n{full_last}"
    return ctx
