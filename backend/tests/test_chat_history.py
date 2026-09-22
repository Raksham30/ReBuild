"""Unit and integration tests for persistent chat history."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from test_delete import client, _add_paper, UID  # noqa: F401  (fixture + seeding helper)


def test_chat_history_persistence_and_scoping(client, monkeypatch):
    from app.services import generation

    # 1. Create two separate workspaces A and B
    ws_a = client.post("/workspaces", json={"name": "Workspace A"}).json()["workspace_id"]
    ws_b = client.post("/workspaces", json={"name": "Workspace B"}).json()["workspace_id"]

    _add_paper(ws_a, "paper_a1", text="Quantum computing principles and algorithms.", title="Quantum Paper")
    _add_paper(ws_b, "paper_b1", text="CRISPR gene editing in agriculture.", title="CRISPR Paper")

    # Mock generation
    def fake_generate(system, user, max_tokens=600):
        if "Quantum" in user or "quantum" in user:
            return "Quantum computing uses qubits to represent complex states."
        return "CRISPR allows precise genome editing."

    monkeypatch.setattr(generation, "generate", fake_generate)

    # Initially both workspaces should have empty chat history
    res_a = client.get(f"/workspaces/{ws_a}/chat/history")
    assert res_a.status_code == 200
    assert res_a.json()["messages"] == []

    res_b = client.get(f"/workspaces/{ws_b}/chat/history")
    assert res_b.status_code == 200
    assert res_b.json()["messages"] == []

    # 2. Ask question in Workspace A
    q_a1 = "What is quantum computing about?"
    ask_res_a = client.post(
        f"/workspaces/{ws_a}/chat/ask",
        json={"question": q_a1, "paper_ids": ["paper_a1"]}
    )
    assert ask_res_a.status_code == 200
    assert "qubits" in ask_res_a.json()["answer"]

    # 3. Verify Workspace A history contains user question + assistant answer
    hist_a = client.get(f"/workspaces/{ws_a}/chat/history").json()["messages"]
    assert len(hist_a) == 2
    assert hist_a[0]["role"] == "user"
    assert hist_a[0]["content"] == q_a1
    assert hist_a[1]["role"] == "assistant"
    assert "qubits" in hist_a[1]["content"]
    assert len(hist_a[1]["citations"]) == 1
    assert hist_a[1]["citations"][0]["paper_title"] == "Quantum Paper"

    # 4. Verify Workspace B history is STILL EMPTY (Workspace isolation)
    hist_b = client.get(f"/workspaces/{ws_b}/chat/history").json()["messages"]
    assert len(hist_b) == 0

    # 5. Ask question in Workspace B
    q_b1 = "What is CRISPR?"
    client.post(
        f"/workspaces/{ws_b}/chat/ask",
        json={"question": q_b1, "paper_ids": ["paper_b1"]}
    )

    # 6. Verify Workspace B has its own conversation history
    hist_b_updated = client.get(f"/workspaces/{ws_b}/chat/history").json()["messages"]
    assert len(hist_b_updated) == 2
    assert hist_b_updated[0]["content"] == q_b1
    assert "CRISPR" in hist_b_updated[1]["content"]

    # Workspace A history remains unchanged
    hist_a_recheck = client.get(f"/workspaces/{ws_a}/chat/history").json()["messages"]
    assert len(hist_a_recheck) == 2
    assert hist_a_recheck[0]["content"] == q_a1

    # 7. Ask second question in Workspace A and verify chronological ordering
    q_a2 = "What datasets were used?"
    client.post(
        f"/workspaces/{ws_a}/chat/ask",
        json={"question": q_a2, "paper_ids": ["paper_a1"]}
    )
    hist_a_final = client.get(f"/workspaces/{ws_a}/chat/history").json()["messages"]
    assert len(hist_a_final) == 4
    assert [m["role"] for m in hist_a_final] == ["user", "assistant", "user", "assistant"]
    assert hist_a_final[2]["content"] == q_a2


def test_authorization_protection(client):
    ws = client.post("/workspaces", json={"name": "Private WS"}).json()["workspace_id"]

    # Switch client user to unauthorized user
    client.current["uid"] = "unauthorized_user"

    # Reading or asking should return 403 Forbidden
    assert client.get(f"/workspaces/{ws}/chat/history").status_code == 403
    assert client.post(f"/workspaces/{ws}/chat/ask", json={"question": "hack?"}).status_code == 403


def test_gemini_failure_preserves_user_message_without_fake_assistant_response(client, monkeypatch):
    from app.services import generation, indexing, embeddings

    monkeypatch.setattr(indexing, "embed_texts", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])

    ws = client.post("/workspaces", json={"name": "Fail WS"}).json()["workspace_id"]
    _add_paper(ws, "p1", text="Sample paper text", title="Sample")

    def failing_generate(system, user, max_tokens=600):
        raise generation.LLMUnavailableError("Gemini API quota exhausted", 429)

    monkeypatch.setattr(generation, "generate", failing_generate)

    # Send ask request which will fail during generation
    q = "Will this fail?"
    res = client.post(f"/workspaces/{ws}/chat/ask", json={"question": q, "paper_ids": ["p1"]})
    assert res.status_code == 429

    # User message must be preserved in history, and NO fake assistant response should be created
    hist = client.get(f"/workspaces/{ws}/chat/history").json()["messages"]
    assert len(hist) == 1
    assert hist[0]["role"] == "user"
    assert hist[0]["content"] == q


def test_delete_workspace_cleans_chat_messages(client):
    from app.services import storage

    ws = client.post("/workspaces", json={"name": "To Delete"}).json()["workspace_id"]
    storage.save_chat_message(ws, "user", "Hello")
    assert len(storage.list_chat_messages(ws)) == 1

    # Delete workspace
    del_res = client.delete(f"/workspaces/{ws}")
    assert del_res.status_code == 204

    # Chat messages for that workspace must be deleted
    assert len(storage.list_chat_messages(ws)) == 0
