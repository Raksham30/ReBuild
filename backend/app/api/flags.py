from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from app.auth import get_current_uid
from app.api.workspaces import require_owned_workspace
from app.schemas import Flag, FlagStatusUpdate
from app.services import storage

router = APIRouter(
    prefix="/workspaces/{workspace_id}/flags",
    tags=["flags"],
)


@router.get("", response_model=list[Flag])
def list_flags(
    workspace_id: str,
    include_dismissed: bool = False,
    uid: str = Depends(get_current_uid),
):
    """Return all stored contradiction flags for this workspace.

    Pass ?include_dismissed=true to also return dismissed flags.
    Flags are created automatically in the background after each paper upload.
    """
    require_owned_workspace(workspace_id, uid)
    raw_flags = storage.list_flags(workspace_id, include_dismissed=include_dismissed)
    # Validate and coerce each raw dict through the Flag schema.
    # Flags that are missing required fields (e.g. saved before this schema
    # existed) are silently skipped so they don't break the response.
    results: list[Flag] = []
    for f in raw_flags:
        try:
            results.append(Flag(**f))
        except Exception:
            pass
    return results


@router.patch("/{flag_id}", status_code=204)
def update_flag_status(
    workspace_id: str,
    flag_id: str,
    req: FlagStatusUpdate,
    uid: str = Depends(get_current_uid),
):
    """Update a flag's status to 'seen' or 'dismissed'.

    Dismissing removes the flag from the default list view.
    Returns 204 No Content on success.
    """
    require_owned_workspace(workspace_id, uid)

    # Verify the flag actually belongs to this workspace before updating.
    flags = storage.list_flags(workspace_id, include_dismissed=True)
    flag_ids = {f["flag_id"] for f in flags}
    if flag_id not in flag_ids:
        raise HTTPException(status_code=404, detail="Flag not found")

    storage.update_flag_status(workspace_id, flag_id, req.status)
