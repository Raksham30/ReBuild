import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


from fastapi.testclient import TestClient
from app.main import app
from app.auth import get_current_uid

TEST_UID = "test_user_regression_123"

def mock_get_current_uid():
    return TEST_UID

# Override get_current_uid for FastAPI TestClient
app.dependency_overrides[get_current_uid] = mock_get_current_uid
client = TestClient(app)


def test_full_upload_regression_suite():
    app.dependency_overrides[get_current_uid] = mock_get_current_uid
    # 1. Create a test workspace
    create_ws_res = client.post("/workspaces", json={"name": "Regression Test Workspace"})
    assert create_ws_res.status_code == 200, f"Workspace creation failed: {create_ws_res.text}"
    ws = create_ws_res.json()
    ws_id = ws["workspace_id"]
    print(f"\n[TEST 1 PASSED] Workspace created: {ws_id}")

    # Paths to generated test files
    small_pdf_path = os.path.join("tests", "data", "small_test.pdf")
    normal_pdf_path = os.path.join("tests", "data", "normal_paper.pdf")
    large_under_20mb_path = os.path.join("tests", "data", "large_under_20mb.pdf")
    over_20mb_path = os.path.join("tests", "data", "over_20mb.pdf")
    non_pdf_path = os.path.join("tests", "data", "non_pdf.txt")

    # 2. Upload small PDF (< 1 MB)
    with open(small_pdf_path, "rb") as f:
        resp = client.post(f"/workspaces/{ws_id}/papers/upload", files={"file": ("small_test.pdf", f, "application/pdf")})
    assert resp.status_code == 200, f"Small PDF upload failed: {resp.status_code} - {resp.text}"
    small_paper = resp.json()
    assert small_paper["status"] == "indexed", f"Status expected 'indexed', got {small_paper['status']}"
    small_paper_id = small_paper["paper_id"]
    print(f"[TEST 2 PASSED] Small PDF uploaded & indexed successfully. Paper ID: {small_paper_id}")

    # 3. Upload normal research paper (10 pages)
    with open(normal_pdf_path, "rb") as f:
        resp = client.post(f"/workspaces/{ws_id}/papers/upload", files={"file": ("normal_paper.pdf", f, "application/pdf")})
    assert resp.status_code == 200, f"Normal paper upload failed: {resp.status_code} - {resp.text}"
    normal_paper = resp.json()
    assert normal_paper["status"] == "indexed"
    normal_paper_id = normal_paper["paper_id"]
    print(f"[TEST 3 PASSED] Normal paper uploaded & indexed successfully. Paper ID: {normal_paper_id}")

    # 4. Upload large PDF under 20 MB (~16 MB)
    with open(large_under_20mb_path, "rb") as f:
        resp = client.post(f"/workspaces/{ws_id}/papers/upload", files={"file": ("large_under_20mb.pdf", f, "application/pdf")})
    assert resp.status_code == 200, f"Large PDF (<20MB) upload failed: {resp.status_code} - {resp.text}"
    large_paper = resp.json()
    assert large_paper["status"] == "indexed"
    print(f"[TEST 4 PASSED] Large PDF under 20MB uploaded & indexed successfully. Paper ID: {large_paper['paper_id']}")

    # 5. Upload PDF over 20 MB -> expect clean 400 rejection
    with open(over_20mb_path, "rb") as f:
        resp = client.post(f"/workspaces/{ws_id}/papers/upload", files={"file": ("over_20mb.pdf", f, "application/pdf")})
    assert resp.status_code == 400, f"Over 20MB PDF expected 400, got {resp.status_code} - {resp.text}"
    assert "PDF too large" in resp.json()["detail"]
    print(f"[TEST 5 PASSED] Over 20MB PDF rejected with clean 400: {resp.json()['detail']}")

    # 6. Upload non-PDF file -> expect clean 400 rejection
    with open(non_pdf_path, "rb") as f:
        resp = client.post(f"/workspaces/{ws_id}/papers/upload", files={"file": ("non_pdf.txt", f, "text/plain")})
    assert resp.status_code == 400, f"Non-PDF file expected 400, got {resp.status_code} - {resp.text}"
    assert "Only PDF files are supported" in resp.json()["detail"]
    print(f"[TEST 6 PASSED] Non-PDF rejected with clean 400: {resp.json()['detail']}")

    # 7. GET /workspaces/{id}/papers lists uploaded papers
    list_resp = client.get(f"/workspaces/{ws_id}/papers")
    assert list_resp.status_code == 200
    papers_list = list_resp.json()
    assert len(papers_list) >= 3
    indexed_ids = [p["paper_id"] for p in papers_list]
    assert small_paper_id in indexed_ids
    assert normal_paper_id in indexed_ids
    print(f"[TEST 7 PASSED] GET /workspaces/{ws_id}/papers listed {len(papers_list)} papers successfully.")

    # 8. GET /workspaces/{id}/papers/{paper_id}/extraction returns populated structured fields
    ext_resp = client.get(f"/workspaces/{ws_id}/papers/{small_paper_id}/extraction")
    assert ext_resp.status_code == 200, f"GET extraction failed: {ext_resp.text}"
    ext_data = ext_resp.json()
    assert "summary" in ext_data and ext_data["summary"] != ""
    print(f"[TEST 8 PASSED] GET /workspaces/{ws_id}/papers/{small_paper_id}/extraction returned populated fields:")
    print(f"   Title: {ext_data.get('title')}")
    print(f"   Summary: {ext_data.get('summary')[:100]}...")


if __name__ == "__main__":
    test_full_upload_regression_suite()
