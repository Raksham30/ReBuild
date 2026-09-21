"""
Metadata store for workspaces/papers/extractions/flags.

Real path:  Cosmos DB (NoSQL API), one database (ResearchDB) with four
            containers created on first use: workspaces, papers,
            extractions, flags. Uses database-level shared throughput so
            all four containers share the same free-tier 1000 RU/s
            instead of each needing their own dedicated allocation.
Fallback:   a single local JSON file with the same shape, for fully
            offline development.
"""
from __future__ import annotations
import json
import os
import uuid
import threading
from datetime import datetime, timezone
from app.config import get_settings
from app.schemas import Workspace, Paper, StructuredExtraction

_lock = threading.Lock()


def _json_default(o):
    """Lets pydantic models (e.g. Citation objects inside flag payloads) be stored as JSON."""
    return o.model_dump() if hasattr(o, "model_dump") else str(o)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _with_retry(fn, retries=3, delay=1.0):
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            if i == retries - 1:
                raise e
            import time
            time.sleep(delay)


# ---- Cosmos helpers: look items up by query, not by a guessed partition key ----
# read_item/delete_item need the exact partition-key value. If a container was
# created earlier with a different partition-key path than the code assumes,
# those calls 404 even though the item exists (and list queries still find it).
# Querying by id and deleting with the container's REAL key path avoids that.

# Items flagged deleted=true (tombstones, see _cosmos_delete) are hidden from every query.
_NOT_DELETED = " AND (NOT IS_DEFINED(c.deleted) OR c.deleted = false)"
_pk_defs: dict[str, dict] = {}


def _cosmos_find(name: str, pk_path: str, item_id: str, workspace_id: str | None = None) -> list[dict]:
    query = "SELECT * FROM c WHERE c.id=@id" + _NOT_DELETED
    params = [{"name": "@id", "value": item_id}]
    if workspace_id is not None:
        query += " AND c.workspace_id=@wid"
        params.append({"name": "@wid", "value": workspace_id})
    return list(_container(name, pk_path).query_items(
        query=query, parameters=params, enable_cross_partition_query=True,
    ))


def _partition_key_for(paths: list[str], item: dict):
    """Builds the partition-key value from the container's REAL key path(s).
    Hierarchical (multi-path) containers need a list with one value per path."""
    values = []
    for path in paths:
        v = item
        for part in path.strip("/").split("/"):
            v = v.get(part) if isinstance(v, dict) else None
        values.append(v)
    return values if len(values) > 1 else values[0]


def _cosmos_delete(name: str, pk_path: str, item_id: str, workspace_id: str | None = None) -> None:
    """Deletes an item whatever the container's partition-key layout is.

    1. real delete using the key built from the container's own key path(s);
    2. real delete using the key the SDK itself derives for upserts;
    3. last resort: a tombstone (deleted=true) written with upsert -- upsert lets the
       server work out the key from the body, so it can't hit a key mismatch. Every
       read/list query above filters tombstones out, so the item is gone for the app.
    """
    container = _container(name, pk_path)
    if name not in _pk_defs:
        _pk_defs[name] = container.read()["partitionKey"]
    pk_def = _pk_defs[name]
    paths = list(pk_def["paths"])

    for item in _cosmos_find(name, pk_path, item_id, workspace_id):
        candidates = [_partition_key_for(paths, item)]
        try:
            sdk_key = container.client_connection._ExtractPartitionKey(pk_def, item)
            if sdk_key not in candidates:
                candidates.append(sdk_key)
        except Exception:
            pass

        last_err = None
        for key in candidates:
            try:
                container.delete_item(item=item["id"], partition_key=key)
                last_err = None
                break
            except Exception as e:
                last_err = e
        if last_err is not None:
            print(f"[storage] real delete failed for {name}/{item_id} "
                  f"(partition key definition: {pk_def}; tried: {candidates}): {last_err}. "
                  f"Falling back to a tombstone.")
            tombstone = dict(item)
            tombstone["deleted"] = True
            container.upsert_item(tombstone)


# ==================== Workspaces ====================

def create_workspace(owner_uid: str, name: str) -> Workspace:
    ws = Workspace(
        workspace_id=str(uuid.uuid4())[:8],
        owner_uid=owner_uid,
        name=name,
        created_at=_now(),
        updated_at=_now(),
    )
    settings = get_settings()
    if settings.use_cosmos:
        item = ws.model_dump()
        item["id"] = ws.workspace_id  # Cosmos requires an 'id' field
        _with_retry(lambda: _container("workspaces", "/owner_uid").upsert_item(item))
    else:
        with _local_db() as db:
            db["workspaces"][ws.workspace_id] = ws.model_dump()
    return ws


def rename_workspace(workspace_id: str, name: str) -> Workspace | None:
    ws = get_workspace(workspace_id)
    if not ws:
        return None
    ws.name = name
    ws.updated_at = _now()
    settings = get_settings()
    if settings.use_cosmos:
        item = ws.model_dump()
        item["id"] = ws.workspace_id
        _with_retry(lambda: _container("workspaces", "/owner_uid").upsert_item(item))
    else:
        with _local_db() as db:
            db["workspaces"][ws.workspace_id] = ws.model_dump()
    return ws


