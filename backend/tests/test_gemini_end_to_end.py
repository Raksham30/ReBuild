import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from app.main import app
from app.config import get_settings
from app.auth import get_current_uid

TEST_UID = "test_user_gemini_e2e"
app.dependency_overrides[get_current_uid] = lambda: TEST_UID
client = TestClient(app)

def test_gemini_e2e_flow():
    # Confirm health endpoint
    health_res = client.get("/health").json()
    print("Health check response:", health_res)
    assert health_res["mode"]["embeddings"] == "gemini"

    # 1. Create a workspace
    create_ws = client.post("/workspaces", json={"name": "Gemini RAG Workspace"}).json()
    ws_id = create_ws["workspace_id"]
    print(f"\n[STEP 8] Created Workspace ID: {ws_id}")

    # 2. Upload paper 1
    small_pdf_path = os.path.join("tests", "data", "small_test.pdf")
    with open(small_pdf_path, "rb") as f:
        up1_res = client.post(
            f"/workspaces/{ws_id}/papers/upload",
            files={"file": ("small_test.pdf", f, "application/pdf")}
        )
    assert up1_res.status_code == 200, f"Upload 1 failed: {up1_res.text}"
    paper1 = up1_res.json()
    p1_id = paper1["paper_id"]
    print(f"\n[STEP 8] Uploaded Paper 1: ID={p1_id}, Status={paper1['status']}, Title={paper1['title']}")

    # 3. Upload paper 2
    normal_pdf_path = os.path.join("tests", "data", "normal_paper.pdf")
    with open(normal_pdf_path, "rb") as f:
        up2_res = client.post(
            f"/workspaces/{ws_id}/papers/upload",
            files={"file": ("normal_paper.pdf", f, "application/pdf")}
        )
    assert up2_res.status_code == 200, f"Upload 2 failed: {up2_res.text}"
    paper2 = up2_res.json()
    p2_id = paper2["paper_id"]
    print(f"\n[STEP 8] Uploaded Paper 2: ID={p2_id}, Status={paper2['status']}, Title={paper2['title']}")

    # 4. GET /workspaces/{id}/papers
    import time
    time.sleep(1.0)
    papers_list = client.get(f"/workspaces/{ws_id}/papers").json()
    print(f"\n[STEP 8] GET /workspaces/{ws_id}/papers response JSON:")
    import json
    print(json.dumps(papers_list, indent=2))
    assert len(papers_list) >= 2
    assert all(p["status"] == "indexed" for p in papers_list)

    # 5. GET /workspaces/{id}/papers/{paper_id}/extraction
    ext1 = client.get(f"/workspaces/{ws_id}/papers/{p1_id}/extraction").json()
    print(f"\n[STEP 8] GET /workspaces/{ws_id}/papers/{p1_id}/extraction response JSON:")
    print(json.dumps(ext1, indent=2))
    assert "summary" in ext1 and ext1["summary"] != ""

    # 6. STEP 9: POST /workspaces/{id}/chat/ask
    ask_req = {
        "question": "What neural network architectures, attention mechanisms, and retrieval methods are evaluated in these papers?"
    }
    print(f"\n[STEP 9] POST /workspaces/{ws_id}/chat/ask question: {ask_req['question']}")
    ask_res = client.post(f"/workspaces/{ws_id}/chat/ask", json=ask_req)
    assert ask_res.status_code == 200, f"Chat ask failed: {ask_res.text}"
    ask_data = ask_res.json()
    print(f"\n[STEP 9] POST /workspaces/{ws_id}/chat/ask response JSON:")
    print(json.dumps(ask_data, indent=2))

    assert "answer" in ask_data and ask_data["answer"] != ""
    assert "citations" in ask_data and len(ask_data["citations"]) > 0

    c0 = ask_data["citations"][0]
    assert "paper_title" in c0 and c0["paper_title"] != ""
    assert "section_type" in c0 and c0["section_type"] != ""
    assert "page_start" in c0 and isinstance(c0["page_start"], int)
    print("\n[STEP 9 PASSED] Citation verified successfully:", c0)

if __name__ == "__main__":
    test_gemini_e2e_flow()
