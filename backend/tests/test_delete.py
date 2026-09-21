"""
Delete paper / delete workspace. Runs fully offline: forces every Azure/Firebase
service off (even if a real .env exists), uses a temp data dir, and fakes
embeddings -- no network, no Gemini quota.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

UID = "delete_test_user"
OTHER_UID = "someone_else"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    for var in (
        "COSMOS_DB_URI", "COSMOS_DB_KEY", "BLOB_STORAGE_CONNECTION_STRING",
        "AI_SEARCH_URL", "AI_SEARCH_ADMIN_KEY", "FIREBASE_SERVICE_ACCOUNT_PATH",
        "FOUNDRY_PROJECT_ENDPOINT",
    ):
        monkeypatch.setenv(var, "")
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOCAL_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("LOCAL_INDEX_DIR", str(tmp_path / "index"))
    monkeypatch.setenv("LOCAL_METADATA_PATH", str(tmp_path / "metadata.json"))

    from app.config import get_settings
    get_settings.cache_clear()

    from app.services import indexing
    monkeypatch.setattr(indexing, "embed_texts", lambda texts: [[1.0, 0.0, 0.0] for _ in texts])

    from app.main import app
    from app.auth import get_current_uid
    current = {"uid": UID}
    app.dependency_overrides[get_current_uid] = lambda: current["uid"]
    c = TestClient(app)
    c.current = current
    yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _add_paper(ws_id, paper_id, text="hello", title=""):
    """Seeds a paper the way the upload endpoint would (record + file + chunks + extraction)."""
    from app.schemas import Chunk, Paper, StructuredExtraction
    from app.services import file_storage, indexing, storage

    file_storage.save_pdf(ws_id, paper_id, b"%PDF-1.4 fake")
    storage.save_paper(Paper(paper_id=paper_id, workspace_id=ws_id, filename=f"{paper_id}.pdf", title=title, status="indexed"))
    storage.save_extraction(ws_id, paper_id, StructuredExtraction(title=paper_id))
    indexing.index_chunks([
        Chunk(chunk_id=f"{paper_id}-0", paper_id=paper_id, text=text, section_type="other",
              page_start=1, page_end=1, order=0),
    ])


def _chunk_paper_ids():
    from app.services import indexing
    chunks, vectors = indexing._load_local()
    assert len(chunks) == len(vectors)
    return sorted(c["paper_id"] for c in chunks)


def test_delete_paper_removes_record_file_and_chunks_only_for_that_paper(client):
    ws = client.post("/workspaces", json={"name": "ws"}).json()["workspace_id"]
    _add_paper(ws, "aaaa1111")
    _add_paper(ws, "bbbb2222")

    from app.services import storage
    storage.save_flag(ws, {"type": "gap", "paper_ids_involved": ["aaaa1111", "bbbb2222"], "payload": {}})

    assert client.delete(f"/workspaces/{ws}/papers/aaaa1111").status_code == 204

    remaining = [p["paper_id"] for p in client.get(f"/workspaces/{ws}/papers").json()]
    assert remaining == ["bbbb2222"]
    assert _chunk_paper_ids() == ["bbbb2222"]
    assert storage.get_extraction(ws, "aaaa1111") is None
    assert storage.get_extraction(ws, "bbbb2222") is not None
    assert storage.list_flags(ws, include_dismissed=True) == []  # flag referenced the deleted paper
    assert not os.path.exists(os.path.join(os.environ["LOCAL_UPLOAD_DIR"], ws, "aaaa1111.pdf"))
    assert os.path.exists(os.path.join(os.environ["LOCAL_UPLOAD_DIR"], ws, "bbbb2222.pdf"))

    assert client.delete(f"/workspaces/{ws}/papers/aaaa1111").status_code == 404


def test_delete_workspace_removes_everything_and_leaves_other_workspaces(client):
    ws1 = client.post("/workspaces", json={"name": "one"}).json()["workspace_id"]
    ws2 = client.post("/workspaces", json={"name": "two"}).json()["workspace_id"]
    _add_paper(ws1, "aaaa1111")
    _add_paper(ws1, "cccc3333")
    _add_paper(ws2, "bbbb2222")

    assert client.delete(f"/workspaces/{ws1}").status_code == 204

    assert client.get(f"/workspaces/{ws1}").status_code == 404
    assert [w["workspace_id"] for w in client.get("/workspaces").json()] == [ws2]
    assert _chunk_paper_ids() == ["bbbb2222"]
    assert not os.path.exists(os.path.join(os.environ["LOCAL_UPLOAD_DIR"], ws1))
    assert len(client.get(f"/workspaces/{ws2}/papers").json()) == 1


def test_cannot_delete_someone_elses_workspace_or_paper(client):
    ws = client.post("/workspaces", json={"name": "mine"}).json()["workspace_id"]
    _add_paper(ws, "aaaa1111")

    client.current["uid"] = OTHER_UID
    assert client.delete(f"/workspaces/{ws}/papers/aaaa1111").status_code == 403
    assert client.delete(f"/workspaces/{ws}").status_code == 403

    client.current["uid"] = UID
    assert len(client.get(f"/workspaces/{ws}/papers").json()) == 1


def test_search_with_empty_paper_scope_returns_nothing(client):
    from app.services import indexing
    ws = client.post("/workspaces", json={"name": "ws"}).json()["workspace_id"]
    _add_paper(ws, "aaaa1111")
    assert indexing.search_chunks("hello", [], top_k=5) == []


class _FakeCosmosContainer:
    """Container whose real partition key is hierarchical (/pk + /workspace_id), unlike
    what the code assumes (/workspace_id): read_item/delete_item with the wrong key fail.
    reject_deletes=True simulates a layout we can't build a valid key for at all."""

    def __init__(self, reject_deletes=False):
        self.items = {}
        self.reject_deletes = reject_deletes

    def read(self):
        return {"partitionKey": {"paths": ["/pk", "/workspace_id"], "kind": "MultiHash"}}

    def upsert_item(self, item):
        item = dict(item)
        item["pk"] = "PK-" + item["id"]          # the server derives the key from the body
        self.items[item["id"]] = item

    def _key(self, it):
        return [it["pk"], it["workspace_id"]]

    def read_item(self, item, partition_key):
        it = self.items.get(item)
        if not it or self._key(it) != partition_key:
            raise KeyError("404")
        return it

    def delete_item(self, item, partition_key):
        it = self.items.get(item)
        if self.reject_deletes or not isinstance(partition_key, list) or len(partition_key) != 2:
            raise ValueError("partition key has fewer components than defined in the collection")
        if not it or self._key(it) != partition_key:
            raise KeyError("404")
        del self.items[item]

    def query_items(self, query, parameters, **kw):
        p = {x["name"]: x["value"] for x in parameters}
        hide_deleted = "IS_DEFINED(c.deleted)" in query
        out = []
        for it in self.items.values():
            if hide_deleted and it.get("deleted"):
                continue
            if it["id"] != p.get("@id", it["id"]):
                continue
            if "@wid" in p and it.get("workspace_id") != p["@wid"]:
                continue
            out.append(it)
        return out


