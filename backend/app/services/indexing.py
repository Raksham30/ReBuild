"""
Chunk index. Azure AI Search (hybrid vector + keyword, free F0 tier is
plenty for a project-sized paper library) when configured, otherwise a
local numpy-backed cosine index persisted to disk as .npz + .jsonl.
Same query contract either way: search(query, paper_ids, top_k) -> list[Chunk-like dict].
"""
from __future__ import annotations
import json
import os
import numpy as np
from app.config import get_settings
from app.schemas import Chunk
from app.services.embeddings import embed_texts

CHUNKS_FILE = "chunks.jsonl"
VECTORS_FILE = "vectors.npy"


def index_chunks(chunks: list[Chunk]) -> None:
    if not chunks:
        return
    settings = get_settings()
    if settings.use_azure_search:
        _index_azure(chunks)
    else:
        _index_local(chunks)


def delete_paper_chunks(paper_ids: list[str]) -> None:
    """Removes every indexed chunk belonging to the given papers."""
    if not paper_ids:
        return
    settings = get_settings()
    if settings.use_azure_search:
        _delete_azure(paper_ids)
    else:
        _delete_local(paper_ids)


def search_chunks_by_paper(query: str, paper_ids: list[str], per_paper_k: int = 3) -> list[dict]:
    """Top chunks for EACH paper (query embedded once). Guarantees every selected
    paper is represented -- a plain top-k over all papers can return chunks from
    only one, which breaks compare/contrast and 'summarise each paper' questions.

    Uses ThreadPoolExecutor(max_workers=4) to query papers in parallel."""
    if not paper_ids:
        return []
    from concurrent.futures import ThreadPoolExecutor
    vector = embed_texts([query])[0]

    def _search_one(pid):
        return search_chunks(query, [pid], top_k=per_paper_k, query_vector=vector)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {pid: executor.submit(_search_one, pid) for pid in paper_ids}
        results: list[dict] = []
        # Collect in original paper_ids order to preserve deterministic ordering
        for pid in paper_ids:
            results.extend(futures[pid].result())
    return results


def search_chunks(query: str, paper_ids: list[str] | None, top_k: int = 8, query_vector=None) -> list[dict]:
    # An EMPTY list means "no papers in scope" (e.g. a workspace whose papers were
    # all deleted) -- it must not fall through to an unfiltered, cross-workspace search.
    if paper_ids is not None and len(paper_ids) == 0:
        return []
    settings = get_settings()
    if settings.use_azure_search:
        return _search_azure(query, paper_ids, top_k, query_vector)
    return _search_local(query, paper_ids, top_k, query_vector)


# ---------------- Azure AI Search path ----------------

def _get_azure_search_client():
    from azure.search.documents import SearchClient
    from azure.core.credentials import AzureKeyCredential
    settings = get_settings()
    return SearchClient(
        endpoint=settings.ai_search_url,
        index_name=settings.ai_search_index_name,
        credential=AzureKeyCredential(settings.ai_search_admin_key),
    )


def ensure_azure_index_exists() -> None:
    """Create or update the Azure AI Search index safely. Safe to call repeatedly."""
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        SearchIndex, SimpleField, SearchableField, SearchField, SearchFieldDataType,
        VectorSearch, HnswAlgorithmConfiguration, VectorSearchProfile,
    )
    from azure.core.credentials import AzureKeyCredential
    from app.services.embeddings import embedding_dim

    settings = get_settings()
    index_client = SearchIndexClient(
        endpoint=settings.ai_search_url,
        credential=AzureKeyCredential(settings.ai_search_admin_key),
    )

    dim = embedding_dim()

    existing_indexes = [idx.name for idx in index_client.list_indexes()]
    if settings.ai_search_index_name in existing_indexes:
        existing_idx = index_client.get_index(settings.ai_search_index_name)
        v_field = next((f for f in existing_idx.fields if f.name == "vector"), None)
        if v_field and getattr(v_field, "vector_search_dimensions", None) != dim:
            print(f"Deleting existing index '{settings.ai_search_index_name}' due to vector dimension change ({getattr(v_field, 'vector_search_dimensions', None)} -> {dim})...")
            index_client.delete_index(settings.ai_search_index_name)
        else:
            print(f"Index '{settings.ai_search_index_name}' exists. Updating schema safely.")

    fields = [
        SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="paper_id", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="text", type=SearchFieldDataType.String),
        SimpleField(name="section_type", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="page_start", type=SearchFieldDataType.Int32),
        SimpleField(name="page_end", type=SearchFieldDataType.Int32),
        SearchField(
            name="vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            vector_search_dimensions=dim,
            vector_search_profile_name="default",
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw-cfg")],
        profiles=[VectorSearchProfile(name="default", algorithm_configuration_name="hnsw-cfg")],
    )
    index = SearchIndex(name=settings.ai_search_index_name, fields=fields, vector_search=vector_search)
    index_client.create_or_update_index(index)



