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
    <main className="page dashboard-page">
      <div className="dashboard-header">
        <div className="dashboard-header-text">
          <span className="eyebrow-tag">Research Dashboard</span>
          <h1>Your Workspaces</h1>
          <p className="dashboard-subtitle">
            Manage and organize your research projects and citation-grounded paper libraries.
          </p>
        </div>
      </div>

      <form className="dashboard-create-card" onSubmit={handleCreate}>
        <div className="create-input-wrapper">
          <span className="create-input-icon">📁</span>
          <input
            type="text"
            className="dashboard-create-input"
            placeholder="Workspace name, e.g. Long-context QA survey..."
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            disabled={creating}
          />
        </div>
        <button className="btn-primary btn-create-workspace" type="submit" disabled={creating || !newName.trim()}>
          {creating ? "Creating…" : "+ New Workspace"}
        </button>
      </form>

      {error && <p className="error-text dashboard-error">{error}</p>}

      {workspaces === null && !error && (
        <div className="dashboard-loading-state">
          <span className="spinner-icon">◌</span>
          <p>Loading workspaces…</p>
        </div>
      )}

      {workspaces && workspaces.length === 0 && (
        <div className="dashboard-empty-card">
          <div className="empty-icon-circle">📁</div>
          <h3>No workspaces yet</h3>
          <p>
            Create your first research workspace to organize papers, chat with your literature, and analyze contradictions.
          </p>
        </div>
      )}

      {workspaces && workspaces.length > 0 && (
        <div className="dashboard-list-container">
          <div className="dashboard-list-header">
            <span className="list-count-label">{workspaces.length} Workspace{workspaces.length !== 1 ? "s" : ""}</span>
          </div>
          <ul className="workspace-list">
            {workspaces.map((ws) => (
              <li key={ws.workspace_id} className="workspace-card-item">
                <div
                  className="workspace-card-clickable"
                  onClick={() => navigate(`/workspace/${ws.workspace_id}`)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      navigate(`/workspace/${ws.workspace_id}`);
                    }
                  }}
                >
                  <div className="workspace-card-left">
                    <div className="workspace-icon-box">📁</div>
                    <div className="workspace-info">
                      <span className="workspace-name">{ws.name}</span>
                      <span className="workspace-desc">Citation-grounded research workspace</span>
                    </div>
                  </div>

                  <div className="workspace-card-right">
                    <span className="workspace-meta">
                      Updated {new Date(ws.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                    </span>
                    <div className="workspace-actions" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        className="btn-link workspace-action-btn"
                        onClick={() => handleRename(ws)}
                      >
                        Rename
                      </button>
                      <button
                        type="button"
                        className="btn-link-danger workspace-action-btn"
                        onClick={() => handleDelete(ws)}
                        disabled={deletingId === ws.workspace_id}
                        aria-label={`Delete workspace ${ws.name}`}
                      >
                        {deletingId === ws.workspace_id ? "Deleting…" : "Delete"}
                      </button>
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </main>
  );
}
