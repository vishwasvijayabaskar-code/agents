import os
import re
import json
import fnmatch
from pathlib import Path
from litellm import completion
from state import AgentState
from ui import console, print_agent_header

BASE = "http://localhost:11434"

_USAGE_FILE = Path(__file__).parent / "usage.jsonl"

def _log_usage(agent: str, model: str, prompt_tokens: int, completion_tokens: int):
    import json as _json
    from datetime import datetime as _dt
    entry = {
        "timestamp": _dt.now().isoformat(),
        "date": _dt.now().strftime("%Y-%m-%d"),
        "agent": agent,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }
    try:
        with open(_USAGE_FILE, 'a') as f:
            f.write(_json.dumps(entry) + "\n")
    except Exception:
        pass

_CHROMA_DIR = str(Path(__file__).parent / "chroma")
_chroma_client = None
_chroma_collection = None

def _get_chroma():
    global _chroma_client, _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection
    try:
        import chromadb
        _chroma_client = chromadb.PersistentClient(path=_CHROMA_DIR)
        _chroma_collection = _chroma_client.get_or_create_collection("agent_memory")
    except Exception:
        _chroma_collection = None
    return _chroma_collection

def _embed_memory(task: str, result: str, agents: list[str], timestamp: str):
    col = _get_chroma()
    if col is None:
        return
    try:
        doc = f"Task: {task}\nAgents: {', '.join(agents)}\nResult: {result[:600]}"
        col.add(documents=[doc], ids=[timestamp],
                metadatas=[{"task": task, "agents": ", ".join(agents), "timestamp": timestamp}])
    except Exception:
        pass

def _relevant_memory(task: str, k: int = 5) -> str:
    col = _get_chroma()
    if col is None:
        return ""
    try:
        count = col.count()
        if count == 0:
            return ""
        results = col.query(query_texts=[task], n_results=min(k, count))
        docs = results.get("documents", [[]])[0]
        if not docs:
            return ""
        return "Semantically relevant past tasks:\n" + "\n---\n".join(docs[:k])
    except Exception:
        return ""

_BINARY_EXTS = {'.png','.jpg','.jpeg','.gif','.ico','.svg','.woff','.ttf','.eot','.mp4','.mp3','.zip','.tar','.gz','.pdf','.pyc','.pyo','.so','.dylib','.lock'}
_SKIP_DIRS = {'.git','node_modules','__pycache__','.venv','venv','env','.env','dist','build','.next','coverage'}

def _load_project_context(project_path: str, task: str, max_total_bytes: int = 150_000, max_file_bytes: int = 40_000) -> str:
    """Walk project dir, return relevant files as formatted context block."""
    root = Path(project_path).expanduser().resolve()
    if not root.exists():
        return f"[Project path not found: {project_path}]"

    # Load .gitignore patterns
    gitignore_patterns = []
    gi = root / ".gitignore"
    if gi.exists():
        gitignore_patterns = [l.strip() for l in gi.read_text().splitlines() if l.strip() and not l.startswith("#")]

    def is_ignored(p: Path) -> bool:
        rel = str(p.relative_to(root))
        for pat in gitignore_patterns:
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(p.name, pat):
                return True
        return False

    # Score files by keyword relevance to task
    task_words = set(re.findall(r'\w+', task.lower()))
    def relevance(p: Path) -> int:
        name_words = set(re.findall(r'\w+', p.stem.lower()))
        return len(name_words & task_words)

    files = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in _BINARY_EXTS:
            continue
        if is_ignored(p):
            continue
        try:
            size = p.stat().st_size
            if size > max_file_bytes:
                continue
            files.append((relevance(p), p))
        except OSError:
            continue

    # Sort: relevant first, then by path
    files.sort(key=lambda x: (-x[0], str(x[1])))

    blocks = []
    total = 0
    for _, p in files:
        try:
            content = p.read_text(errors="replace")
            rel = p.relative_to(root)
            block = f"### {rel}\n```\n{content}\n```"
            if total + len(block) > max_total_bytes:
                break
            blocks.append(block)
            total += len(block)
        except OSError:
            continue

    if not blocks:
        return "[No readable files found in project]"
    return f"<project_files path=\"{root}\">\n" + "\n\n".join(blocks) + "\n</project_files>"

