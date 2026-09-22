import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../hooks/useAuth";
import InlineEdit from "../components/InlineEdit";

// Lightweight markdown renderer -- not a full parser, just the subset
// Gemini's responses actually use: ### / ## headers, **bold**, and
// paragraph breaks. Enough to stop raw "### **Title**" showing as
// literal characters, without pulling in a full markdown dependency.
function renderInlineBold(text, keyPrefix) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={`${keyPrefix}-${i}`}>{part.slice(2, -2)}</strong>
      : part
  );
}

function renderRich(text) {
  // Split into blocks line-by-line (not just on blank lines) so a heading
  // immediately followed by content on the next line -- with no blank
  // line between them, which is exactly what real Gemini output looks
  // like -- still gets detected as its own heading block.
  const lines = text.split("\n");
  const blocks = [];
  let paragraphLines = [];

  const flush = () => {
    if (paragraphLines.length) {
      blocks.push({ type: "p", text: paragraphLines.join("\n").trim() });
      paragraphLines = [];
    }
  };

  for (const line of lines) {
    const headingMatch = line.match(/^(#{1,3})\s+(.*)$/);
    if (headingMatch) {
      flush();
      blocks.push({ type: "h", level: headingMatch[1].length, text: headingMatch[2] });
    } else if (line.trim() === "") {
      flush();
    } else {
      paragraphLines.push(line);
    }
  }
  flush();

  return blocks.map((b, i) => {
    if (b.type === "h") {
      const content = renderInlineBold(b.text, `h${i}`);
      const Tag = b.level === 1 ? "h3" : b.level === 2 ? "h4" : "h5";
      return <Tag key={i} className="answer-heading">{content}</Tag>;
    }
    return <p key={i} className="answer-paragraph">{renderInlineBold(b.text, `p${i}`)}</p>;
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
  const [answer, setAnswer] = useState(null);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState(null);
  const [deletingWorkspace, setDeletingWorkspace] = useState(false);
  const [editingWorkspace, setEditingWorkspace] = useState(false);
  const [editingPaperId, setEditingPaperId] = useState(null);
  const [gapLoading, setGapLoading] = useState(false);
  const [gapResult, setGapResult] = useState(null);

  // Contradiction flags -- fetched in background, never blocks the UI
  const [flags, setFlags] = useState([]);
  const [flagsOpen, setFlagsOpen] = useState(false);

  // Review Builder state
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
    // Fire-and-forget: flags are background data, never block workspace load
    loadFlags();
  }

  // Fetch active (non-dismissed) flags in the background.
  // Errors are silently swallowed -- this is supplemental info, not critical.
  async function loadFlags() {
    try {
      const token = await getToken();
      const data = await api.listFlags(token, workspaceId, false);
      setFlags(data);
    } catch {
      // Intentionally silent -- flag fetch must never surface as an error
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

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
      setAnswer(null);
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
      navigate("/", { replace: true });
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
      // Remove flag from list immediately -- dismissed ones stay gone,
      // "seen" ones are now seen and stay until dismissed or page reload.
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
    if (!question.trim()) return;
    setAsking(true);
    setError("");
    setAnswer(null);
    try {
      const token = await getToken();
      const res = await api.ask(token, workspaceId, question.trim(), Array.from(selected));
      setAnswer(res);
    } catch (e) {
      setError(e.message);
    } finally {
      setAsking(false);
    }
  }

  // ---- Review Builder handlers ----

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
    <main className="page">
      <div className="page-header">
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
            {flags.length > 0 && (
              <button
                type="button"
                className="flags-badge"
                onClick={() => setFlagsOpen(true)}
                title="Click to view detected contradictions"
              >
                ⚠ {flags.length} possible contradiction{flags.length !== 1 ? "s" : ""} found
              </button>
            )}
          </h1>
        )}
        <p className="page-subtitle">Upload PDFs, then ask questions answered strictly from what's here.</p>
        <div className="header-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={handleResearchGap}
            disabled={gapLoading || papers.length === 0}
          >
            {gapLoading ? "Analyzing all papers…" : "Research Gap"}
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

      {gapResult && (
        <section className="panel gap-panel">
          <div className="gap-panel-head">
            <h2>Research gaps</h2>
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

      {flagsOpen && (
        <div className="flags-overlay" onClick={() => setFlagsOpen(false)}>
          <div className="flags-panel" onClick={(e) => e.stopPropagation()}>
            <div className="flags-panel-head">
              <h2>Possible contradictions ({flags.length})</h2>
              <button
                type="button"
                className="btn-link btn-link--muted"
                onClick={() => setFlagsOpen(false)}
              >
                Close
              </button>
            </div>
            <p className="muted flags-note">
              These were detected automatically in the background when papers were uploaded.
              Each entry shows the two conflicting claims side by side.
            </p>
            {flags.length === 0 ? (
              <p className="muted">No active flags — all have been dismissed.</p>
            ) : (
              <div className="flag-list">
                {flags.map((flag) => (
                  <div key={flag.flag_id} className="flag-entry">
                    <p className="flag-explanation">{flag.payload.explanation}</p>
                    <div className="flag-claims">
                      <div className="flag-claim">
                        <span className="flag-claim-source">{flag.payload.paper_a_title}</span>
                        <p className="flag-claim-text">"{flag.payload.claim_a}"</p>
                        {flag.payload.paper_a_citation && (
                          <span className="flag-claim-loc">
                            {flag.payload.paper_a_citation.section_type}, p.
                            {flag.payload.paper_a_citation.page_start}
                          </span>
                        )}
                      </div>
                      <div className="flag-claim flag-claim--b">
                        <span className="flag-claim-source">{flag.payload.paper_b_title}</span>
                        <p className="flag-claim-text">"{flag.payload.claim_b}"</p>
                        {flag.payload.paper_b_citation && (
                          <span className="flag-claim-loc">
                            {flag.payload.paper_b_citation.section_type}, p.
                            {flag.payload.paper_b_citation.page_start}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flag-actions">
                      <button
                        type="button"
                        className="btn-ghost"
                        onClick={() => handleFlagAction(flag.flag_id, "seen")}
                      >
                        Mark seen
                      </button>
                      <button
                        type="button"
                        className="btn-link-danger"
                        onClick={() => handleFlagAction(flag.flag_id, "dismissed")}
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      <section className="panel">
        <h2>Papers</h2>
        <label className="upload-control">
          <input type="file" accept="application/pdf" onChange={handleUpload} disabled={uploading} />
          <span>{uploading ? "Uploading and indexing…" : "Upload a PDF"}</span>
        </label>

        {papers.length === 0 ? (
          <p className="muted">No papers yet.</p>
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
                    <label>
                      <input
                        type="checkbox"
                        checked={selected.has(p.paper_id)}
                        onChange={() => toggleSelected(p.paper_id)}
                      />
                      <span className="paper-title">{p.title || p.filename}</span>
                    </label>
                    <span className="paper-actions">
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
                        {deletingId === p.paper_id ? "Removing…" : "Remove"}
                      </button>
                    </span>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <h2>Ask</h2>
        <form onSubmit={handleAsk} className="ask-form">
          <textarea
            rows={2}
            placeholder="What datasets do these papers use?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button className="btn-primary" type="submit" disabled={asking || papers.length === 0}>
            {asking ? "Thinking…" : "Ask"}
          </button>
        </form>

        {answer && (
          <div className="answer-block">
            <div className="answer-text">{renderRich(answer.answer)}</div>
            {answer.citations.length > 0 && (
              <div className="citations">
                {answer.citations.map((c, i) => (
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
      </section>

      {/* ---- Review Builder ---- */}
      <section className="panel">
        <h2>Review Builder</h2>
        <form onSubmit={handleGenerateReview} className="review-form">
          <label className="review-label">
            Idea / thesis
            <input
              type="text"
              placeholder="e.g. Transformer attention is over-parameterised for small datasets"
              value={reviewIdea}
              onChange={(e) => setReviewIdea(e.target.value)}
              required
            />
          </label>
          <label className="review-label">
            Your own research / findings
            <textarea
              rows={4}
              placeholder="Describe your original contributions, experiments, or observations…"
              value={reviewOwnResearch}
              onChange={(e) => setReviewOwnResearch(e.target.value)}
              required
            />
          </label>
          <label className="review-label">
            Formatting instructions <span className="muted">(optional)</span>
            <textarea
              rows={2}
              placeholder="e.g. Use IEEE format, keep it under 2 pages, formal tone…"
              value={reviewInstructions}
              onChange={(e) => setReviewInstructions(e.target.value)}
            />
          </label>
          <p className="muted review-scope-hint">
            Scoped to the {selected.size} paper{selected.size !== 1 ? "s" : ""} checked above.
          </p>
          <div className="review-actions">
            <button
              className="btn-primary"
              type="submit"
              disabled={reviewLoading || papers.length === 0 || !reviewIdea.trim() || !reviewOwnResearch.trim()}
            >
              {reviewLoading ? "Generating review…" : "Generate Review"}
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
            <p className="muted">This may take 30–60 seconds. Generating your draft from {selected.size} paper{selected.size !== 1 ? "s" : ""}…</p>
          </div>
        )}

        {reviewResult && (
          <div className="answer-block">
            <div className="answer-text">{renderRich(reviewResult.draft)}</div>
            {reviewResult.citations?.length > 0 && (
              <div className="citations">
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
      </section>

      {error && <p className="error-text">{error}</p>}
    </main>
  );
}
