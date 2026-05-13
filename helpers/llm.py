from litellm import completion
from ui import console
from helpers.usage import _log_usage

BASE = "http://localhost:11434"

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
