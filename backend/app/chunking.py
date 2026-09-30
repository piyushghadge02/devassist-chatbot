def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """SRS 3.3: chunk size 500 characters, overlap 50 characters."""
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")
    text = (text or "").strip()
    if not text:
        return []
    chunks, start, step = [], 0, chunk_size - overlap
    while start < len(text):
        chunk = text[start:start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(text):
            break
        start += step
    return chunks
