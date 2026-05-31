import json
import re

from helpers.config import cfg
from helpers.delegation import execute_delegation, parse_delegation, strip_delegation_tags
from helpers.llm import _call
from helpers.memory import _cache_lookup, _relevant_memory
from helpers.plugins import get_plugin_descriptions, get_plugin_routes
from state import AgentState

# --- Fast-path routing heuristics ---

_MULTI_HOP = ("then", "after that", "first", "research and", "research then",
              "find and", "analyze and build", "step 1", "step 2")

_CODE_KEYWORDS = ("write", "build", "implement", "create", "code", "html",
                  "css", "python", "javascript", "function", "class", "api",
                  "endpoint", "component", "page", "app", "script", "fix",
                  "refactor", "debug")

_RESEARCH_KEYWORDS = ("research", "search", "find out", "look up",
                      "what is the latest", "compare", "analyze",
                      "investigate", "how does.*work", "explain")

def _fast_route(task: str) -> str | None:
    """Return route string if task can be classified without LLM, else None."""
    t = task.lower().strip()
    # Never fast-route multi-hop tasks
    if any(kw in t for kw in _MULTI_HOP):
        return None
    # Never fast-route long/complex tasks — let orchestrator LLM decide
    if len(task) > 150:
        return None
    # Keyword-based routing for obvious cases
    if any(kw in t for kw in _RESEARCH_KEYWORDS):
        return "RESEARCHER"
    if any(kw in t for kw in _CODE_KEYWORDS):
        return "CODER"
    # Short + simple = FAST
    return "FAST"

# --- Escalation heuristics ---

_ESCALATION_KEYWORDS = ("complex", "production", "scalable", "from scratch",
                        "entire", "full", "architect", "system design",
                        "comprehensive", "enterprise", "distributed")

_HEAVY_TASK_KEYWORDS = ("write", "build", "implement", "create", "design",
                        "architect", "debug", "refactor")

def _should_escalate_to_claude(task: str, route: str) -> bool:
    """Override CODER→CLAUDE for complex tasks."""
    if route != "CODER":
        return False
    t = task.lower()
    has_heavy = any(kw in t for kw in _HEAVY_TASK_KEYWORDS)
    has_complex = any(kw in t for kw in _ESCALATION_KEYWORDS)
    # Escalate if: (heavy keyword + long task) OR (heavy + complexity signal)
    if has_heavy and (len(task) > 200 or has_complex):
        return True
    return False

# --- Confidence routing (Tier 3.4) ---

# Escalation chain: if FAST output is weak, try CODER; if CODER weak, try CLAUDE
_CONFIDENCE_CHAIN = {"FAST": "CODER", "CODER": "CLAUDE"}


def _heuristic_score(output: str) -> int | None:
    """Fast heuristic pre-check. Returns score if confident, None if ambiguous.
    Returns int if confident, None if LLM scoring needed."""
    if not output:
        return 2
    stripped = output.strip()
    low = stripped.lower()
    # Check error signals first (regardless of length)
    _ERROR_SIGNALS = ("sorry, i can't", "sorry, i cannot", "i cannot help",
                      "unable to", "i can't help", "[error", "error:")
    if any(sig in low for sig in _ERROR_SIGNALS):
        return 3  # likely bad → let LLM confirm
    # Too short = suspicious
    if len(stripped) < 50:
        return 2
    # Has code blocks = probably good
    if "```" in output or ("def " in output and "return " in output) or ("function " in output and "{" in output):
        return 7  # skip LLM
    return None  # ambiguous → need LLM


def _score_output(task: str, output: str) -> int:
    """Score agent output quality 1-10. Uses heuristic first, LLM only if ambiguous."""
    # Heuristic pre-check to avoid unnecessary LLM call
    heuristic = _heuristic_score(output)
    if heuristic is not None:
        return heuristic

    fast_model = cfg.model("fast")
    system = (
        "You are a quality evaluator. Rate how well the output answers the task on a scale of 1-10. "
        "Output ONLY a single integer (1-10) with no other text."
    )
    user = f"Task: {task}\n\nOutput:\n{output[:1200]}"
    try:
        raw = _call(fast_model, system, user).strip()
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
        m = re.search(r'\b(10|[1-9])\b', raw)
        return int(m.group()) if m else 5
    except Exception:
        return 5


def _confidence_escalation_done(state: AgentState) -> bool:
    """True if a confidence escalation already happened this task (cap at 1)."""
    return any("confidence escalation" in h for h in (state.get("history") or []))


# --- Task decomposition (Tier 8B) ---

def _is_multi_hop(task: str) -> bool:
    """True if task contains multi-hop signals and is non-trivial."""
    t = task.lower()
    return len(task) > 60 and any(kw in t for kw in _MULTI_HOP)


