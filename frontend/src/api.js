import { auth } from "./firebaseConfig";

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_API_BASE ||
  "http://127.0.0.1:8010";

async function request(
  path,
  token = null,
  { method = "GET", body, isForm = false } = {}
) {
  // If token wasn't provided, get it from the currently logged-in Firebase user
  if (!token) {
    const user = auth.currentUser;

    if (!user) {
      throw new Error("User is not logged in");
    }

    token = await user.getIdToken();
  }

  const headers = {
    Authorization: `Bearer ${token}`,
  };

  // Don't set Content-Type for FormData.
  // The browser automatically sets multipart/form-data with the boundary.
  if (!isForm) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: isForm
      ? body
      : body !== undefined
      ? JSON.stringify(body)
      : undefined,
  });

  if (!res.ok) {
    let detail = res.statusText;

    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      // Response wasn't JSON
    }

    throw new Error(`${res.status}: ${detail}`);
  }

  if (res.status === 204) {
    return null;
  }

  return res.json();
}

export const api = {
  // Health check doesn't require Firebase authentication
  health: () =>
    fetch(`${API_BASE}/health`).then((r) => {
      if (!r.ok) {
        throw new Error(`Health check failed: ${r.status}`);
      }
      return r.json();
    }),

  // Workspaces
  listWorkspaces: (token) =>
    request("/workspaces", token),

  createWorkspace: (token, name) =>
    request("/workspaces", token, {
      method: "POST",
      body: { name },
    }),

  getWorkspace: (token, id) =>
    request(`/workspaces/${id}`, token),

  renameWorkspace: (token, id, name) =>
    request(`/workspaces/${id}`, token, { method: "PATCH", body: { name } }),

  deleteWorkspace: (token, id) =>
    request(`/workspaces/${id}`, token, { method: "DELETE" }),

  // Papers
  listPapers: (token, wsId) =>
    request(`/workspaces/${wsId}/papers`, token),

  uploadPaper: (token, wsId, file) => {
    const form = new FormData();
    form.append("file", file);

    return request(`/workspaces/${wsId}/papers/upload`, token, {
      method: "POST",
      body: form,
      isForm: true,
    });
  },

  renamePaper: (token, wsId, paperId, name) =>
    request(`/workspaces/${wsId}/papers/${paperId}`, token, { method: "PATCH", body: { name } }),

  deletePaper: (token, wsId, paperId) =>
    request(`/workspaces/${wsId}/papers/${paperId}`, token, { method: "DELETE" }),

  // Contradiction flags (populated automatically in background after upload)
  listFlags: (token, wsId, includeDismissed = false) =>
    request(
      `/workspaces/${wsId}/flags${includeDismissed ? "?include_dismissed=true" : ""}`,
      token
    ),

  updateFlagStatus: (token, wsId, flagId, status) =>
    request(`/workspaces/${wsId}/flags/${flagId}`, token, {
      method: "PATCH",
      body: { status },
    }),

  getContradictionStatus: (token, wsId) =>
    request(`/workspaces/${wsId}/flags/status`, token),

  runContradictionAnalysis: (token, wsId) =>
    request(`/workspaces/${wsId}/flags/run`, token, { method: "POST" }),

  // Research gaps across every paper in the workspace
  gapAnalysis: (token, wsId) =>
    request(`/workspaces/${wsId}/research/gap-analysis`, token, {
      method: "POST",
      body: {},
    }),

  // Chat
  getChatHistory: (token, wsId) =>
    request(`/workspaces/${wsId}/chat/history`, token),

  deleteChatHistory: (token, wsId) =>
    request(`/workspaces/${wsId}/chat/history`, token, { method: "DELETE" }),

  ask: (token, wsId, question, paperIds) =>
    request(`/workspaces/${wsId}/chat/ask`, token, {
      method: "POST",
      body: {
        question,
        paper_ids:
          paperIds && paperIds.length
            ? paperIds
            : null,
      },
    }),

  // Research writer
  write: (token, wsId, { idea, own_research, instructions, paper_ids }) =>
    request(`/workspaces/${wsId}/research/write`, token, {
      method: "POST",
      body: { idea, own_research, instructions, paper_ids },
    }),

  writePdf: async (token, wsId, { idea, own_research, instructions, paper_ids, draft }) => {
    if (!token) {
      const user = auth.currentUser;
      if (!user) throw new Error("User is not logged in");
      token = await user.getIdToken();
    }
    const res = await fetch(
      `${API_BASE}/workspaces/${wsId}/research/write/pdf`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ idea, own_research, instructions, paper_ids, draft }),
      }
    );
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const data = await res.json();
        detail = data.detail || detail;
      } catch {
        // Response wasn't JSON
      }
      throw new Error(`${res.status}: ${detail}`);
    }
    return res.blob();
  },
};