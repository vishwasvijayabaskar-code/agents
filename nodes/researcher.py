import re

from helpers.config import cfg
from helpers.llm import _call_stream
from helpers.search import _fetch_page, _format_search_results, _search
from helpers.session import _session_ctx
from state import AgentState
from ui import console, print_agent_header


def _summarize_page(content: str, task: str) -> str:
    """Compress fetched page content to ~500 chars using fast model."""
    from helpers.llm import _call
    fast_model = cfg.model("fast")
    system = "Summarize this web page content in 2-3 sentences. Keep only information relevant to the user's task. Be concise."
    user = f"Task: {task}\n\nPage content:\n{content[:3000]}"
    try:
        return _call(fast_model, system, user, agent="RESEARCHER_SUMMARIZE").strip()
    except Exception:
        return content[:1000]  # fallback: raw truncation


def _pick_urls_to_fetch(results: list[dict], task: str, max_fetch: int) -> list[str]:
    """Pick top-N URLs from results most relevant to task."""
    if not results or max_fetch == 0:
        return []
    task_words = set(re.findall(r'\w+', task.lower()))
    scored = []
    for r in results:
        title_words = set(re.findall(r'\w+', (r.get('title') or '').lower()))
        score = len(title_words & task_words)
        url = r.get('href') or r.get('url') or ''
        if url and url.startswith('http'):
            scored.append((score, url))
    scored.sort(reverse=True)
    return [url for _, url in scored[:max_fetch]]


def researcher(state: AgentState) -> AgentState:
    try:
        model = cfg.model("researcher")
        max_results = cfg.get("researcher", "max_search_results", 5)
        max_fetches = cfg.get("researcher", "max_page_fetches", 2)
        max_page_chars = cfg.get("researcher", "max_page_chars", 5000)

        console.print("[info]Searching web...[/info]")
        results = _search(state["task"], max_results=max_results)
        search_text = _format_search_results(results)

        # Optionally fetch full page content for top URLs
        summarize = cfg.get("researcher", "summarize_pages", True)
        page_content = ""
        if max_fetches > 0 and results:
            urls = _pick_urls_to_fetch(results, state["task"], max_fetches)
            fetched = []
            for url in urls:
                console.print(f"[info]Fetching {url[:60]}...[/info]")
                content = _fetch_page(url, max_chars=max_page_chars)
                if not content.startswith("["):  # not an error
                    if summarize and len(content) > 1000:
                        content = _summarize_page(content, state["task"])
                    fetched.append(f"--- {url} ---\n{content}")
            if fetched:
                page_content = "\n\nPage content:\n" + "\n\n".join(fetched)

        system = "You are a deep research and analysis expert. Think step by step. Use the web search results and page content as grounding. Give structured, detailed output."
        proj = f"\n\n{state['project_context']}" if state.get("project_context") else ""
        user = (
            f"Task: {state['task']}{_session_ctx(state)}{proj}"
            f"\n\nWeb search results:\n{search_text}"
            f"{page_content}"
        )
        print_agent_header("RESEARCHER", model)
        result = _call_stream(model, system, user, agent="RESEARCHER")

        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["RESEARCHER"] = result
        state["result"] = result
        state["history"].append("Researcher completed")
    except Exception as e:
        error_msg = f"[RESEARCHER error: {e}]"
        console.print(f"[bold red]{error_msg}[/bold red]")
        if not state.get("agent_outputs"):
            state["agent_outputs"] = {}
        state["agent_outputs"]["RESEARCHER"] = error_msg
        state["result"] = error_msg
    return state
