import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas import ParsedSection
from app.services.chunking import chunk_sections, MAX_CHARS, OVERLAP_CHARS


def test_chunk_sections_termination_and_finite_chunks():
    # Construct a section with text significantly longer than MAX_CHARS (e.g. 50,000 characters)
    long_text = "This is a sentence in a research paper test document. " * 1000
    assert len(long_text) > MAX_CHARS * 10

    section = ParsedSection(
        section_type="method",
        text=long_text,
        page_start=1,
        page_end=5,
    )

    # Call chunk_sections
    chunks = chunk_sections(paper_id="test_paper_1", sections=[section])

    # Assert finite number of chunks produced
    assert isinstance(chunks, list)
    assert len(chunks) > 0
    # Expected chunk count approx len(long_text) / (MAX_CHARS - OVERLAP_CHARS)
    expected_approx = len(long_text) / (MAX_CHARS - OVERLAP_CHARS)
    assert len(chunks) <= expected_approx + 5

    # Assert that all chunks have valid fields and order
    for idx, c in enumerate(chunks):
        assert c.paper_id == "test_paper_1"
        assert c.section_type == "method"
        assert c.order == idx
        assert len(c.text) <= MAX_CHARS

    print(f"Unit Test Passed: Generated {len(chunks)} chunks for {len(long_text)} chars of text.")


if __name__ == "__main__":
    test_chunk_sections_termination_and_finite_chunks()
