import { useEffect, useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../hooks/useAuth";
import InlineEdit from "../components/InlineEdit";

function renderInlineBold(text, keyPrefix) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={`${keyPrefix}-${i}`}>{part.slice(2, -2)}</strong>
      : part
  );
}

function renderRich(text) {
  if (!text) return null;
  const lines = text.split("\n");
  const blocks = [];
  let paragraphLines = [];
  let tableLines = [];

  const flushParagraph = () => {
    if (paragraphLines.length) {
      blocks.push({ type: "p", text: paragraphLines.join("\n").trim() });
      paragraphLines = [];
    }
  };

  const flushTable = () => {
    if (tableLines.length) {
      blocks.push({ type: "table", lines: [...tableLines] });
      tableLines = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
      flushParagraph();
      tableLines.push(trimmed);
      continue;
    } else if (tableLines.length > 0) {
      flushTable();
    }

    const headingMatch = line.match(/^(#{1,4})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph();
      blocks.push({ type: "h", level: headingMatch[1].length, text: headingMatch[2] });
    } else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      flushParagraph();
      blocks.push({ type: "bullet", text: trimmed.slice(2) });
    } else if (/^\d+\.\s/.test(trimmed)) {
      flushParagraph();
      blocks.push({ type: "numbered", text: trimmed });
    } else if (trimmed === "") {
      flushParagraph();
    } else {
      paragraphLines.push(line);
    }
  }
  flushParagraph();
  flushTable();

  return blocks.map((b, i) => {
    if (b.type === "h") {
      const content = renderInlineBold(b.text, `h${i}`);
      const Tag = b.level === 1 ? "h3" : b.level === 2 ? "h4" : "h5";
      return <Tag key={i} className="answer-heading">{content}</Tag>;
    }
    if (b.type === "bullet") {
      return (
        <li key={i} className="answer-bullet">
          {renderInlineBold(b.text, `b${i}`)}
        </li>
      );
    }
    if (b.type === "numbered") {
      return (
        <div key={i} className="answer-numbered">
          {renderInlineBold(b.text, `num${i}`)}
        </div>
      );
    }
    if (b.type === "table") {
      const rows = b.lines
        .filter((l) => !/^\|?[\s:\-]+\|[\s:\-\|]+$/.test(l.trim()))
        .map((l) => l.trim().slice(1, -1).split("|").map((c) => c.trim()));

      if (rows.length === 0) return null;
      const headerRow = rows[0];
      const dataRows = rows.slice(1);

      return (
        <div key={i} className="review-table-container">
          <table className="review-table">
            <thead>
              <tr>
                {headerRow.map((cell, cIdx) => (
                  <th key={cIdx}>{renderInlineBold(cell, `th${i}-${cIdx}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {dataRows.map((r, rIdx) => (
                <tr key={rIdx}>
                  {r.map((cell, cIdx) => (
                    <td key={cIdx}>{renderInlineBold(cell, `td${i}-${rIdx}-${cIdx}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    return (
      <p key={i} className="answer-paragraph">
        {renderInlineBold(b.text, `p${i}`)}
      </p>
    );
  });
}

export default function Workspace() {
  const { workspaceId } = useParams();
  const navigate = useNavigate();
  const { getToken } = useAuth();

  const [workspace, setWorkspace] = useState(null);
  const [papers, setPapers] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [uploading, setUploading] = useState(false);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatLoading, setChatLoading] = useState(true);
  const chatHistoryRef = useRef(null);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState(null);
  const [deletingWorkspace, setDeletingWorkspace] = useState(false);
  const [editingWorkspace, setEditingWorkspace] = useState(false);
  const [editingPaperId, setEditingPaperId] = useState(null);
  const [gapLoading, setGapLoading] = useState(false);
  const [gapResult, setGapResult] = useState(null);

  // Contradiction flags
  const [flags, setFlags] = useState([]);

  // Review Builder state
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewIdea, setReviewIdea] = useState("");
  const [reviewOwnResearch, setReviewOwnResearch] = useState("");
  const [reviewInstructions, setReviewInstructions] = useState("");
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewResult, setReviewResult] = useState(null);
  const [pdfDownloading, setPdfDownloading] = useState(false);

  async function loadAll() {
    try {
      const token = await getToken();
      const [ws, ps] = await Promise.all([
        api.getWorkspace(token, workspaceId),
        api.listPapers(token, workspaceId),
      ]);
      setWorkspace(ws);
      setPapers(ps);
      setSelected(new Set(ps.map((p) => p.paper_id)));
    } catch (e) {
      setError(e.message);
    }
    loadFlags();
  }

  async function loadChatHistory() {
    setChatLoading(true);
    try {
      const token = await getToken();
      const data = await api.getChatHistory(token, workspaceId);
      setChatMessages(data.messages || []);
    } catch (e) {
      console.error("Failed to load chat history:", e);
    } finally {
      setChatLoading(false);
    }
  }

  async function loadFlags() {
    try {
      const token = await getToken();
      const data = await api.listFlags(token, workspaceId, false);
      setFlags(data);
    } catch {
      // Intentionally silent
    }
  }

  useEffect(() => {
    loadAll();
    loadChatHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  useEffect(() => {
    if (chatHistoryRef.current) {
      chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
    }
  }, [chatMessages, asking, chatLoading]);

  async function handleUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const token = await getToken();
      await api.uploadPaper(token, workspaceId, file);
      await loadAll();
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function handleDeletePaper(paper) {
    if (!window.confirm(`Remove "${paper.title || paper.filename}" from this workspace? This cannot be undone.`)) return;
    setDeletingId(paper.paper_id);
    setError("");
    try {
      const token = await getToken();
      await api.deletePaper(token, workspaceId, paper.paper_id);
      setPapers((prev) => prev.filter((p) => p.paper_id !== paper.paper_id));
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(paper.paper_id);
        return next;
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setDeletingId(null);
    }
  }

  async function handleDeleteWorkspace() {
    if (!window.confirm(`Delete workspace "${workspace?.name || ""}" and all ${papers.length} of its papers? This cannot be undone.`)) return;
    setDeletingWorkspace(true);
    setError("");
    try {
      const token = await getToken();
      await api.deleteWorkspace(token, workspaceId);
      navigate("/workspace", { replace: true });
    } catch (e) {
      setError(e.message);
      setDeletingWorkspace(false);
    }
  }

  async function handleRenameWorkspace(name) {
    setError("");
    try {
      const token = await getToken();
      const ws = await api.renameWorkspace(token, workspaceId, name);
      setWorkspace(ws);
      setEditingWorkspace(false);
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleRenamePaper(paper, name) {
    setError("");
    try {
      const token = await getToken();
      const updated = await api.renamePaper(token, workspaceId, paper.paper_id, name);
      setPapers((prev) => prev.map((p) => (p.paper_id === paper.paper_id ? { ...p, title: updated.title } : p)));
      setEditingPaperId(null);
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleResearchGap() {
    setGapLoading(true);
    setError("");
    setGapResult(null);
    try {
      const token = await getToken();
      setGapResult(await api.gapAnalysis(token, workspaceId));
    } catch (e) {
      setError(e.message);
    } finally {
      setGapLoading(false);
    }
  }

  async function handleFlagAction(flagId, status) {
    try {
      const token = await getToken();
      await api.updateFlagStatus(token, workspaceId, flagId, status);
      setFlags((prev) => prev.filter((f) => f.flag_id !== flagId));
    } catch (e) {
      setError(e.message);
    }
  }

  function toggleSelected(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleAsk(e) {
    e.preventDefault();
    const q = question.trim();
    if (!q) return;

    setAsking(true);
    setError("");
    setQuestion("");

    const tempUserMsg = {
      message_id: `temp-${Date.now()}`,
      workspace_id: workspaceId,
      role: "user",
      content: q,
      created_at: new Date().toISOString()
    };
    setChatMessages((prev) => [...prev, tempUserMsg]);

    try {
      const token = await getToken();
      await api.ask(token, workspaceId, q, Array.from(selected));
      const updated = await api.getChatHistory(token, workspaceId);
      setChatMessages(updated.messages || []);
    } catch (e) {
      setError(e.message);
      try {
        const token = await getToken();
        const updated = await api.getChatHistory(token, workspaceId);
        setChatMessages(updated.messages || []);
      } catch {
        // Keep current state if re-fetch fails
      }
    } finally {
      setAsking(false);
    }
  }

  async function handleGenerateReview(e) {
    e.preventDefault();
    if (!reviewIdea.trim() || !reviewOwnResearch.trim()) return;
    setReviewLoading(true);
    setError("");
    setReviewResult(null);
    try {
      const token = await getToken();
      const res = await api.write(token, workspaceId, {
        idea: reviewIdea.trim(),
        own_research: reviewOwnResearch.trim(),
        instructions: reviewInstructions.trim() || null,
        paper_ids: Array.from(selected),
      });
      setReviewResult(res);
    } catch (e) {
      setError(e.message);
    } finally {
      setReviewLoading(false);
    }
  }

  async function handleDownloadPdf() {
    setPdfDownloading(true);
    setError("");
    try {
      const token = await getToken();
      const blob = await api.writePdf(token, workspaceId, {
        idea: reviewIdea.trim(),
        own_research: reviewOwnResearch.trim(),
        instructions: reviewInstructions.trim() || null,
        paper_ids: Array.from(selected),
        draft: reviewResult?.draft || null,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "review_draft.pdf";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e.message);
    } finally {
      setPdfDownloading(false);
    }
  }


  return (
    <main className="page workspace-page">
      {/* Redesigned Dashboard Hero Header */}
      <div className="workspace-hero-header">
        <div className="workspace-hero-left">
          <span className="eyebrow-tag">YOUR WORKSPACE</span>
          <div className="workspace-title-row">
            {editingWorkspace ? (
              <InlineEdit
                initialValue={workspace?.name || ""}
                maxLength={120}
                label="Workspace name"
                onSave={handleRenameWorkspace}
                onCancel={() => setEditingWorkspace(false)}
              />
            ) : (
              <h1>
                {workspace?.name || "Workspace"}
                {workspace && (
                  <button type="button" className="btn-link rename-link" onClick={() => setEditingWorkspace(true)}>
                    Rename
                  </button>
                )}
              </h1>
            )}
          </div>
          <p className="page-subtitle">Citation-grounded research workspace &amp; comparative analysis.</p>
        </div>

        <div className="workspace-hero-right">
          <button
            type="button"
            className="btn-primary"
            onClick={handleResearchGap}
            disabled={gapLoading || papers.length === 0}
          >
            {gapLoading ? "Analyzing papers…" : "Research Gap Analysis"}
          </button>
          <button
            type="button"
            className="btn-danger"
            onClick={handleDeleteWorkspace}
            disabled={deletingWorkspace || !workspace}
          >
            {deletingWorkspace ? "Deleting…" : "Delete workspace"}
          </button>
        </div>
      </div>

      {error && <p className="error-text">{error}</p>}

      {/* Research Gap Analysis Results Panel */}
      {gapResult && (
        <section className="panel gap-panel">
          <div className="gap-panel-head">
            <h2>Research Gaps Analysis</h2>
            <button type="button" className="btn-link btn-link--muted" onClick={() => setGapResult(null)}>
              Close
            </button>
          </div>
          <div className="answer-text gap-text">{renderRich(gapResult.analysis)}</div>
          <p className="muted">{gapResult.caveat}</p>
          {gapResult.citations?.length > 0 && (
            <div className="citations">
              {gapResult.citations.map((c, i) => (
                <div key={i} className="citation-card">
                  <span className="citation-source">
                    {c.paper_title} — {c.section_type}, p.{c.page_start}
                    {c.page_end !== c.page_start ? `–${c.page_end}` : ""}
                  </span>
                  <p className="citation-snippet">{c.snippet}</p>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* 3-Column Equal Grid Layout */}
      <div className="workspace-grid">
        {/* CARD 1: Research Papers */}
        <section className="panel workspace-card">
          <div className="card-header">
            <div className="card-header-left">
              <div className="card-icon-container">📄</div>
              <h2>Research Papers</h2>
            </div>
            <span className="count-badge">{papers.length}</span>
          </div>

          <p className="card-desc">Manage and index your PDF reference library.</p>

          {/* Prominent Upload Zone */}
          <label className="upload-dropzone">
            <input type="file" accept="application/pdf" onChange={handleUpload} disabled={uploading} />
            <div className="dropzone-content">
              <div className="dropzone-icon">📁</div>
              <span className="dropzone-title">
                {uploading ? "Indexing PDF..." : "Upload PDF Papers"}
              </span>
              <span className="dropzone-sub">
                {uploading ? "Extracting sections & vector chunks" : "Drag & drop files here or click to browse"}
              </span>
            </div>
          </label>

          {papers.length === 0 ? (
            <p className="muted empty-hint">No papers uploaded yet.</p>
          ) : (
            <ul className="paper-list">
              {papers.map((p) => (
                <li key={p.paper_id} className="paper-row">
                  {editingPaperId === p.paper_id ? (
                    <InlineEdit
                      initialValue={p.title || p.filename}
                      maxLength={300}
                      label="Paper name"
                      onSave={(name) => handleRenamePaper(p, name)}
                      onCancel={() => setEditingPaperId(null)}
                    />
                  ) : (
                    <>
                      <label className="paper-select-label">
                        <input
                          type="checkbox"
                          checked={selected.has(p.paper_id)}
                          onChange={() => toggleSelected(p.paper_id)}
                        />
                        <span className="paper-title">{p.title || p.filename}</span>
                      </label>
                      <div className="paper-row-actions">
                        <span className={`paper-status paper-status--${p.status}`}>{p.status}</span>
                        <button type="button" className="btn-link" onClick={() => setEditingPaperId(p.paper_id)}>
                          Rename
                        </button>
                        <button
                          type="button"
                          className="btn-link-danger"
                          onClick={() => handleDeletePaper(p)}
                          disabled={deletingId === p.paper_id}
                        >
                          {deletingId === p.paper_id ? "..." : "Remove"}
                        </button>
                      </div>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* CARD 2: Ask & Research Chat */}
        <section className="panel workspace-card">
          <div className="card-header">
            <div className="card-header-left">
              <div className="card-icon-container">💬</div>
              <h2>Ask &amp; Research Chat</h2>
            </div>
            <span className="scope-hint">{selected.size} of {papers.length} scoped</span>
          </div>

          <p className="card-desc">Ask questions grounded strictly in your selected papers.</p>

          <div className="chat-history-container" ref={chatHistoryRef}>
            {chatLoading ? (
              <div className="chat-loading-state">Loading conversation...</div>
            ) : chatMessages.length === 0 ? (
              <div className="chat-empty-state">
                <p>No conversation history yet.</p>
                <span className="muted">Ask a question below to start research chat.</span>
              </div>
            ) : (
              chatMessages.map((msg, i) => (
                <div key={msg.message_id || i} className={`chat-bubble-card chat-bubble-${msg.role}`}>
                  <div className="chat-bubble-header">
                    <span className="chat-bubble-role">
                      {msg.role === "user" ? "USER" : "RESEARCH ASSISTANT"}
                    </span>
                    {msg.created_at && (
                      <span className="chat-bubble-time">
                        {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    )}
                  </div>
                  <div className="chat-bubble-body">
                    {msg.role === "user" ? (
                      <p className="chat-user-text">{msg.content}</p>
                    ) : (
                      renderRich(msg.content)
                    )}
                  </div>
                  {msg.role === "assistant" && msg.citations && msg.citations.length > 0 && (
                    <div className="citations">
                      <h4>Sources &amp; Citations</h4>
                      {msg.citations.map((c, cIdx) => (
                        <div key={cIdx} className="citation-card">
                          <span className="citation-source">
                            {c.paper_title} — {c.section_type}, p.{c.page_start}
                            {c.page_end !== c.page_start ? `–${c.page_end}` : ""}
                          </span>
                          <p className="citation-snippet">{c.snippet}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
            {asking && (
              <div className="chat-bubble-card chat-bubble-assistant chat-bubble-loading">
                <div className="chat-bubble-header">
                  <span className="chat-bubble-role">RESEARCH ASSISTANT</span>
                </div>
                <div className="chat-bubble-body">
                  <p className="muted">Synthesizing answer from papers...</p>
                </div>
              </div>
            )}
          </div>

          <form onSubmit={handleAsk} className="ask-form">
            <div className="chat-input-container">
              <textarea
                rows={2}
                placeholder="Ask a question across your selected paper library (e.g. What datasets do these papers use?)"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleAsk(e);
                  }
                }}
              />
              <div className="chat-input-actions">
                <span className="chat-hint">Press Enter to ask, Shift+Enter for new line</span>
                <button
                  className="btn-primary btn-chat-send"
                  type="submit"
                  disabled={asking || papers.length === 0 || !question.trim()}
                >
                  {asking ? "Synthesizing…" : "Ask Question ↵"}
                </button>
              </div>
            </div>
          </form>
        </section>

        {/* CARD 3: Contradictions */}
        <section className="panel workspace-card">
          <div className="card-header">
            <div className="card-header-left">
              <div className="card-icon-container">⚖️</div>
              <h2>Contradictions</h2>
            </div>
            {flags.length > 0 && <span className="flag-count-badge">⚠ {flags.length}</span>}
          </div>

          <p className="card-desc">Background detection of conflicting claims between papers.</p>

          {flags.length === 0 ? (
            <div className="empty-contradictions-panel">
              <div className="empty-icon-circle">⚖️</div>
              <h3>No contradictions found</h3>
              <p>No active contradiction flags detected in this workspace.</p>
            </div>
          ) : (
            <div className="flag-list-inline">
              {flags.map((flag) => (
                <div key={flag.flag_id} className="flag-card-inline">
                  <p className="flag-explanation">{flag.payload.explanation}</p>
                  
                  <div className="flag-claim-box">
                    <span className="claim-source-tag">{flag.payload.paper_a_title}</span>
                    <p className="claim-text">"{flag.payload.claim_a}"</p>
                    {flag.payload.paper_a_citation && (
                      <span className="claim-loc">
                        {flag.payload.paper_a_citation.section_type}, p.{flag.payload.paper_a_citation.page_start}
                      </span>
                    )}
                  </div>

                  <div className="flag-claim-box flag-claim-box--b">
                    <span className="claim-source-tag claim-source-tag--b">{flag.payload.paper_b_title}</span>
                    <p className="claim-text">"{flag.payload.claim_b}"</p>
                    {flag.payload.paper_b_citation && (
                      <span className="claim-loc">
                        {flag.payload.paper_b_citation.section_type}, p.{flag.payload.paper_b_citation.page_start}
                      </span>
                    )}
                  </div>

                  <div className="flag-actions-row">
                    <button
                      type="button"
                      className="btn-ghost btn-sm"
                      onClick={() => handleFlagAction(flag.flag_id, "seen")}
                    >
                      Mark seen
                    </button>
                    <button
                      type="button"
                      className="btn-link-danger btn-sm"
                      onClick={() => handleFlagAction(flag.flag_id, "dismissed")}
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {/* Full-Width Literature Review Paper Generator Banner Below Cards */}
      <section className="review-cta-banner">
        <div className="review-banner-header">
          <div className="review-banner-left">
            <div className="review-icon-container">📝</div>
            <div>
              <h2>Literature Review Paper Generator</h2>
              <p>Synthesize your original thesis idea and research findings with cited literature.</p>
            </div>
          </div>

          <button
            type="button"
            className="btn-primary btn-review-cta"
            onClick={() => setReviewOpen((prev) => !prev)}
          >
            {reviewOpen ? "Hide Review Builder" : "Write Review Paper →"}
          </button>
        </div>

        {reviewOpen && (
          <div className="panel review-drawer-panel">
            <form onSubmit={handleGenerateReview} className="review-form">
              <label className="review-label">
                Idea / Thesis statement
                <input
                  type="text"
                  placeholder="e.g. Transformer attention is over-parameterised for small dataset regimes"
                  value={reviewIdea}
                  onChange={(e) => setReviewIdea(e.target.value)}
                  required
                />
              </label>
              <label className="review-label">
                Your own research / findings
                <textarea
                  rows={3}
                  placeholder="Describe your original contributions, experiments, or methodology observations…"
                  value={reviewOwnResearch}
                  onChange={(e) => setReviewOwnResearch(e.target.value)}
                  required
                />
              </label>
              <label className="review-label">
                Formatting instructions <span className="muted">(optional)</span>
                <textarea
                  rows={2}
                  placeholder="e.g. Use IEEE format, formal academic tone, under 3 pages…"
                  value={reviewInstructions}
                  onChange={(e) => setReviewInstructions(e.target.value)}
                />
              </label>

              <div className="review-actions">
                <button
                  className="btn-primary"
                  type="submit"
                  disabled={reviewLoading || papers.length === 0 || !reviewIdea.trim() || !reviewOwnResearch.trim()}
                >
                  {reviewLoading ? "Generating cited review draft…" : "Generate Review"}
                </button>
                {reviewResult && (
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={handleDownloadPdf}
                    disabled={pdfDownloading}
                  >
                    {pdfDownloading ? "Preparing PDF…" : "Download as PDF"}
                  </button>
                )}
              </div>
            </form>

            {reviewLoading && (
              <div className="review-loading">
                <p className="muted">Generating your review draft grounded in {selected.size} selected paper{selected.size !== 1 ? "s" : ""}…</p>
              </div>
            )}

            {reviewResult && (
              <div className="answer-block">
                <h3>Drafted Literature Review</h3>
                <div className="answer-text">{renderRich(reviewResult.draft)}</div>
                {reviewResult.citations?.length > 0 && (
                  <div className="citations">
                    <h4>Citations</h4>
                    {reviewResult.citations.map((c, i) => (
                      <div key={i} className="citation-card">
                        <span className="citation-source">
                          {c.paper_title} — {c.section_type}, p.{c.page_start}
                          {c.page_end !== c.page_start ? `–${c.page_end}` : ""}
                        </span>
                        <p className="citation-snippet">{c.snippet}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
