from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from app.auth import get_current_uid
from app.api.workspaces import require_owned_workspace
from app.schemas import Flag, FlagStatusUpdate, ContradictionStatus
from app.services import storage, agent

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
    results: list[Flag] = []
    for f in raw_flags:
        try:
            results.append(Flag(**f))
        except Exception:
            pass
    return results


@router.get("/status", response_model=ContradictionStatus)
def get_flag_status(
    workspace_id: str,
    uid: str = Depends(get_current_uid),
):
    """Return the contradiction analysis status for this workspace."""
    require_owned_workspace(workspace_id, uid)
    status_dict = storage.get_contradiction_status(workspace_id)
    return ContradictionStatus(**status_dict)


@router.post("/run", response_model=ContradictionStatus)
def run_flag_analysis(
    workspace_id: str,
    uid: str = Depends(get_current_uid),
):
    """Trigger contradiction analysis across indexed papers in this workspace."""
    require_owned_workspace(workspace_id, uid)
    papers = storage.list_papers(workspace_id)
    paper_ids = [p.paper_id for p in papers if p.status == "indexed"]

    if len(paper_ids) < 2:
        raise HTTPException(
            status_code=400,
            detail="Upload and index at least 2 papers to check for conflicting claims."
        )

    storage.save_contradiction_status(
        workspace_id,
        status="running",
        analyzed_paper_count=len(paper_ids)
    )

    try:
        pairs, checked = agent.find_contradictions(workspace_id, paper_ids)
        existing_flags = storage.list_flags(workspace_id, include_dismissed=True)
        
        for pair in pairs:
            flag_dict = {
                "type": "contradiction",
                "status": "new",
                "paper_ids_involved": [pair.paper_a_id, pair.paper_b_id],
                "payload": pair.model_dump(),
            }
            already_exists = any(
                f.get("payload", {}).get("paper_a_id") == pair.paper_a_id and
                f.get("payload", {}).get("paper_b_id") == pair.paper_b_id and
                f.get("payload", {}).get("claim_a") == pair.claim_a
                for f in existing_flags
            )
            if not already_exists:
                storage.save_flag(workspace_id, flag_dict)

        status_dict = storage.save_contradiction_status(
            workspace_id,
            status="completed",
            analyzed_paper_count=len(paper_ids),
            error=None
        )
        return ContradictionStatus(**status_dict)
    except Exception as e:
        status_dict = storage.save_contradiction_status(
            workspace_id,
            status="failed",
            error=str(e)
        )
        return ContradictionStatus(**status_dict)


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

    flags = storage.list_flags(workspace_id, include_dismissed=True)
    flag_ids = {f["flag_id"] for f in flags}
    if flag_id not in flag_ids:
        raise HTTPException(status_code=404, detail="Flag not found")

    storage.update_flag_status(workspace_id, flag_id, req.status)
