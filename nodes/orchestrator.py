import os
import re
import json
from state import AgentState
from helpers.llm import _call
from helpers.memory import _relevant_memory

def orchestrator(state: AgentState) -> AgentState:
    model = os.getenv("ORCHESTRATOR_MODEL", "ollama/llama3.2")

    prev_outputs = ""
    for agent, output in (state.get("agent_outputs") or {}).items():
        prev_outputs += f"\n\n[{agent} already ran]:\n{output[:600]}..."

    memory_ctx = ""
    semantic = _relevant_memory(state["task"])
    if semantic:
        memory_ctx = f"\n{semantic}"
    elif state.get("memory"):
        recent = state["memory"][-3:]
        memory_ctx = "\nPast tasks: " + "; ".join([m["task"] for m in recent])

    if state.get("session_history"):
        session_ctx = "\nThis session: " + "; ".join([h["task"] for h in state["session_history"][-3:]])
        memory_ctx += session_ctx

    system = """You are a task orchestrator. Decide what to do next.

Output ONLY valid JSON. No explanation. No markdown.
Examples:
{"route": "CODER", "done": false}
{"route": "RESEARCHER", "done": false}
{"route": "FAST", "done": false}
{"route": "CODEX", "done": false}
{"route": "CLAUDE", "done": false}
{"route": null, "done": true}

CODER: code generation, web design, HTML/CSS/JS/Python snippets
CODEX: autonomous coding tasks that require file creation, refactoring whole projects, multi-file builds
RESEARCHER: research, analysis, planning, science, strategy (uses web search)
FAST: summaries, simple questions, quick answers
CLAUDE: complex reasoning, writing, essays, multi-step analysis, anything needing deep thought
EXECUTOR: run/test the code that CODER just wrote (use AFTER CODER when user says "run it", "test it", "execute it", "verify it works")

Rules:
- If a previous agent already answered the task well, set done=true
- RESEARCHER then CODER/CODEX is valid for "research + build" tasks
- Use CODEX for "build entire app" or "refactor this project" style tasks
- Use CLAUDE for nuanced reasoning, writing, or when other agents have tried and failed
- If ANY worker agent (CODER, RESEARCHER, FAST, CODEX, CLAUDE) has already run and produced output, set done=true UNLESS the task explicitly requires chaining (e.g. research THEN build)
- CODER should only run ONCE per task — never route to CODER if CODER already ran
- If iterations >= 2, always set done=true"""

    user = f"Task: {state['task']}\nIterations: {state['iterations']}{memory_ctx}{prev_outputs}"

    raw = _call(model, system, user).strip()
    # Strip qwen3 chain-of-thought tags before JSON extraction
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()

    try:
        json_match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
        parsed = json.loads(json_match.group() if json_match else raw)
        route = parsed.get("route")
        done = parsed.get("done", False)
    except Exception:
        raw_upper = raw.upper()
        if "CODER" in raw_upper:
            route, done = "CODER", False
        elif "RESEARCHER" in raw_upper:
            route, done = "RESEARCHER", False
        elif "TRUE" in raw_upper or "DONE" in raw_upper:
            route, done = None, True
        else:
            route, done = "FAST", False

    state["route"] = route
    state["done"] = done
    state["iterations"] = state.get("iterations", 0) + 1
    state["history"].append(f"Orchestrator → route={route}, done={done}, iter={state['iterations']}")
    return state


def route_decision(state: AgentState) -> str:
    # Hard stop: done flag or iteration cap
    if state.get("done") or state.get("iterations", 0) >= 3:
        return "__end__"

    route = state.get("route")
    agent_outputs = state.get("agent_outputs") or {}

    # Hard-coded guard: never re-run an agent that already produced output
    if route in agent_outputs:
        return "__end__"

    # CODEX only fires for explicit "build entire app / refactor project" signals
    if route == "CODEX":
        task = (state.get("task") or "").lower()
        codex_signals = ("build entire", "refactor", "entire app", "full project", "from scratch")
        if not any(s in task for s in codex_signals):
            # Demote to CODER (return directly, don't mutate state)
            if "CODER" in agent_outputs:
                return "__end__"
            return "CODER"
        if "CODER" in agent_outputs:
            return "__end__"

    if route in ("CODER", "RESEARCHER", "FAST", "CODEX", "CLAUDE", "EXECUTOR"):
        return route
    return "__end__"
