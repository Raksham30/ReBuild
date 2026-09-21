"""
Concurrent upload pipeline: verify that a failure in the extraction branch
surfaces correctly as an HTTP 500, even when the chunking+indexing branch
succeeds. This is the 'less obvious of the two failure orders' the user
specifically asked to see tested.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

UID = "concurrent_test_user"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Force all Azure/Firebase services off
    for var in (
        "COSMOS_DB_URI", "COSMOS_DB_KEY", "BLOB_STORAGE_CONNECTION_STRING",
        "AI_SEARCH_URL", "AI_SEARCH_ADMIN_KEY", "FIREBASE_SERVICE_ACCOUNT_PATH",
        "FOUNDRY_PROJECT_ENDPOINT",
    ):
        monkeypatch.setenv(var, "")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOCAL_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("LOCAL_INDEX_DIR", str(tmp_path / "index"))
    monkeypatch.setenv("LOCAL_METADATA_PATH", str(tmp_path / "metadata.json"))

    from app.config import get_settings
    get_settings.cache_clear()

    # Fake embeddings so indexing works without Gemini
    from app.services import indexing
    monkeypatch.setattr(indexing, "embed_texts", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])

    from app.main import app
    from app.auth import get_current_uid
    app.dependency_overrides[get_current_uid] = lambda: UID
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _make_minimal_pdf():
    """A minimal valid PDF that pypdf can parse (1 page, some text)."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n212\n%%EOF"
    )


def test_extraction_failure_surfaces_as_500_when_chunking_succeeds(client, monkeypatch):
    """
    The concurrent pipeline calls:
        chunks_result = future_chunks.result()   # succeeds
        fields = future_fields.result()          # raises RuntimeError

    This test proves that even though future_chunks.result() returns
    normally, the subsequent future_fields.result() raising an exception
    is NOT swallowed -- it propagates as an HTTP 500 to the client.
    """
    from app.services import extraction

    # Make extraction blow up with a distinctive error
    def _boom_extraction(paper_id, sections):
        raise RuntimeError("DELIBERATE EXTRACTION FAILURE FOR TEST")

    monkeypatch.setattr(extraction, "extract_structured_fields", _boom_extraction)

    # Create a workspace first
    ws = client.post("/workspaces", json={"name": "extraction-fail-test"}).json()
    ws_id = ws["workspace_id"]

    # Upload a minimal PDF -- chunking+indexing should succeed,
    # but extraction should fail
    pdf_bytes = _make_minimal_pdf()
    resp = client.post(
        f"/workspaces/{ws_id}/papers/upload",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )

    # The response MUST be 500, not 200
    assert resp.status_code == 500, (
        f"Expected HTTP 500 when extraction fails, got {resp.status_code}: {resp.text}"
    )
    detail = resp.json()["detail"]
    assert "DELIBERATE EXTRACTION FAILURE FOR TEST" in detail, (
        f"Expected the extraction error message in the response, got: {detail}"
    )
    print(f"[TEST PASSED] Extraction failure surfaced as HTTP 500: {detail}")


def test_chunking_failure_surfaces_as_500_when_extraction_would_succeed(client, monkeypatch):
    """Complementary test: if chunking/indexing fails, that also surfaces as 500."""
    from app.services import chunking, extraction

    def _boom_chunking(paper_id, sections):
        raise RuntimeError("DELIBERATE CHUNKING FAILURE FOR TEST")

    # extraction returns normally
    from app.schemas import StructuredExtraction
    monkeypatch.setattr(chunking, "chunk_sections", _boom_chunking)
    monkeypatch.setattr(extraction, "extract_structured_fields",
                        lambda pid, secs: StructuredExtraction(title="ok"))

    ws = client.post("/workspaces", json={"name": "chunking-fail-test"}).json()
    ws_id = ws["workspace_id"]

    pdf_bytes = _make_minimal_pdf()
    resp = client.post(
        f"/workspaces/{ws_id}/papers/upload",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )

    assert resp.status_code == 500, (
        f"Expected HTTP 500 when chunking fails, got {resp.status_code}: {resp.text}"
    )
    detail = resp.json()["detail"]
    assert "DELIBERATE CHUNKING FAILURE FOR TEST" in detail, (
        f"Expected the chunking error message in the response, got: {detail}"
    )
    print(f"[TEST PASSED] Chunking failure surfaced as HTTP 500: {detail}")
