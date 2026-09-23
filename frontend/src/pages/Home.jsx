import { useNavigate } from "react-router-dom";

export default function Home() {
  const navigate = useNavigate();

  return (
    <main className="page home-page">
      {/* Hero Section */}
      <section className="home-hero">
        <div className="home-badge">
          <span className="home-badge-dot"></span>
          Academic Research Intelligence Platform • 
        </div>

        <h1 className="home-title">Research Paper Assistant</h1>

        <p className="home-subtitle">
          Transform collections of PDF literature into structured, citation-grounded 
          intelligence with background contradiction analysis, research gap discovery, 
          and AI-assisted synthesis.
        </p>

        <div className="home-actions">
          <button className="btn-primary btn-hero" onClick={() => navigate("/workspace")}>
            Open Workspaces
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M6 12L10 8L6 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
          <button className="btn-ghost btn-hero" onClick={() => navigate("/about")}>
            System Architecture
          </button>
        </div>
      </section>

      {/* Highlights Bar */}
      <section className="home-stats-bar">
        <div className="stat-item">
          <span className="stat-val">Dual-Pipeline</span>
          <span className="stat-lbl">Vector Index + Structured Extractions</span>
        </div>
        <div className="stat-divider"></div>
        <div className="stat-item">
          <span className="stat-val">100% Traceable</span>
          <span className="stat-lbl">Section &amp; Page-Level Inline Citations</span>
        </div>
        <div className="stat-divider"></div>
        <div className="stat-item">
          <span className="stat-val">Proactive Analysis</span>
          <span className="stat-lbl">Automated Conflict &amp; Gap Detection</span>
        </div>
      </section>

      {/* Workflow Pillars */}
      <section className="home-section">
        <div className="section-head">
          <h2 className="section-title">Workflow Capabilities</h2>
          <p className="section-desc">Designed specifically for literature review, synthesis, and comparative analysis.</p>
        </div>

        <div className="home-features">
          <div className="feature-card">
            <div className="feature-card-header">
              <div className="feature-badge">01</div>
              <h3>Structured Paper Extraction</h3>
            </div>
            <p>
              Every uploaded PDF is parsed into a standardized record extracting 
              <strong> datasets</strong>, <strong>methods</strong>, <strong>key results</strong>, and <strong>limitations</strong>.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-card-header">
              <div className="feature-badge">02</div>
              <h3>Citation-Grounded RAG</h3>
            </div>
            <p>
              Perform deep semantic queries across your library. Responses strictly cite 
              verified passages tagged with exact section types and page numbers.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-card-header">
              <div className="feature-badge">03</div>
              <h3>Background Contradiction Finder</h3>
            </div>
            <p>
              Background workers automatically examine uploaded papers pairwise to flag 
              conflicting metrics, opposing claims, and mismatched findings.
            </p>
          </div>

          <div className="feature-card">
            <div className="feature-card-header">
              <div className="feature-badge">04</div>
              <h3>Gap Analysis &amp; Literature Review</h3>
            </div>
            <p>
              Uncover unaddressed research methodologies across your collection and generate 
              properly attributed literature review drafts.
            </p>
          </div>
        </div>
      </section>

      {/* How it Works Stepper */}
      <section className="home-section home-steps-section">
        <div className="section-head">
          <h2 className="section-title">How It Works</h2>
        </div>

        <div className="steps-grid">
          <div className="step-card">
            <span className="step-num">Step 1</span>
            <h4>Create Workspace</h4>
            <p>Group research papers into topic-specific libraries (e.g., Transformer Efficiency, Medical Imaging).</p>
          </div>

          <div className="step-card">
            <span className="step-num">Step 2</span>
            <h4>Upload Literature</h4>
            <p>PDFs are ingested through automated layout-aware parsing, vector indexing, and schema reduction.</p>
          </div>

          <div className="step-card">
            <span className="step-num">Step 3</span>
            <h4>Synthesize &amp; Write</h4>
            <p>Query your library, inspect detected contradiction flags, find gaps, and export cited paper reviews.</p>
          </div>
        </div>
      </section>

      {/* Bottom CTA Card */}
      <section className="home-cta-card">
        <h3>Ready to analyze your research library?</h3>
        <p>Create your first workspace to upload papers and run citation-grounded synthesis.</p>
        <button className="btn-primary" onClick={() => navigate("/workspace")}>
          Launch Workspace Dashboard →
        </button>
      </section>
    </main>
  );
}
