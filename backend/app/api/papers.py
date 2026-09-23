from __future__ import annotations
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    HTTPException,
    Depends,
    BackgroundTasks,
)

from app.auth import get_current_uid
from app.api.workspaces import require_owned_workspace
from app.schemas import Paper, StructuredExtraction
from app.services import (
    parsing,
    chunking,
    indexing,
    extraction,
    storage,
    file_storage,
    agent,
)
from app.services.generation import LLMUnavailableError
from app.schemas import RenameRequest


router = APIRouter(
    prefix="/workspaces/{workspace_id}/papers",
    tags=["papers"],
)


# Maximum allowed PDF size: 20 MB
MAX_PDF_SIZE = 20 * 1024 * 1024

# Read/upload in small chunks instead of loading the entire PDF into RAM
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB


def _run_background_flags(workspace_id: str, new_paper_id: str):
    """
    Runs after upload response is returned.

    Contradiction checking is incremental:
    only compare the newly uploaded paper against existing papers.
    """
    try:
        all_papers = [
            p.paper_id
            for p in storage.list_papers(workspace_id)
            if p.status == "indexed"
        ]

        if len(all_papers) < 2:
            return

        storage.save_contradiction_status(
            workspace_id,
            status="running",
            analyzed_paper_count=len(all_papers)
        )

        existing = [
            pid
            for pid in all_papers
            if pid != new_paper_id
        ]

        new_flags = agent.find_new_contradiction_flags(
            workspace_id,
            new_paper_id,
            existing,
        )

        for flag in new_flags:
            storage.save_flag(workspace_id, flag)

        storage.save_contradiction_status(
            workspace_id,
            status="completed",
            analyzed_paper_count=len(all_papers),
            error=None
        )

    except Exception as exc:
        storage.save_contradiction_status(
            workspace_id,
            status="failed",
            error=str(exc)
        )


@router.post("/upload", response_model=Paper)
async def upload_paper(
    workspace_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    uid: str = Depends(get_current_uid),
):
    # ---------------------------------------------------------
    # 0. Start total upload timer
    # ---------------------------------------------------------

    t_upload_start = time.perf_counter()

    # ---------------------------------------------------------
    # 1. Check workspace ownership
    # ---------------------------------------------------------

    require_owned_workspace(workspace_id, uid)

    # ---------------------------------------------------------
    # 2. Validate file type
    # ---------------------------------------------------------

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No file selected",
        )

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported",
        )

    # ---------------------------------------------------------
    # 3. Generate paper ID
    # ---------------------------------------------------------

    paper_id = str(uuid.uuid4())[:8]

    # ---------------------------------------------------------
    # 4. Read PDF in chunks
    #
    # IMPORTANT:
    # Do NOT use:
    #
    #     content = await file.read()
    #
    # because that loads the complete PDF into RAM.
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # 4. Read PDF in chunks
    # ---------------------------------------------------------
    import psutil
    def _mem_mb():
        return psutil.Process().memory_info().rss / (1024 * 1024)

    m_start = _mem_mb()
    print(f"[MEM INSTRUMENTATION] Start upload_paper RSS: {m_start:.2f} MB")

    content_chunks = []
    total_size = 0

    try:
        while True:
            chunk = await file.read(UPLOAD_CHUNK_SIZE)

            if not chunk:
                break

            total_size += len(chunk)

            if total_size > MAX_PDF_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"PDF too large. "
                        f"Maximum allowed size is "
                        f"{MAX_PDF_SIZE / (1024 * 1024):.0f} MB."
                    ),
                )

            content_chunks.append(chunk)

    finally:
        await file.close()

    content = b"".join(content_chunks)
    t_file_read = time.perf_counter()
    print(f"[TIME INSTRUMENTATION] File read took {t_file_read - t_upload_start:.2f} s")
    m_read = _mem_mb()
    print(f"[MEM INSTRUMENTATION] After file.read ({total_size} bytes): {m_read:.2f} MB (delta: {m_read - m_start:+.2f} MB)")

    # ---------------------------------------------------------
    # 6. Save PDF to storage
    # ---------------------------------------------------------

    _storage_path, local_path = file_storage.save_pdf(
        workspace_id,
        paper_id,
        content,
    )

    # ---------------------------------------------------------
    # 7. Create initial paper record
    # ---------------------------------------------------------

    paper = Paper(
        paper_id=paper_id,
        workspace_id=workspace_id,
        filename=file.filename,
        status="parsing",
    )

    storage.save_paper(paper)

    # ---------------------------------------------------------
    # 8. Parse, chunk, index and extract (with timing + concurrency)
    # ---------------------------------------------------------

    try:
        # ---- Parse PDF ----
        t0_parse = time.perf_counter()
        t0_mem = _mem_mb()
        sections, num_pages = parsing.parse_pdf(local_path)
        t1_parse = time.perf_counter()
        t1_mem = _mem_mb()
        print(f"[TIME INSTRUMENTATION] parse_pdf took {t1_parse - t0_parse:.2f} s")
        print(f"[MEM INSTRUMENTATION] After parse_pdf ({num_pages} pages, {len(sections)} sections): {t1_mem:.2f} MB (delta: {t1_mem - t0_mem:+.2f} MB)")

        # ---- Concurrent: chunking+indexing || extraction ----
        def _process_chunks(secs):
            t_chunk_start = time.perf_counter()
            cks = chunking.chunk_sections(paper_id, secs)
            t_chunk_end = time.perf_counter()
            print(f"[TIME INSTRUMENTATION] chunk_sections took {t_chunk_end - t_chunk_start:.2f} s")

            t_index_start = time.perf_counter()
            indexing.index_chunks(cks)
            t_index_end = time.perf_counter()
            print(f"[TIME INSTRUMENTATION] index_chunks took {t_index_end - t_index_start:.2f} s")
            return cks

        def _process_extraction(secs):
            t_ext_start = time.perf_counter()
            flds = extraction.extract_structured_fields(paper_id, secs)
            t_ext_end = time.perf_counter()
            print(f"[TIME INSTRUMENTATION] extract_structured_fields took {t_ext_end - t_ext_start:.2f} s")
            return flds

        t_concurrent_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_chunks = executor.submit(_process_chunks, sections)
            future_fields = executor.submit(_process_extraction, sections)
            try:
                chunks_result = future_chunks.result()   # will raise if processing fails
                fields = future_fields.result()          # will raise if processing fails
            except Exception as exc:
                # Propagate the exception so FastAPI returns a loud HTTPException
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=str(exc)) from exc
        t_concurrent_end = time.perf_counter()
        print(f"[TIME INSTRUMENTATION] Concurrent chunk+index & extraction took {t_concurrent_end - t_concurrent_start:.2f} s")

        t7_mem = _mem_mb()
        print(f"[MEM INSTRUMENTATION] After extract_structured_fields: {t7_mem:.2f} MB (delta: {t7_mem - t1_mem:+.2f} MB)")
        print(f"[MEM INSTRUMENTATION] Total upload_paper end RSS: {t7_mem:.2f} MB (total delta: {t7_mem - m_start:+.2f} MB)")

        t_total_upload = time.perf_counter()
        print(f"[TIME INSTRUMENTATION] Total upload took {t_total_upload - t_upload_start:.2f} s")

        # Save structured extraction
        storage.save_extraction(
            workspace_id,
            paper_id,
            fields,
        )

        # -----------------------------------------------------
        # 9. Update paper after successful ingestion
        # -----------------------------------------------------

        title = fields.title or file.filename

        paper = Paper(
            paper_id=paper_id,
            workspace_id=workspace_id,
            filename=file.filename,
            title=title,
            num_pages=num_pages,
            status="indexed",
        )

        storage.save_paper(paper)

        # -----------------------------------------------------
        # 10. Run contradiction/gap analysis in background
        # -----------------------------------------------------

        background_tasks.add_task(
            _run_background_flags,
            workspace_id,
            paper_id,
        )

    except Exception as e:
        traceback.print_exc()

        # Mark paper as failed
        paper.status = "failed"
        storage.save_paper(paper)

        # Quota/overload errors carry their own status (429/503) and a readable message.
        if isinstance(e, LLMUnavailableError):
            raise HTTPException(status_code=e.status_code, detail=str(e))

        raise HTTPException(
            status_code=500,
            detail=f"Ingestion failed: {type(e).__name__}: {e}",
        )

    # ---------------------------------------------------------
    # 11. Return successfully indexed paper
    # ---------------------------------------------------------

    return paper


