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


def _call_stream(
    model: str,
    system: str,
    user: str,
    agent: str = "WORKER",
    messages: list[dict] | None = None,
) -> str:
    """Stream tokens with rich display, return full text.

    If `messages` is provided (multi-turn history), it is used directly
    (prepended with system message). Otherwise builds single-turn from user.
    """
    full_text = ""
    usage = None

    if messages:
        # Multi-turn: system + history + new user message
        msg_list = [{"role": "system", "content": system}] + messages + [{"role": "user", "content": user}]
    else:
        msg_list = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    for chunk in completion(
        model=model,
        messages=msg_list,
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
        _log_usage(agent, model, len(system.split()) + len(user.split()), len(full_text.split()))
    return full_text
