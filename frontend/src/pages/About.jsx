import { useNavigate } from "react-router-dom";

export default function About() {
  const navigate = useNavigate();

  return (
    <main className="page about-page">
      {/* Header */}
      <div className="about-header">
        <span className="home-badge">Platform Architecture &amp; Capabilities</span>
        <h1>About Research Paper Assistant</h1>
        <p className="page-subtitle">
          An intelligent academic research workspace designed for literature synthesis, 
          structured extraction, verifiable citation grounding, and automated contradiction detection.
        </p>
      </div>

      {/* Feature Cards Grid */}
      <div className="about-cards-grid">
        {/* 1. Platform Overview */}
        <section className="panel about-card-compact">
          <div className="about-card-top">
            <div className="about-icon">🎯</div>
            <span className="about-tag">Core System</span>
          </div>
          <h2>Platform Overview</h2>
          <p>
            An intelligent research workspace that extracts structured methodologies, cross-references literature, 
            detects empirical conflicts, and drafts cited research reviews beyond basic single-PDF Q&amp;A.
          </p>
          <div className="about-pill-list">
            <span className="about-pill">Dual-Pipeline</span>
            <span className="about-pill">Grounded RAG</span>
            <span className="about-pill">Synthesis</span>
          </div>
        </section>

        {/* 2. Workspace Organization */}
        <section className="panel about-card-compact">
          <div className="about-card-top">
            <div className="about-icon">📂</div>
            <span className="about-tag">Library Management</span>
          </div>
          <h2>Workspace Organization</h2>
          <p>
            Research is structured into isolated project libraries. Upload collections of PDFs with status tracking, 
            scoped vector indexes, and granular paper selection controls.
          </p>
          <div className="about-pill-list">
            <span className="about-pill">Isolated Context</span>
            <span className="about-pill">Multi-PDF Ingestion</span>
            <span className="about-pill">Paper Scoping</span>
          </div>
        </section>

        {/* 3. Structured Extractions */}
        <section className="panel about-card-compact">
          <div className="about-card-top">
            <div className="about-icon">🔬</div>
            <span className="about-tag">Data Schemas</span>
          </div>
          <h2>Structured Extractions</h2>
          <p>
            Automated section parsing reduces every PDF into standardized records: 
            extracting <strong>datasets</strong>, <strong>methods</strong>, <strong>key results</strong>, and <strong>limitations</strong>.
          </p>
          <div className="about-pill-list">
            <span className="about-pill">Datasets &amp; Methods</span>
            <span className="about-pill">Key Results</span>
            <span className="about-pill">Limitations</span>
          </div>
        </section>

        {/* 4. Grounded Research Chat */}
        <section className="panel about-card-compact">
          <div className="about-card-top">
            <div className="about-icon">💬</div>
            <span className="about-tag">Citation Engine</span>
          </div>
          <h2>Citation-Grounded Chat</h2>
          <p>
            Query your library with strict ground-truth constraints. Answers rely exclusively on paper excerpts 
            and cite exact source papers, section types, and page numbers.
          </p>
          <div className="about-pill-list">
            <span className="about-pill">Zero Hallucinations</span>
            <span className="about-pill">Page Numbers</span>
            <span className="about-pill">Traceable Snippets</span>
          </div>
        </section>

        {/* 5. Contradiction Analysis */}
        <section className="panel about-card-compact">
          <div className="about-card-top">
            <div className="about-icon">⚖️</div>
            <span className="about-tag">Proactive Workers</span>
          </div>
          <h2>Contradiction Analysis</h2>
          <p>
            Automated background tasks cross-examine newly uploaded papers pairwise to surface conflicting 
            metrics, opposing claims, and mismatched findings side by side.
          </p>
          <div className="about-pill-list">
            <span className="about-pill">Background Scanner</span>
            <span className="about-pill">Pairwise Comparison</span>
            <span className="about-pill">Conflict Flags</span>
          </div>
        </section>

        {/* 6. Review Paper Generation */}
        <section className="panel about-card-compact">
          <div className="about-card-top">
            <div className="about-icon">✍️</div>
            <span className="about-tag">Synthesis &amp; Drafting</span>
          </div>
          <h2>Review Paper Generation</h2>
          <p>
            Identify unexplored research gaps across your collection and generate structured literature review drafts 
            synthesizing your original thesis with cited paper excerpts.
          </p>
          <div className="about-pill-list">
            <span className="about-pill">Gap Analysis</span>
            <span className="about-pill">Thesis Drafting</span>
            <span className="about-pill">PDF Export</span>
          </div>
        </section>
      </div>

      {/* Dual Pipeline Visual Showcase Box */}
      <section className="about-architecture-box">
        <div className="arch-box-header">
          <h3>Dual-Pipeline Processing Model</h3>
          <p>Why Research Paper Assistant outperforms conventional PDF chat tools:</p>
        </div>
        <div className="arch-box-grid">
          <div className="arch-item">
            <div className="arch-item-num">01</div>
            <div>
              <h4>Section-Aware Vector Chunks</h4>
              <p>Passages are indexed with section classifications (Abstract, Method, Results) and exact page boundaries for precision retrieval.</p>
            </div>
          </div>
          <div className="arch-item">
            <div className="arch-item-num">02</div>
            <div>
              <h4>Per-Paper Structured Schemas</h4>
              <p>Standardized metadata extractions stored per paper_id enable uniform comparative tables and automated contradiction checking.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer CTA */}
      <div className="about-footer">
        <button className="btn-primary btn-hero" onClick={() => navigate("/workspace")}>
          Launch Workspace Dashboard →
        </button>
      </div>
    </main>
  );
}
