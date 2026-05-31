import os
import threading
import time
from contextlib import contextmanager

from litellm import completion

from helpers.usage import _log_usage
from ui import console

BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")

# Substrings signalling a transient error worth retrying (connection/timeout/5xx).
_TRANSIENT_SIGNALS = (
    "connection",
    "timeout",
    "timed out",
    "refused",
    "reset",
    "temporarily",
    "overloaded",
    "503",
    "502",
    "504",
    "internalserver",
    "apiconnection",
    "service unavailable",
)


def _retry_count() -> int:
    """Number of retries on transient LLM errors (config limits.llm_retries, default 2)."""
    try:
        from helpers.config import cfg

        return max(0, int(cfg.get("limits", "llm_retries", 2)))
    except Exception:
        return 2


def _is_transient(exc: Exception) -> bool:
    """True if the exception looks like a transient/retryable failure."""
    if isinstance(exc, TokenBudgetExceeded):
        return False
    text = f"{type(exc).__name__} {exc}".lower()
    return any(sig in text for sig in _TRANSIENT_SIGNALS)


def _completion_with_retry(**kwargs):
    """Call litellm.completion with bounded exponential backoff on transient errors.
    Returns the completion result (a response or a streaming iterator)."""
    retries = _retry_count()
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return completion(**kwargs)
        except Exception as e:
            last_exc = e
            if not _is_transient(e) or attempt == retries:
                raise
            delay = 0.5 * (2**attempt)  # 0.5s, 1s, 2s, ...
            console.print(
                f"[yellow]LLM transient error ({type(e).__name__}); "
                f"retry {attempt + 1}/{retries} in {delay:.1f}s[/yellow]"
            )
            time.sleep(delay)
    raise last_exc  # unreachable, defensive


# Thread-local storage for streaming callback and token budget tracking.
_stream_ctx = threading.local()


class TokenBudgetExceeded(Exception):
    """Raised when a task exceeds its token budget."""

    pass


@contextmanager
def stream_callback(cb):
    """Context manager: set a token callback for _call_stream in this thread."""
    _stream_ctx.callback = cb
    try:
        yield
    finally:
        _stream_ctx.callback = None


@contextmanager
def token_budget(max_tokens: int = 0):
    """Context manager: set a per-task token budget for this thread.
    If max_tokens is 0 or negative, no budget is enforced."""
    _stream_ctx.budget = max_tokens
    _stream_ctx.budget_used = 0
    try:
        yield
    finally:
        _stream_ctx.budget = 0
        _stream_ctx.budget_used = 0


def get_budget_used() -> int:
    """Return tokens consumed in current budget scope."""
    return getattr(_stream_ctx, "budget_used", 0)


def _check_budget():
    """Raise TokenBudgetExceeded if budget is set and exceeded."""
    budget = getattr(_stream_ctx, "budget", 0)
    if budget > 0:
        used = getattr(_stream_ctx, "budget_used", 0)
        if used >= budget:
            raise TokenBudgetExceeded(f"Token budget exceeded: {used}/{budget} tokens used")


def _track_tokens(prompt_tokens: int, completion_tokens: int):
    """Add tokens to budget counter."""
    if getattr(_stream_ctx, "budget", 0) > 0:
        _stream_ctx.budget_used = getattr(_stream_ctx, "budget_used", 0) + prompt_tokens + completion_tokens


def _call(model: str, system: str, user: str, agent: str = "ORCHESTRATOR") -> str:
    _check_budget()
    response = _completion_with_retry(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        api_base=BASE,
    )
    try:
        u = response.usage
        pt, ct = u.prompt_tokens or 0, u.completion_tokens or 0
        _log_usage(agent, model, pt, ct)
        _track_tokens(pt, ct)
    except Exception:
        pass
    return response.choices[0].message.content


def _call_stream(
    model: str,
    system: str,
    user: str,
    agent: str = "WORKER",
    messages: list[dict] | None = None,
    token_callback: callable = None,
) -> str:
    """Stream tokens with rich display, return full text.

    If `messages` is provided (multi-turn history), it is used directly
    (prepended with system message). Otherwise builds single-turn from user.

    If `token_callback` is provided, each delta is also passed to it
    (used by web UI for SSE streaming).
    """
    _check_budget()

    # Use explicit callback or fall back to thread-local (web UI injects this)
    if token_callback is None:
        token_callback = getattr(_stream_ctx, "callback", None)

    full_text = ""
    usage = None

    if messages:
        # Multi-turn: system + history + new user message
        msg_list = [{"role": "system", "content": system}] + messages + [{"role": "user", "content": user}]
    else:
        msg_list = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    stream = _completion_with_retry(
        model=model,
        messages=msg_list,
        api_base=BASE,
        stream=True,
        stream_options={"include_usage": True},
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        console.print(delta, end="", markup=False)
        full_text += delta
        if token_callback and delta:
            token_callback(delta)
        if hasattr(chunk, "usage") and chunk.usage:
            usage = chunk.usage
    console.print()
    if usage:
        pt, ct = usage.prompt_tokens or 0, usage.completion_tokens or 0
        _log_usage(agent, model, pt, ct)
        _track_tokens(pt, ct)
    else:
        pt = len(system.split()) + len(user.split())
        ct = len(full_text.split())
        _log_usage(agent, model, pt, ct)
        _track_tokens(pt, ct)
    return full_text