def _call(model: str, system: str, user: str, agent: str = "ORCHESTRATOR") -> str:
    response = completion(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        api_base=BASE,
    )
    try:
        u = response.usage
        _log_usage(agent, model, u.prompt_tokens or 0, u.completion_tokens or 0)
    except Exception:
        pass
    return response.choices[0].message.content

def _call_stream(model: str, system: str, user: str, agent: str = "WORKER") -> str:
    """Stream tokens with rich display, return full text."""
    full_text = ""
    usage = None
    for chunk in completion(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        api_base=BASE,
        stream=True,
        stream_options={"include_usage": True},
    ):
        delta = chunk.choices[0].delta.content or ""
        console.print(delta, end="", markup=False)
        full_text += delta
        if hasattr(chunk, 'usage') and chunk.usage:
            usage = chunk.usage
    console.print()
    if usage:
        _log_usage(agent, model, usage.prompt_tokens or 0, usage.completion_tokens or 0)
    else:
        # Fallback: approximate if provider doesn't support stream usage
        _log_usage(agent, model, len(system.split()) + len(user.split()), len(full_text.split()))
    return full_text

def _search(query: str) -> str:
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        return "\n\n".join([f"**{r['title']}**\n{r['body']}" for r in results])
    except Exception as e:
        return f"[Search unavailable: {e}]"

def _write_files(content: str, output_dir: str) -> list[str]:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    written = []

    # Try filename headers: **filename.ext** or ### filename.ext
    named_pattern = re.compile(
        r'(?:\*\*([^*\n]+\.\w+)\*\*|###\s+([^\n]+\.\w+))\s*\n```(?:\w+)?\n(.*?)```',
        re.DOTALL
    )
    matches = list(named_pattern.finditer(content))

    if matches:
        for m in matches:
            filename = (m.group(1) or m.group(2)).strip()
            code = m.group(3)
            path = os.path.join(output_dir, filename)
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                f.write(code)
            written.append(filename)
    else:
        lang_map = {
            'html': 'index.html', 'css': 'styles.css',
            'javascript': 'script.js', 'js': 'script.js',
            'python': 'output.py', 'py': 'output.py',
            'typescript': 'output.ts', 'ts': 'output.ts',
        }
        lang_pattern = re.compile(r'```(\w+)\n(.*?)```', re.DOTALL)
        seen = set()
        for m in lang_pattern.finditer(content):
            lang = m.group(1).lower()
            filename = lang_map.get(lang, f'output.{lang}')
            if filename in seen:
                continue
            seen.add(filename)
            path = os.path.join(output_dir, filename)
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                f.write(m.group(2))
            written.append(filename)

    return written

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

_ANAPHORA = ("it", "this", "that", "them", "the app", "the project", "the code", "add to", "extend", "update", "modify", "fix it", "improve it")

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

def coder(state: AgentState) -> AgentState:
    model = os.getenv("CODER_MODEL", "ollama/llama3.2")

    context = _session_ctx(state)
    if state.get("project_context"):
        context += f"\n\n{state['project_context']}"
    if (state.get("agent_outputs") or {}).get("RESEARCHER"):
        context += f"\n\nResearch context:\n{state['agent_outputs']['RESEARCHER']}"

    system = "You are an expert software engineer. Write clean, production-quality code. Always prefix each code block with its filename like **app.py** or **styles.css** on its own line. CRITICAL: If session context or project_files describe existing code or a project already built, you MUST extend/modify that exact project — do NOT start fresh, do NOT switch languages or frameworks, do NOT invent a new stack."
    print_agent_header("CODER", model)
    result = _call_stream(model, system, state["task"] + context, agent="CODER")

    if state.get("output_dir"):
        written = _write_files(result, state["output_dir"])
        if written:
            result += f"\n\n[Files written to {state['output_dir']}: {', '.join(written)}]"
            state["history"].append(f"Coder wrote: {written}")

    if not state.get("agent_outputs"):
        state["agent_outputs"] = {}
    state["agent_outputs"]["CODER"] = result
    state["result"] = result
    state["history"].append("Coder completed")
    return state

