def chunk_text(
    text: str, chunk_size_chars: int = 3000, overlap_chars: int = 300
) -> list[str]:
    """
    Splits text into overlapping chunks for embedding.

    This is a character-based splitter rather than a token-exact one: it
    avoids pulling in a tokenizer dependency just for chunk boundaries, and
    the overlap makes it robust to imprecise cuts (~4 chars/token is a
    reasonable approximation for chunk_size_chars=3000 -> ~750 tokens).

    Splits on paragraph boundaries where possible so we don't cut a
    sentence in half mid-word if we can help it; falls back to a hard cut
    if a single paragraph is longer than chunk_size_chars.
    """
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph

        if len(candidate) <= chunk_size_chars:
            current = candidate
            continue

        # Current chunk is full -- flush it, then start the next one with
        # the trailing overlap from the chunk we just closed.
        if current:
            chunks.append(current)
            overlap = current[-overlap_chars:] if overlap_chars else ""
            current = f"{overlap}\n\n{paragraph}" if overlap else paragraph
        else:
            current = paragraph

        # A single paragraph longer than chunk_size_chars: hard-split it.
        while len(current) > chunk_size_chars:
            chunks.append(current[:chunk_size_chars])
            current = current[chunk_size_chars - overlap_chars :]

    if current:
        chunks.append(current)

    return chunks
