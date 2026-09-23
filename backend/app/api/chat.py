from fastapi import APIRouter, Depends
from app.auth import get_current_uid
from app.api.workspaces import require_owned_workspace
from app.schemas import AskRequest, AskResponse, ChatHistoryResponse
from app.services import agent, storage

router = APIRouter(prefix="/workspaces/{workspace_id}/chat", tags=["chat"])


@router.get("/history", response_model=ChatHistoryResponse)
def get_history(workspace_id: str, uid: str = Depends(get_current_uid)):
    require_owned_workspace(workspace_id, uid)
    messages = storage.list_chat_messages(workspace_id)
    return ChatHistoryResponse(messages=messages)


@router.post("/ask", response_model=AskResponse)
def ask(workspace_id: str, req: AskRequest, uid: str = Depends(get_current_uid)):
    require_owned_workspace(workspace_id, uid)
    workspace_paper_ids = {p.paper_id for p in storage.list_papers(workspace_id)}
    requested = set(req.paper_ids) if req.paper_ids else workspace_paper_ids
    scoped_ids = list(requested & workspace_paper_ids)

    # 1. Save user question message
    storage.save_chat_message(workspace_id, "user", req.question)

    # 2. Run existing RAG / Gemini pipeline
    answer, citations = agent.answer_question(workspace_id, req.question, scoped_ids)

    # 3. Save assistant answer message (with citation metadata)
    storage.save_chat_message(workspace_id, "assistant", answer, citations=citations)

    return AskResponse(answer=answer, citations=citations)


@router.delete("/history", status_code=204)
@router.delete("", status_code=204)
def delete_chat(workspace_id: str, uid: str = Depends(get_current_uid)):
    """Delete all chat messages for this workspace."""
    require_owned_workspace(workspace_id, uid)
    storage.delete_chat_messages(workspace_id)