@router.get("", response_model=list[Paper])
def list_papers(
    workspace_id: str,
    uid: str = Depends(get_current_uid),
):
    require_owned_workspace(
        workspace_id,
        uid,
    )

    return storage.list_papers(workspace_id)


@router.get("/{paper_id}", response_model=Paper)
def get_paper(
    workspace_id: str,
    paper_id: str,
    uid: str = Depends(get_current_uid),
):
    require_owned_workspace(
        workspace_id,
        uid,
    )

    paper = storage.get_paper(
        workspace_id,
        paper_id,
    )

    if not paper:
        raise HTTPException(
            status_code=404,
            detail="Paper not found",
        )

    return paper


@router.get(
    "/{paper_id}/extraction",
    response_model=StructuredExtraction,
)
def get_extraction(
    workspace_id: str,
    paper_id: str,
    uid: str = Depends(get_current_uid),
):
    require_owned_workspace(
        workspace_id,
        uid,
    )

    ext = storage.get_extraction(
        workspace_id,
        paper_id,
    )

    if not ext:
        raise HTTPException(
            status_code=404,
            detail="No extraction found for this paper",
        )

    return ext


@router.delete(
    "/{paper_id}",
    status_code=204,
)
def delete_paper(
    workspace_id: str,
    paper_id: str,
    uid: str = Depends(get_current_uid),
):
    require_owned_workspace(
        workspace_id,
        uid,
    )

    paper = storage.get_paper(
        workspace_id,
        paper_id,
    )

    if not paper:
        raise HTTPException(
            status_code=404,
            detail="Paper not found",
        )

    # Index first (must succeed, otherwise stale chunks would keep
    # showing up in answers), then the file, then the metadata record
    # last so a failed delete can simply be retried.
    indexing.delete_paper_chunks([paper_id])

    try:
        file_storage.delete_pdf(workspace_id, paper_id)
    except Exception as e:
        print(f"[delete_paper] could not remove stored file for {paper_id}: {e}")

    storage.delete_paper(workspace_id, paper_id)


@router.patch("/{paper_id}")
def rename_paper(
    workspace_id: str,
    paper_id: str,
    req: RenameRequest,
    uid: str = Depends(get_current_uid),
):
    require_owned_workspace(workspace_id, uid)
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    if len(name) > 300:
        raise HTTPException(status_code=400, detail="Name is too long (max 300 characters)")
    paper = storage.rename_paper(workspace_id, paper_id, name)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper
