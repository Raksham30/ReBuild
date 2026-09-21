"""Rename, cross-paper chat retrieval and the Research Gap feature (offline)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from test_delete import client, _add_paper  # noqa: F401  (fixture + seeding helper)


def test_rename_workspace_and_paper(client):
    ws = client.post("/workspaces", json={"name": "old"}).json()["workspace_id"]
    _add_paper(ws, "aaaa1111")

    r = client.patch(f"/workspaces/{ws}", json={"name": "  New name  "})
    assert r.status_code == 200 and r.json()["name"] == "New name"
    assert client.get(f"/workspaces/{ws}").json()["name"] == "New name"
    assert client.patch(f"/workspaces/{ws}", json={"name": "   "}).status_code == 400

    r = client.patch(f"/workspaces/{ws}/papers/aaaa1111", json={"name": "My renamed paper"})
    assert r.status_code == 200
    papers = client.get(f"/workspaces/{ws}/papers").json()
    assert papers[0]["title"] == "My renamed paper"
    assert client.patch(f"/workspaces/{ws}/papers/nope", json={"name": "x"}).status_code == 404

    client.current["uid"] = "someone_else"
    assert client.patch(f"/workspaces/{ws}", json={"name": "hack"}).status_code == 403
    assert client.patch(f"/workspaces/{ws}/papers/aaaa1111", json={"name": "hack"}).status_code == 403


def test_multi_paper_question_gets_context_from_every_paper(client, monkeypatch):
    from app.services import generation
    ws = client.post("/workspaces", json={"name": "ws"}).json()["workspace_id"]
    _add_paper(ws, "aaaa1111", text="AR capture the flag for cybersecurity education", title="Paper AR")
    _add_paper(ws, "bbbb2222", text="Ensemble model evaluation on tabular data", title="Paper Ensemble")

    seen = {}
    def fake_generate(system, user, max_tokens=600):
        seen["system"], seen["user"] = system, user
        return "Common: none. Paper AR is X. Paper Ensemble is Y."
    monkeypatch.setattr(generation, "generate", fake_generate)

    r = client.post(f"/workspaces/{ws}/chat/ask",
                    json={"question": "anything common in these 2 papers?", "paper_ids": ["aaaa1111", "bbbb2222"]})
    assert r.status_code == 200
    assert "AR capture the flag" in seen["user"] and "Ensemble model evaluation" in seen["user"]
    assert 'paper="Paper AR"' in seen["user"] and 'paper="Paper Ensemble"' in seen["user"]
    assert {c["paper_id"] for c in r.json()["citations"]} == {"aaaa1111", "bbbb2222"}
    assert "compare" in seen["system"].lower()


def test_research_gap_uses_all_indexed_papers(client, monkeypatch):
    from app.services import generation
    ws = client.post("/workspaces", json={"name": "ws"}).json()["workspace_id"]
    _add_paper(ws, "aaaa1111", text="Limitations: only English datasets were tested", title="Paper One")
    _add_paper(ws, "bbbb2222", text="Future work: real-time deployment is untested", title="Paper Two")

    seen = {}
    def fake_generate(system, user, max_tokens=600):
        seen["user"], seen["max_tokens"] = user, max_tokens
        return "1. **Multilingual coverage**\nWhy it's a gap: ...\nPossible direction: ..."
    monkeypatch.setattr(generation, "generate", fake_generate)

    r = client.post(f"/workspaces/{ws}/research/gap-analysis", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["found_gap"] is True and "Multilingual" in body["analysis"]
    assert "Paper One" in seen["user"] and "Paper Two" in seen["user"]
    assert "only English datasets" in seen["user"] and "real-time deployment" in seen["user"]
    assert seen["max_tokens"] >= 2000


def test_research_gap_with_no_papers(client):
    ws = client.post("/workspaces", json={"name": "empty"}).json()["workspace_id"]
    r = client.post(f"/workspaces/{ws}/research/gap-analysis", json={})
    assert r.status_code == 200 and r.json()["found_gap"] is False


def test_save_flag_with_pydantic_payload_and_lock_always_released(client):
    """Regression: a Citation object inside a flag payload used to crash json.dump in
    the local DB handle *before* the lock was released, hanging every later request."""
    from app.schemas import Citation
    from app.services import storage

    ws = client.post("/workspaces", json={"name": "ws"}).json()["workspace_id"]
    cit = Citation(paper_id="p", paper_title="t", section_type="other", page_start=1, page_end=1, snippet="s")
    storage.save_flag(ws, {"type": "contradiction", "paper_ids_involved": ["p"], "payload": {"c": cit}})
    flags = storage.list_flags(ws)
    assert flags[0]["payload"]["c"]["paper_title"] == "t"

    # Even if the write itself fails, the lock must be released.
    class Boom:
        def model_dump(self):
            raise RuntimeError("boom")
    try:
        with storage._local_db() as db:
            db["workspaces"]["x"] = Boom()
    except RuntimeError:
        pass
    assert storage.list_workspaces(UID_FOR_TEST)  is not None   # would hang forever if the lock leaked


UID_FOR_TEST = "delete_test_user"
