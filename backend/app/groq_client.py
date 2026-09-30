from .prompts import RATE_LIMIT_MESSAGE

class RateLimitError_(Exception): pass

def _is_rate_limit(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    return "ratelimit" in name or getattr(exc, "status_code", None) == 429 or "429" in str(exc)

async def stream_chat(messages: list[dict], api_key: str, model: str):
    """Yield tokens. Without a Groq key, yields a deterministic offline response
    so the app is fully runnable/testable locally. With a key, uses Groq streaming."""
    if not api_key:
        user = messages[-1]["content"] if messages else ""
        has_context = len(messages) > 0 and "retrieved document context" in messages[0]["content"]
        prefix = "[Offline mode: set GROQ_API_KEY for live Groq answers] "
        text = (f"{prefix}This is a programming-assistance response to: {user[:200]}. "
                + ("I used your uploaded document context to ground this answer. " if has_context else "")
                + "```python\n# example\nprint('hello from DevAssist')\n```")
        for word in text.split(" "):
            yield word + " "
        return
    try:
        from groq import AsyncGroq, RateLimitError
    except Exception:
        from groq import AsyncGroq  # type: ignore
        RateLimitError = ()  # type: ignore
    client = AsyncGroq(api_key=api_key)
    try:
        stream = await client.chat.completions.create(model=model, messages=messages, stream=True)
        async for chunk in stream:
            try:
                delta = chunk.choices[0].delta.content
            except Exception:
                delta = None
            if delta:
                yield delta
    except Exception as exc:
        if _is_rate_limit(exc) or (RateLimitError and isinstance(exc, RateLimitError)):
            raise RateLimitError_(RATE_LIMIT_MESSAGE) from exc
        raise
