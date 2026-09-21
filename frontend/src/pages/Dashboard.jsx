import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../hooks/useAuth";

export default function Dashboard() {
  const { getToken } = useAuth();
  const navigate = useNavigate();

  const [workspaces, setWorkspaces] = useState(null);
  const [error, setError] = useState("");
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState(null);

  async function load() {
    try {
      const token = await getToken();
      setWorkspaces(await api.listWorkspaces(token));
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreate(e) {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setError("");
    try {
      const token = await getToken();
      const ws = await api.createWorkspace(token, newName.trim());
      setNewName("");
      navigate(`/workspace/${ws.workspace_id}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  }

  async function handleRename(ws) {
    const name = window.prompt("Rename workspace", ws.name);
    if (name === null || !name.trim() || name.trim() === ws.name) return;
    setError("");
    try {
      const token = await getToken();
      const updated = await api.renameWorkspace(token, ws.workspace_id, name.trim());
      setWorkspaces((prev) => prev.map((w) => (w.workspace_id === ws.workspace_id ? updated : w)));
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleDelete(ws) {
    if (!window.confirm(`Delete workspace "${ws.name}" and all its papers? This cannot be undone.`)) return;
    setDeletingId(ws.workspace_id);
    setError("");
    try {
      const token = await getToken();
      await api.deleteWorkspace(token, ws.workspace_id);
      setWorkspaces((prev) => prev.filter((w) => w.workspace_id !== ws.workspace_id));
    } catch (e) {
      setError(e.message);
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <main className="page">
      <div className="page-header">
        <h1>Your workspaces</h1>
        <p className="page-subtitle">
          Each workspace is its own library of papers, with its own citation-grounded chat.
        </p>
      </div>

      <form className="new-workspace" onSubmit={handleCreate}>
        <input
          type="text"
          placeholder="Workspace name, e.g. Long-context QA survey"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <button className="btn-primary" type="submit" disabled={creating}>
          {creating ? "Creating…" : "New workspace"}
        </button>
      </form>

      {error && <p className="error-text">{error}</p>}

      {workspaces === null && !error && <p className="muted">Loading workspaces…</p>}
      {workspaces && workspaces.length === 0 && (
        <p className="muted">No workspaces yet — create one above to upload your first papers.</p>
      )}

      <ul className="workspace-list">
        {workspaces?.map((ws) => (
          <li key={ws.workspace_id} className="workspace-item">
            <button className="workspace-row" onClick={() => navigate(`/workspace/${ws.workspace_id}`)}>
              <span className="workspace-name">{ws.name}</span>
              <span className="workspace-meta">updated {new Date(ws.updated_at).toLocaleDateString()}</span>
            </button>
            <button type="button" className="btn-link workspace-delete" onClick={() => handleRename(ws)}>
              Rename
            </button>
            <button
              type="button"
              className="btn-link-danger workspace-delete"
              onClick={() => handleDelete(ws)}
              disabled={deletingId === ws.workspace_id}
              aria-label={`Delete workspace ${ws.name}`}
            >
              {deletingId === ws.workspace_id ? "Deleting…" : "Delete"}
            </button>
          </li>
        ))}
      </ul>
    </main>
  );
}