def list_workspaces(owner_uid: str) -> list[Workspace]:
    settings = get_settings()
    if settings.use_cosmos:
        items = _container("workspaces", "/owner_uid").query_items(
            query="SELECT * FROM c WHERE c.owner_uid=@uid" + _NOT_DELETED,
            parameters=[{"name": "@uid", "value": owner_uid}],
            partition_key=owner_uid,
        )
        return [Workspace(**i) for i in items]
    with _local_db() as db:
        return [Workspace(**w) for w in db["workspaces"].values() if w["owner_uid"] == owner_uid]


def get_workspace(workspace_id: str) -> Workspace | None:
    settings = get_settings()
    if settings.use_cosmos:
        items = list(_container("workspaces", "/owner_uid").query_items(
            query="SELECT * FROM c WHERE c.workspace_id=@wid" + _NOT_DELETED,
            parameters=[{"name": "@wid", "value": workspace_id}],
            enable_cross_partition_query=True,
        ))
        return Workspace(**items[0]) if items else None
    with _local_db() as db:
        w = db["workspaces"].get(workspace_id)
        return Workspace(**w) if w else None


def delete_workspace(workspace_id: str, owner_uid: str) -> None:
    """Deletes the workspace record plus every paper, extraction and flag in it.
    (Chunks in the search index and files in blob/disk are removed by the caller.)"""
    for p in list_papers(workspace_id):
        delete_paper(workspace_id, p.paper_id)
    for f in list_flags(workspace_id, include_dismissed=True):
        _delete_flag(workspace_id, f["flag_id"])
    settings = get_settings()
    if settings.use_cosmos:
        _cosmos_delete("workspaces", "/owner_uid", workspace_id)
    else:
        with _local_db() as db:
            db["workspaces"].pop(workspace_id, None)


# ==================== Papers ====================

def save_paper(paper: Paper) -> None:
    settings = get_settings()
    if settings.use_cosmos:
        item = paper.model_dump()
        item["id"] = paper.paper_id
        _with_retry(lambda: _container("papers", "/workspace_id").upsert_item(item))
    else:
        with _local_db() as db:
            db["papers"][paper.paper_id] = paper.model_dump()


def rename_paper(workspace_id: str, paper_id: str, name: str) -> Paper | None:
    """Sets the display name (title) shown in the UI and in citations."""
    paper = get_paper(workspace_id, paper_id)
    if not paper:
        return None
    paper.title = name
    save_paper(paper)
    return paper


def get_paper(workspace_id: str, paper_id: str) -> Paper | None:
    settings = get_settings()
    if settings.use_cosmos:
        try:
            item = _container("papers", "/workspace_id").read_item(item=paper_id, partition_key=workspace_id)
            return None if item.get("deleted") else Paper(**item)
        except Exception:
            found = _cosmos_find("papers", "/workspace_id", paper_id, workspace_id)
            return Paper(**found[0]) if found else None
    with _local_db() as db:
        p = db["papers"].get(paper_id)
        return Paper(**p) if p and p["workspace_id"] == workspace_id else None


def list_papers(workspace_id: str) -> list[Paper]:
    settings = get_settings()
    if settings.use_cosmos:
        items = list(_container("papers", "/workspace_id").query_items(
            query="SELECT * FROM c WHERE c.workspace_id=@wid" + _NOT_DELETED,
            parameters=[{"name": "@wid", "value": workspace_id}],
            enable_cross_partition_query=True,
        ))
        return [Paper(**i) for i in items]
    with _local_db() as db:
        return [Paper(**p) for p in db["papers"].values() if p["workspace_id"] == workspace_id]


def delete_paper(workspace_id: str, paper_id: str) -> None:
    """Deletes the paper record, its extraction, and any flags that involve it."""
    settings = get_settings()
    if settings.use_cosmos:
        for name in ("papers", "extractions"):
            _cosmos_delete(name, "/workspace_id", paper_id, workspace_id)
    else:
        with _local_db() as db:
            db["papers"].pop(paper_id, None)
            db["extractions"].pop(paper_id, None)
    for f in list_flags(workspace_id, include_dismissed=True):
        if paper_id in (f.get("paper_ids_involved") or []):
            _delete_flag(workspace_id, f["flag_id"])


# ==================== Extractions ====================

def save_extraction(workspace_id: str, paper_id: str, extraction: StructuredExtraction) -> None:
    settings = get_settings()
    if settings.use_cosmos:
        item = extraction.model_dump()
        item["id"] = paper_id
        item["workspace_id"] = workspace_id
        item["paper_id"] = paper_id
        _with_retry(lambda: _container("extractions", "/workspace_id").upsert_item(item))
    else:
        with _local_db() as db:
            db["extractions"][paper_id] = extraction.model_dump()