def _index_azure(chunks: list[Chunk]) -> None:
    ensure_azure_index_exists()
    vectors = embed_texts([c.text for c in chunks])
    client = _get_azure_search_client()
    docs = []
    for c, v in zip(chunks, vectors):
        docs.append({
            "chunk_id": c.chunk_id, "paper_id": c.paper_id, "text": c.text,
            "section_type": c.section_type, "page_start": c.page_start,
            "page_end": c.page_end, "vector": v,
        })
    results = client.upload_documents(documents=docs)
    failed = [r for r in results if not r.succeeded]
    if failed:
        # upload_documents() does NOT raise on a per-document rejection (e.g.
        # a vector whose length doesn't match the index's configured
        # dimension) -- it just returns a per-doc result list, so the
        # request "succeeds" and the paper shows as "indexed" while the
        # chunk silently never lands in the index and can never be found
        # by search. Surface it loudly instead of leaving it to look like
        # an empty/irrelevant-question problem later.
        details = "; ".join(f"{r.key}: {r.error_message}" for r in failed[:5])
        raise RuntimeError(
            f"Azure AI Search rejected {len(failed)}/{len(docs)} chunk(s) during "
            f"upload_documents -- these are NOT searchable even though the paper "
            f"will otherwise show as 'indexed'. First failure(s): {details}"
        )


def _search_azure(query: str, paper_ids: list[str] | None, top_k: int, query_vector=None) -> list[dict]:
    from azure.search.documents.models import VectorizedQuery
    client = _get_azure_search_client()
    vector = query_vector if query_vector is not None else embed_texts([query])[0]
    filter_str = None
    if paper_ids:
        ids = " or ".join(f"paper_id eq '{pid}'" for pid in paper_ids)
        filter_str = f"({ids})"
    results = client.search(
        search_text=query,
        vector_queries=[VectorizedQuery(vector=vector, k_nearest_neighbors=top_k, fields="vector")],
        filter=filter_str,
        top=top_k,
    )
    return [dict(r) for r in results]


def _delete_azure(paper_ids: list[str]) -> None:
    client = _get_azure_search_client()
    for pid in paper_ids:
        while True:
            hits = list(client.search(
                search_text="*", filter=f"paper_id eq '{pid}'", select=["chunk_id"], top=1000,
            ))
            if not hits:
                break
            client.delete_documents(documents=[{"chunk_id": h["chunk_id"]} for h in hits])


# ---------------- Local fallback path ----------------

def _paths():
    settings = get_settings()
    return (
        os.path.join(settings.local_index_dir, CHUNKS_FILE),
        os.path.join(settings.local_index_dir, VECTORS_FILE),
    )


def _load_local():
    chunks_path, vectors_path = _paths()
    chunks: list[dict] = []
    if os.path.exists(chunks_path):
        with open(chunks_path) as f:
            chunks = [json.loads(line) for line in f]
    vectors = np.load(vectors_path) if os.path.exists(vectors_path) else np.zeros((0, 0))
    return chunks, vectors


def _index_local(chunks: list[Chunk]) -> None:
    chunks_path, vectors_path = _paths()
    os.makedirs(os.path.dirname(chunks_path), exist_ok=True)
    existing_chunks, existing_vectors = _load_local()
    new_vectors = np.array(embed_texts([c.text for c in chunks]))

    if existing_vectors.size == 0:
        all_vectors = new_vectors
    else:
        all_vectors = np.vstack([existing_vectors, new_vectors])

    with open(chunks_path, "a") as f:
        for c in chunks:
            f.write(json.dumps(c.model_dump()) + "\n")
    np.save(vectors_path, all_vectors)


def _search_local(query: str, paper_ids: list[str] | None, top_k: int, query_vector=None) -> list[dict]:
    chunks, vectors = _load_local()
    if not chunks or vectors.size == 0:
        return []
    q_vec = np.array(query_vector if query_vector is not None else embed_texts([query])[0])

    mask = np.array([
        (paper_ids is None or c["paper_id"] in paper_ids) for c in chunks
    ])
    if not mask.any():
        return []

    candidate_idx = np.where(mask)[0]
    candidate_vectors = vectors[candidate_idx]

    norms = np.linalg.norm(candidate_vectors, axis=1) * (np.linalg.norm(q_vec) + 1e-9)
    norms[norms == 0] = 1e-9
    sims = candidate_vectors @ q_vec / norms

    top_local_idx = np.argsort(-sims)[:top_k]
    results = []
    for i in top_local_idx:
        real_idx = candidate_idx[i]
        c = dict(chunks[real_idx])
        c["@search.score"] = float(sims[i])
        results.append(c)
    return results


def _delete_local(paper_ids: list[str]) -> None:
    chunks, vectors = _load_local()
    if not chunks:
        return
    drop = set(paper_ids)
    keep = [i for i, c in enumerate(chunks) if c["paper_id"] not in drop]
    if len(keep) == len(chunks):
        return
    chunks_path, vectors_path = _paths()
    with open(chunks_path, "w") as f:
        for i in keep:
            f.write(json.dumps(chunks[i]) + "\n")
    np.save(vectors_path, vectors[keep] if keep else np.zeros((0, 0)))
