from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth import get_current_uid
from app.schemas import Workspace, RenameRequest
from app.services import storage, indexing, file_storage

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    name: str


def require_owned_workspace(workspace_id: str, uid: str) -> Workspace:
    ws = storage.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(404, "Workspace not found")
    if ws.owner_uid != uid:
        raise HTTPException(403, "You don't have access to this workspace")
    return ws


@router.post("", response_model=Workspace)
def create_workspace(req: CreateWorkspaceRequest, uid: str = Depends(get_current_uid)):
    return storage.create_workspace(uid, req.name)


@router.get("", response_model=list[Workspace])
def list_my_workspaces(uid: str = Depends(get_current_uid)):
    """This is the 'history' shown on the dashboard after login."""
    return storage.list_workspaces(uid)


@router.get("/{workspace_id}", response_model=Workspace)
def get_workspace(workspace_id: str, uid: str = Depends(get_current_uid)):
    return require_owned_workspace(workspace_id, uid)


@router.patch("/{workspace_id}", response_model=Workspace)
def rename_workspace(workspace_id: str, req: RenameRequest, uid: str = Depends(get_current_uid)):
    require_owned_workspace(workspace_id, uid)
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "Name cannot be empty")
    if len(name) > 120:
        raise HTTPException(400, "Name is too long (max 120 characters)")
    return storage.rename_workspace(workspace_id, name)


@router.delete("/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: str, uid: str = Depends(get_current_uid)):
    """Permanently deletes a workspace with all its papers, index chunks and files."""
    require_owned_workspace(workspace_id, uid)

    paper_ids = [p.paper_id for p in storage.list_papers(workspace_id)]
    indexing.delete_paper_chunks(paper_ids)

    try:
        file_storage.delete_workspace_files(workspace_id)
    except Exception as e:
        print(f"[delete_workspace] could not remove stored files for {workspace_id}: {e}")

    storage.delete_workspace(workspace_id, uid)
