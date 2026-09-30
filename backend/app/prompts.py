SYSTEM_PROMPT = (
    "You are a helpful coding assistant. You strictly answer questions related to "
    "software engineering, algorithms, system design, and code. If a user asks about "
    "general topics (weather, news, cooking, casual chat), politely decline and state "
    "that you are designed only for programming assistance."
)
RATE_LIMIT_MESSAGE = "Traffic is high. Please wait 10 seconds before asking again."

def build_prompt(user_message: str, context_chunks: list[str]) -> list[dict]:
    system = SYSTEM_PROMPT
    if context_chunks:
        context = "\n\n---\n\n".join(context_chunks)
        system = f"{SYSTEM_PROMPT}\n\nUse the following retrieved document context if relevant:\n\n{context}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user_message}]
