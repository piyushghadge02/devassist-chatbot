SYSTEM_PROMPT = (
    "You are a helpful coding assistant. You strictly answer questions related to "
    "software engineering, algorithms, system design, and code. If a user asks about "
    "general topics (weather, news, cooking, casual chat), politely decline and state "
    "that you are designed only for programming assistance."
)
RATE_LIMIT_MESSAGE = "Traffic is high. Please wait 10 seconds before asking again."

def build_prompt(user_message: str, context_chunks: list[str], document_selected: bool = False) -> list[dict]:
    system = SYSTEM_PROMPT
    if context_chunks:
        context = "\n\n---\n\n".join(context_chunks)
        system = (
            f"{SYSTEM_PROMPT}\n\n"
            f"IMPORTANT: A document has been selected for this conversation. "
            f"Answer the user's question using ONLY the following retrieved document context. "
            f"Extract and present whatever relevant information the context contains about the topic. "
            f"If the context truly contains no information about the topic, state: "
            f"'The selected document does not contain information about this topic.' "
            f"Do NOT use your general knowledge. Do NOT refuse based on the programming-only guardrail "
            f"when a document is selected.\n\n"
            f"{context}"
        )
    elif document_selected:
        system = (
            f"{SYSTEM_PROMPT}\n\n"
            f"IMPORTANT: A document has been selected for this conversation, but no relevant content "
            f"was found in it for this question. You MUST state: "
            f"'The selected document does not contain information about this topic.' "
            f"Do NOT use your general knowledge. Do NOT refuse based on the programming-only guardrail "
            f"when a document is selected."
        )
    return [{"role": "system", "content": system}, {"role": "user", "content": user_message}]