def _with_fake_cosmos(monkeypatch, **container_kwargs):
    from app.config import get_settings
    from app.services import storage

    monkeypatch.setenv("COSMOS_DB_URI", "https://fake")
    monkeypatch.setenv("COSMOS_DB_KEY", "fake")
    get_settings.cache_clear()
    containers = {}
    monkeypatch.setattr(storage, "_container",
                        lambda name, pk: containers.setdefault(name, _FakeCosmosContainer(**container_kwargs)))
    storage._pk_defs.clear()
    return containers


def test_cosmos_get_and_delete_paper_with_hierarchical_partition_key(monkeypatch):
    from app.config import get_settings
    from app.schemas import Paper
    from app.services import storage

    containers = _with_fake_cosmos(monkeypatch)
    try:
        storage.save_paper(Paper(paper_id="p1", workspace_id="w1", filename="a.pdf"))
        assert storage.get_paper("w1", "p1") is not None      # read_item 404s -> query fallback
        storage.delete_paper("w1", "p1")
        assert storage.get_paper("w1", "p1") is None
        assert containers["papers"].items == {}                # really deleted
    finally:
        get_settings.cache_clear()


def test_cosmos_delete_falls_back_to_tombstone_when_no_key_works(monkeypatch):
    """The user's real failure: 'partition key ... has fewer components than defined'.
    Delete must still succeed from the app's point of view."""
    from app.config import get_settings
    from app.schemas import Paper
    from app.services import storage

    containers = _with_fake_cosmos(monkeypatch, reject_deletes=True)
    try:
        storage.save_paper(Paper(paper_id="p1", workspace_id="w1", filename="a.pdf"))
        storage.save_paper(Paper(paper_id="p2", workspace_id="w1", filename="b.pdf"))
        storage.delete_paper("w1", "p1")                       # must not raise
        assert [p.paper_id for p in storage.list_papers("w1")] == ["p2"]
        assert storage.get_paper("w1", "p1") is None
        assert containers["papers"].items["p1"]["deleted"] is True
    finally:
        get_settings.cache_clear()
