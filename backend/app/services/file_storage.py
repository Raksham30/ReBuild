"""
Stores/retrieves the raw uploaded PDF bytes.

Real path:  Azure Blob Storage, under papers/{workspace_id}/{paper_id}.pdf
Fallback:   local disk under data/uploads/{workspace_id}/{paper_id}.pdf

Parsing always needs a local file path to read from, so save_pdf()
returns BOTH a storage_path (what you'd persist/reference) and a
guaranteed-local path to hand to the parser.
"""
import os
import shutil
from app.config import get_settings

_blob_service_client = None


def save_pdf(workspace_id: str, paper_id: str, content: bytes) -> tuple[str, str]:
    """Returns (storage_path, local_path_for_parsing)."""
    settings = get_settings()
    local_dir = os.path.join(settings.local_upload_dir, workspace_id)
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, f"{paper_id}.pdf")
    # Always keep a local copy -- it's our parsing scratch space either way,
    # and it's the only copy at all in fallback mode.
    with open(local_path, "wb") as f:
        f.write(content)

    if settings.use_blob:
        blob_path = f"{workspace_id}/{paper_id}.pdf"
        _upload_to_blob(blob_path, content)
        return blob_path, local_path

    return local_path, local_path


def _get_blob_client():
    global _blob_service_client
    if _blob_service_client is None:
        from azure.storage.blob import BlobServiceClient
        settings = get_settings()
        _blob_service_client = BlobServiceClient.from_connection_string(
            settings.blob_storage_connection_string
        )
        try:
            _blob_service_client.create_container(settings.blob_container_name)
        except Exception:
            pass  # already exists
    return _blob_service_client


def _upload_to_blob(blob_path: str, content: bytes) -> None:
    settings = get_settings()
    client = _get_blob_client()
    blob_client = client.get_blob_client(container=settings.blob_container_name, blob=blob_path)
    blob_client.upload_blob(content, overwrite=True)


def delete_pdf(workspace_id: str, paper_id: str) -> None:
    """Removes the stored PDF (local copy + blob). Missing files are ignored."""
    settings = get_settings()
    local_path = os.path.join(settings.local_upload_dir, workspace_id, f"{paper_id}.pdf")
    if os.path.exists(local_path):
        os.remove(local_path)
    if settings.use_blob:
        _delete_blob(f"{workspace_id}/{paper_id}.pdf")


def delete_workspace_files(workspace_id: str) -> None:
    """Removes every stored PDF for a workspace (local folder + blobs)."""
    settings = get_settings()
    shutil.rmtree(os.path.join(settings.local_upload_dir, workspace_id), ignore_errors=True)
    if settings.use_blob:
        container = _get_blob_client().get_container_client(settings.blob_container_name)
        for blob in container.list_blobs(name_starts_with=f"{workspace_id}/"):
            _delete_blob(blob.name)


def _delete_blob(blob_path: str) -> None:
    from azure.core.exceptions import ResourceNotFoundError
    settings = get_settings()
    blob_client = _get_blob_client().get_blob_client(container=settings.blob_container_name, blob=blob_path)
    try:
        blob_client.delete_blob()
    except ResourceNotFoundError:
        pass