def get_extraction(workspace_id: str, paper_id: str) -> StructuredExtraction | None:
    settings = get_settings()
    if settings.use_cosmos:
        try:
            item = _container("extractions", "/workspace_id").read_item(item=paper_id, partition_key=workspace_id)
            if item.get("deleted"):
                return None
        except Exception:
            found = _cosmos_find("extractions", "/workspace_id", paper_id, workspace_id)
            if not found:
                return None
            item = found[0]
        return StructuredExtraction(**{k: v for k, v in item.items() if k in StructuredExtraction.model_fields})
    with _local_db() as db:
        e = db["extractions"].get(paper_id)
        return StructuredExtraction(**e) if e else None


def get_extractions(workspace_id: str, paper_ids: list[str]) -> dict[str, StructuredExtraction]:
    result = {}
    for pid in paper_ids:
        ext = get_extraction(workspace_id, pid)
        if ext is not None:
            result[pid] = ext
    return result


# ==================== Flags (background gap/contradiction findings) ====================

def save_flag(workspace_id: str, flag: dict) -> None:
    # Flag payloads hold pydantic objects (Citation); normalise to plain JSON for both backends.
    flag = json.loads(json.dumps(flag, default=_json_default))
    flag.setdefault("flag_id", str(uuid.uuid4())[:8])
    flag["workspace_id"] = workspace_id
    flag.setdefault("status", "new")
    flag.setdefault("created_at", _now())
    settings = get_settings()
    if settings.use_cosmos:
        item = dict(flag)
        item["id"] = flag["flag_id"]
        _container("flags", "/workspace_id").upsert_item(item)
    else:
        with _local_db() as db:
            db.setdefault("flags", {})[flag["flag_id"]] = flag


def list_flags(workspace_id: str, include_dismissed: bool = False) -> list[dict]:
    settings = get_settings()
    if settings.use_cosmos:
        items = list(_container("flags", "/workspace_id").query_items(
            query="SELECT * FROM c WHERE c.workspace_id=@wid" + _NOT_DELETED,
            parameters=[{"name": "@wid", "value": workspace_id}],
            partition_key=workspace_id,
        ))
    else:
        with _local_db() as db:
            items = [f for f in db.get("flags", {}).values() if f["workspace_id"] == workspace_id]
    if not include_dismissed:
        items = [f for f in items if f.get("status") != "dismissed"]
    return items


def update_flag_status(workspace_id: str, flag_id: str, status: str) -> None:
    settings = get_settings()
    if settings.use_cosmos:
        container = _container("flags", "/workspace_id")
        item = container.read_item(item=flag_id, partition_key=workspace_id)
        item["status"] = status
        container.upsert_item(item)
    else:
        with _local_db() as db:
            if flag_id in db.get("flags", {}):
                db["flags"][flag_id]["status"] = status


def _delete_flag(workspace_id: str, flag_id: str) -> None:
    settings = get_settings()
    if settings.use_cosmos:
        _cosmos_delete("flags", "/workspace_id", flag_id, workspace_id)
    else:
        with _local_db() as db:
            db.get("flags", {}).pop(flag_id, None)


# ==================== Cosmos client ====================

_cosmos_client = None
_cosmos_db = None
_containers: dict[str, object] = {}


def _get_database():
    global _cosmos_client, _cosmos_db
    if _cosmos_db is None:
        from azure.cosmos import CosmosClient
        settings = get_settings()
        _cosmos_client = CosmosClient(settings.cosmos_db_uri, credential=settings.cosmos_db_key)
        # offer_throughput here sets DATABASE-level shared throughput, so
        # containers created below don't each need their own allocation --
        # keeps everything inside the 1000 RU/s free tier.
        _cosmos_db = _cosmos_client.create_database_if_not_exists(
            id=settings.cosmos_db_database, offer_throughput=400
        )
    return _cosmos_db


def _container(name: str, partition_key_path: str):
    if name not in _containers:
        from azure.cosmos import PartitionKey
        db = _get_database()
        _containers[name] = db.create_container_if_not_exists(
            id=name, partition_key=PartitionKey(path=partition_key_path)
        )
    return _containers[name]


# ==================== Local JSON fallback ====================

class _LocalDbHandle:
    def __enter__(self):
        _lock.acquire()
        self.path = get_settings().local_metadata_path
        if os.path.exists(self.path):
            with open(self.path) as f:
                self.data = json.load(f)
        else:
            self.data = {"workspaces": {}, "papers": {}, "extractions": {}, "flags": {}}
        self.data.setdefault("flags", {})
        return self.data

    def __exit__(self, *exc):
        # try/finally: if writing fails (e.g. non-serialisable data) the lock MUST
        # still be released, otherwise every later metadata call hangs forever.
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            # Write to a temp file and swap it in, so a failed write can't leave a
            # truncated/corrupt metadata file behind.
            tmp_path = self.path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(self.data, f, indent=2, default=_json_default)
            os.replace(tmp_path, self.path)
        finally:
            _lock.release()


def _local_db():
    return _LocalDbHandle()