def researcher(state: AgentState) -> AgentState:
    model = os.getenv("RESEARCHER_MODEL", "ollama/llama3.2")

    console.print("[info]Searching web...[/info]")
    search_results = _search(state["task"])

    system = "You are a deep research and analysis expert. Think step by step. Use the web search results as grounding. Give structured, detailed output."
    proj = f"\n\n{state['project_context']}" if state.get("project_context") else ""
    user = f"Task: {state['task']}{_session_ctx(state)}{proj}\n\nWeb search results:\n{search_results}"
    print_agent_header("RESEARCHER", model)
    result = _call_stream(model, system, user, agent="RESEARCHER")

    if not state.get("agent_outputs"):
        state["agent_outputs"] = {}
    state["agent_outputs"]["RESEARCHER"] = result
    state["result"] = result
    state["history"].append("Researcher completed")
    return state

def fast(state: AgentState) -> AgentState:
    model = os.getenv("FAST_MODEL", "ollama/llama3.2")
    system = "You are a fast, concise assistant. Give short, direct answers."
    print_agent_header("FAST", model)
    result = _call_stream(model, system, state["task"] + _session_ctx(state), agent="FAST")

    if not state.get("agent_outputs"):
        state["agent_outputs"] = {}
    state["agent_outputs"]["FAST"] = result
    state["result"] = result
    state["history"].append("Fast agent completed")
    return state

def executor(state: AgentState) -> AgentState:
    """Runs shell commands embedded in coder output. Retries up to 3x on failure."""
    import subprocess
    import re as _re

    coder_output = (state.get("agent_outputs") or {}).get("CODER", "")
    run_tags = _re.findall(r'<run>(.*?)</run>', coder_output, _re.DOTALL)
    if not run_tags:
        # Also try fenced shell blocks labeled run
        run_tags = _re.findall(r'```(?:run|bash|sh)\n(.*?)```', coder_output, _re.DOTALL)

    if not run_tags:
        state["agent_outputs"]["EXECUTOR"] = "[No commands to run]"
        state["history"].append("Executor: no commands found")
        return state

    work_dir = state.get("output_dir") or str(Path(__file__).parent / "output")
    all_results = []
    for cmd in run_tags:
        cmd = cmd.strip()
        retries = 0
        while retries < 3:
            try:
                proc = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True,
                    timeout=60, cwd=work_dir
                )
                stdout = proc.stdout.strip()
                stderr = proc.stderr.strip()
                exit_code = proc.returncode
                result_str = f"$ {cmd}\n"
                if stdout:
                    result_str += stdout + "\n"
                if stderr:
                    result_str += f"STDERR: {stderr}\n"
                result_str += f"Exit: {exit_code}"
                all_results.append(result_str)
                if exit_code == 0:
                    break
                retries += 1
            except subprocess.TimeoutExpired:
                all_results.append(f"$ {cmd}\nTIMEOUT after 60s")
                break
            except Exception as e:
                all_results.append(f"$ {cmd}\nERROR: {e}")
                break

    combined = "\n\n".join(all_results)
    if not state.get("agent_outputs"):
        state["agent_outputs"] = {}
    state["agent_outputs"]["EXECUTOR"] = combined
    state["result"] = (state.get("result") or "") + f"\n\n[Execution output]\n{combined}"
    state["history"].append(f"Executor ran {len(run_tags)} command(s)")
    print_agent_header("EXECUTOR")
    console.print(combined, style="info")
    return state

def codex(state: AgentState) -> AgentState:
    """Runs OpenAI Codex CLI non-interactively for autonomous code tasks."""
    import subprocess
    from pathlib import Path

    work_dir = state.get("output_dir") or str(Path(__file__).parent / "output" / "codex")
    Path(work_dir).mkdir(parents=True, exist_ok=True)

    context = ""
    if (state.get("agent_outputs") or {}).get("RESEARCHER"):
        context = f"\n\nContext from research:\n{state['agent_outputs']['RESEARCHER'][:1000]}"

    prompt = state["task"] + context
    print_agent_header("CODEX", "codex-cli")
    console.print("[info]Running autonomous code agent...[/info]")

    try:
        proc = subprocess.run(
            ["codex", "exec", prompt],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=work_dir,
        )
        result = proc.stdout or proc.stderr or "[Codex returned no output]"
    except subprocess.TimeoutExpired:
        result = "[Codex timed out after 5 minutes]"
    except Exception as e:
        result = f"[Codex error: {e}]"

    if not state.get("agent_outputs"):
        state["agent_outputs"] = {}
    state["agent_outputs"]["CODEX"] = result
    state["result"] = result
    state["history"].append("Codex agent completed")
    return state

def claude(state: AgentState) -> AgentState:
    """Claude API node — strong reasoning, writing, and analysis."""
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
