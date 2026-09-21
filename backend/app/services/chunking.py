import uuid

from app.schemas import ParsedSection, Chunk


# Maximum size of each chunk
MAX_CHARS = 1400

# Number of characters shared between consecutive chunks
OVERLAP_CHARS = 150


MAX_CHUNKS_PER_PAPER = 2000


def _snap_to_word_boundary(text: str, ideal_end: int, search_window: int = 80) -> int:
    """Nudges a chunk-end index left to the nearest whitespace, so chunks
    (and the citation snippets built from them) don't start/end mid-word.
    Only searches back up to `search_window` chars -- if nothing's found
    that close, just use the raw index rather than shrinking the chunk a lot."""
    if ideal_end >= len(text):
        return ideal_end
    if text[ideal_end].isspace():
        return ideal_end
    earliest = max(0, ideal_end - search_window)
    idx = text.rfind(" ", earliest, ideal_end)
    if idx == -1:
        idx = text.rfind("\n", earliest, ideal_end)
    return idx + 1 if idx != -1 else ideal_end


def chunk_sections(
    paper_id: str,
    sections: list[ParsedSection],
) -> list[Chunk]:

    chunks: list[Chunk] = []

    order = 0

    # Safety check: overlap must be smaller than chunk size.
    if OVERLAP_CHARS >= MAX_CHARS:
        raise ValueError(
            "OVERLAP_CHARS must be smaller than MAX_CHARS"
        )

    for section in sections:
        if len(chunks) >= MAX_CHUNKS_PER_PAPER:
            break

        text = section.text or ""

        # Ignore completely empty sections
        if not text.strip():
            continue

        start = 0

        while start < len(text):
            if len(chunks) >= MAX_CHUNKS_PER_PAPER:
                break

            # Calculate the end of the current chunk, snapped to a word
            # boundary so chunks/citations don't start or end mid-word.
            end = _snap_to_word_boundary(text, min(start + MAX_CHARS, len(text)))
            if end <= start:
                end = min(start + MAX_CHARS, len(text))  # degenerate case: no whitespace nearby

            piece = text[start:end].strip()

            # Add only non-empty chunks
            if piece:
                chunks.append(
                    Chunk(
                        chunk_id=str(uuid.uuid4()),
                        paper_id=paper_id,
                        text=piece,
                        section_type=section.section_type,
                        page_start=section.page_start,
                        page_end=section.page_end,
                        order=order,
                    )
                )

                order += 1

            # -------------------------------------------------
            # IMPORTANT:
            # If we reached the end of the text, STOP.
            #
            # Without this check, the overlap causes the last
            # chunk to be generated infinitely.
            # -------------------------------------------------
            if end >= len(text):
                break

            # Move forward while keeping some overlap, ensuring start always advances
            new_start = max(start + 1, end - OVERLAP_CHARS)
            # Snap the new start forward to the next word boundary too, so
            # the *following* chunk also doesn't begin mid-word.
            if new_start < len(text) and not text[new_start].isspace():
                next_space = text.find(" ", new_start, min(new_start + 80, len(text)))
                if next_space != -1:
                    new_start = next_space + 1
            start = new_start

    return chunks