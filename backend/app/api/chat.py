from fastapi import APIRouter, Depends
from app.auth import get_current_uid
from app.api.workspaces import require_owned_workspace
from app.schemas import AskRequest, AskResponse
from app.services import agent, storage

router = APIRouter(prefix="/workspaces/{workspace_id}/chat", tags=["chat"])


@router.post("/ask", response_model=AskResponse)
def ask(workspace_id: str, req: AskRequest, uid: str = Depends(get_current_uid)):
    require_owned_workspace(workspace_id, uid)
    # Scope strictly to this workspace's papers, regardless of what the
    # request body claims -- prevents cross-workspace data leakage.
    workspace_paper_ids = {p.paper_id for p in storage.list_papers(workspace_id)}
    requested = set(req.paper_ids) if req.paper_ids else workspace_paper_ids
    scoped_ids = list(requested & workspace_paper_ids)

    answer, citations = agent.answer_question(workspace_id, req.question, scoped_ids)
    return AskResponse(answer=answer, citations=citations)