def _decompose_task(task: str, model: str) -> list[dict] | None:
    """Ask LLM to decompose a multi-hop task into subtasks.
    Returns list of {"route": ..., "task": ...} or None if decomposition fails."""
    system = """You are a task decomposer. Break the user's task into 2-4 sequential subtasks.
Output ONLY a valid JSON array. No explanation. No markdown.
Each subtask has "route" (RESEARCHER, CODER, FAST, CLAUDE, CODEX) and "task" (specific instruction).

Example:
[{"route": "RESEARCHER", "task": "find the latest React best practices for 2025"},
 {"route": "CODER", "task": "build a todo app applying those best practices"}]

Rules:
- RESEARCHER for anything needing web search or analysis
- CODER for code generation
- CLAUDE for complex reasoning or writing
- FAST for simple lookups
- Max 4 subtasks
- Each subtask.task should be specific and self-contained"""

    try:
        raw = _call(model, system, f"Task: {task}").strip()
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
        # Extract JSON array
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            subtasks = json.loads(match.group())
            # Validate structure
            if isinstance(subtasks, list) and len(subtasks) >= 2:
                valid = all(
                    isinstance(s, dict) and "route" in s and "task" in s
                    for s in subtasks
                )
                if valid:
                    return subtasks[:4]  # cap at 4
    except Exception:
        pass
    return None


# --- Orchestrator node ---

def orchestrator(state: AgentState) -> AgentState:
    # Force-route: --route CLI flag bypasses orchestrator entirely
    force = state.get("force_route")
    if force and state.get("iterations", 0) == 0:
        state["route"] = force
        state["done"] = False
        state["iterations"] = 1
        state["history"].append(f"Orchestrator → forced route={force}")
        return state

    # --- Cache check: if near-identical task was run recently, return cached ---
    if state.get("iterations", 0) == 0 and not state.get("agent_outputs"):
        cache_enabled = cfg.get("limits", "cache_ttl_hours", 24) > 0
        if cache_enabled:
            cached = _cache_lookup(state["task"])
            if cached:
                state["result"] = cached
                state["done"] = True
                state["iterations"] = 1
                state["history"].append("Orchestrator → cache hit (similar task found in memory)")
                return state

    # --- Subtask execution: if subtasks exist, execute next one ---
    subtasks = state.get("subtasks")
    if subtasks:
        idx = state.get("current_subtask", 0)
        if idx < len(subtasks):
            st = subtasks[idx]
            state["route"] = st["route"]
            state["done"] = False
            state["iterations"] = state.get("iterations", 0) + 1
            state["current_subtask"] = idx + 1
            state["history"].append(
                f"Orchestrator → subtask {idx+1}/{len(subtasks)}: route={st['route']}, task={st['task'][:60]}"
            )
            return state
        else:
            # All subtasks done
            state["subtasks"] = None
            state["done"] = True
            state["history"].append("Orchestrator → all subtasks complete")
            return state

    # Fast-path: skip LLM for simple/obvious tasks on first iteration
    if state.get("iterations", 0) == 0 and not state.get("agent_outputs"):
        fast = _fast_route(state["task"])
        if fast:
            state["route"] = fast
            state["done"] = False
            state["iterations"] = 1
            state["history"].append(f"Orchestrator → fast-path route={fast}")
            return state

    # --- Multi-hop decomposition: on first iteration for complex tasks ---
    if state.get("iterations", 0) == 0 and _is_multi_hop(state["task"]):
        model = cfg.model("orchestrator")
        subtasks = _decompose_task(state["task"], model)
        if subtasks:
            state["subtasks"] = subtasks
            state["current_subtask"] = 0
            state["history"].append(
                f"Orchestrator → decomposed into {len(subtasks)} subtasks: "
                + " → ".join(s["route"] for s in subtasks)
            )
            # Re-enter to execute first subtask
            return orchestrator(state)

    # --- Delegation post-processing (Tier 8D) ---
    # After a worker runs, check if its output contains <delegate> tags.
    # If so, execute the delegated task and re-run the original worker with
    # the delegated result injected. Max 1 delegation per task.
    already_delegated = any("delegation" in h for h in (state.get("history") or []))
    if not already_delegated:
        agent_outputs_check = state.get("agent_outputs") or {}
        for agent_name, output in agent_outputs_check.items():
            delegation = parse_delegation(output)
            if delegation:
                target_agent, query = delegation
                # Look up node function for target agent
                node_map = _get_delegation_targets()
                if target_agent in node_map:
                    state["history"].append(
                        f"Orchestrator → delegation {agent_name}→{target_agent}: {query[:60]}"
                    )
                    delegate_result = execute_delegation(
                        target_agent, query, node_map[target_agent], state
                    )
                    # Inject delegation result back and strip tags from original
                    clean_output = strip_delegation_tags(output)
                    state["agent_outputs"][agent_name] = (
                        clean_output + f"\n\n[Delegated from {target_agent}]:\n{delegate_result[:1500]}"
                    )
                    state["result"] = state["agent_outputs"][agent_name]
                break  # max 1 delegation per pass

    # Confidence routing: if exactly 1 worker ran and no prior escalation,
    # score the output and escalate to a stronger model if quality is low (< 5).
    # Skip if task was fast-pathed — trivial tasks don't need quality scoring.
    # Skip if route was forced (--route) — user explicitly chose the agent.
    was_fast_pathed = any("fast-path" in h for h in (state.get("history") or []))
    was_forced = any("forced route" in h for h in (state.get("history") or []))
    agent_outputs_now = state.get("agent_outputs") or {}
    workers_now = _worker_nodes()
    workers_ran = [k for k in agent_outputs_now if k in workers_now]
    if len(workers_ran) == 1 and not _confidence_escalation_done(state) and not was_fast_pathed and not was_forced:
        last_agent = workers_ran[0]
        last_output = agent_outputs_now[last_agent]
        if last_agent in _CONFIDENCE_CHAIN:
            score = _score_output(state["task"], last_output)
            if score < 5:
                target = _CONFIDENCE_CHAIN[last_agent]
                # Don't escalate if target already ran
                if target not in agent_outputs_now:
                    state["route"] = target
                    state["done"] = False
                    state["iterations"] = state.get("iterations", 0) + 1
                    state["history"].append(
                        f"Orchestrator → confidence escalation {last_agent}→{target} (score={score}/10)"
                    )
                    return state

    # Full LLM routing for ambiguous / non-decomposable tasks
    model = cfg.model("orchestrator")

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

    plugin_info = get_plugin_descriptions()
    system = f"""You are a task orchestrator. Decide what to do next.

Output ONLY valid JSON. No explanation. No markdown.
Examples:
{{"route": "CODER", "done": false}}
{{"route": "RESEARCHER", "done": false}}
{{"route": "FAST", "done": false}}
{{"route": "CODEX", "done": false}}
{{"route": "CLAUDE", "done": false}}
{{"route": null, "done": true}}

CODER: code generation, web design, HTML/CSS/JS/Python snippets
CODEX: autonomous coding tasks that require file creation, refactoring whole projects, multi-file builds
RESEARCHER: research, analysis, planning, science, strategy (uses web search)
FAST: summaries, simple questions, quick answers
CLAUDE: complex reasoning, writing, essays, multi-step analysis, anything needing deep thought. Also: large code tasks, architecture, production-grade systems.
EXECUTOR: run/test the code that CODER just wrote (use AFTER CODER when user says "run it", "test it", "execute it", "verify it works")
CODEBASE: answer questions about an indexed codebase — "how does X work in this project", "where is Y defined", "write a PR to fix Z" (use when --project is set and task is about understanding existing code){plugin_info}

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

    # Escalation: complex code tasks → CLAUDE instead of CODER
    if route and _should_escalate_to_claude(state["task"], route):
        route = "CLAUDE"
        state["history"].append("Orchestrator → escalated CODER→CLAUDE (complex task)")

    state["route"] = route
    state["done"] = done
    state["iterations"] = state.get("iterations", 0) + 1
    state["history"].append(f"Orchestrator → route={route}, done={done}, iter={state['iterations']}")
    return state


_BUILTIN_WORKERS = {"CODER", "RESEARCHER", "FAST", "CODEX", "CLAUDE", "EXECUTOR", "CODEBASE"}

def _worker_nodes() -> set[str]:
    return _BUILTIN_WORKERS | set(get_plugin_routes())


def _get_delegation_targets() -> dict:
    """Return {name: node_fn} for agents that can be delegated to."""
    # Import lazily to avoid circular imports
    from nodes import claude, coder, fast, researcher
    return {
        "CODER": coder,
        "RESEARCHER": researcher,
        "FAST": fast,
        "CLAUDE": claude,
    }


def route_decision(state: AgentState) -> str:
    agent_outputs = state.get("agent_outputs") or {}
    route = state.get("route")
    workers = _worker_nodes()

    # Iteration cap: higher for subtask mode (2 per subtask + 1 for decomposition)
    subtasks = state.get("subtasks")
    max_iter = (len(subtasks) * 2 + 1) if subtasks else 3

    # Hard stop: done flag or iteration cap
    if state.get("done") or state.get("iterations", 0) >= max_iter:
        return _maybe_synthesize(agent_outputs, workers)

    # Hard-coded guard: never re-run an agent that already produced output
    if route in agent_outputs:
        return _maybe_synthesize(agent_outputs, workers)

    # CODEX only fires for explicit "build entire app / refactor project" signals
    if route == "CODEX":
        task = (state.get("task") or "").lower()
        codex_signals = ("build entire", "refactor", "entire app", "full project", "from scratch")
        if not any(s in task for s in codex_signals):
            # Demote to CODER (return directly, don't mutate state)
            if "CODER" in agent_outputs:
                return _maybe_synthesize(agent_outputs, workers)
            return "CODER"
        if "CODER" in agent_outputs:
            return _maybe_synthesize(agent_outputs, workers)

    if route in workers:
        return route
    return _maybe_synthesize(agent_outputs, workers)


def _maybe_synthesize(agent_outputs: dict, workers: set) -> str:
    """Route to SYNTHESIZE if multiple workers ran and haven't been merged yet."""
    worker_ran = [k for k in agent_outputs if k in workers]
    if len(worker_ran) > 1 and "SYNTHESIZE" not in agent_outputs:
        return "SYNTHESIZE"
    return "__end__"
