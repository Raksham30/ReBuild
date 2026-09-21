"""Gemini quota exhaustion must surface as a clean 429 with a readable message, not a 500."""
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_llm_quota_error_becomes_429(monkeypatch):
    from app.main import app
    from app.auth import get_current_uid
    from app.api import chat
    from app.schemas import Workspace
    from app.services import agent
    from app.services.generation import LLMUnavailableError

    app.dependency_overrides[get_current_uid] = lambda: "u1"
    monkeypatch.setattr(chat, "require_owned_workspace",
                        lambda ws, uid: Workspace(workspace_id=ws, owner_uid=uid, name="n", created_at="", updated_at=""))
    monkeypatch.setattr(chat.storage, "list_papers", lambda ws: [])

    def boom(*a, **k):
        raise LLMUnavailableError("Gemini API quota exhausted", 429)
    monkeypatch.setattr(agent, "answer_question", boom)

    try:
        r = TestClient(app).post("/workspaces/w1/chat/ask", json={"question": "hi"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 429
    assert "quota" in r.json()["detail"].lower()
