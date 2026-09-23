import { useState } from "react";
import { useAuth } from "../hooks/useAuth";

export default function Login() {
  const { signInWithGoogle, signInWithEmail, signUpWithEmail } = useAuth();
  const [mode, setMode] = useState("signin"); // "signin" | "signup"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleGoogle() {
    setError("");
    setBusy(true);
    try {
      await signInWithGoogle();
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleEmailSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "signin") await signInWithEmail(email, password);
      else await signUpWithEmail(email, password);
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      {/* Ambient background styling */}
      <div className="login-ambient-grid" aria-hidden="true" />
      <div className="login-backdrop-decor" aria-hidden="true">
        <div className="login-decor-circle login-decor-circle--1" />
        <div className="login-decor-circle login-decor-circle--2" />
        <div className="login-decor-circle login-decor-circle--3" />
      </div>

      <div className="login-container">
        {/* Left Column: Rich Academic Editorial & Interactive Research Showcase */}
        <div className="login-brand-col">
          <div className="login-brand-header">
            <div className="login-brand-badge">
              <span className="login-brand-icon">📚</span>
              <span>Research Paper Assistant</span>
            </div>

            <h1 className="login-hero-title">
              Read across your research, <br />
              <span className="login-hero-em">not just one paper at a time.</span>
            </h1>

            <p className="login-hero-copy">
              Upload multi-paper libraries into structured workspaces and ask complex research questions.
              Every response is strictly synthesized with page-level citations and real-time contradiction alerts.
            </p>
          </div>

          {/* 3 Structured Feature Cards */}
          <div className="login-feature-grid">
            <div className="login-feature-card">
              <div className="feature-card-icon">💬</div>
              <div className="feature-card-content">
                <h4>Citation-Grounded Chat</h4>
                <p>Pinpoint page, section, and verbatim snippets for every answer.</p>
              </div>
            </div>

            <div className="login-feature-card">
              <div className="feature-card-icon">⚡</div>
              <div className="feature-card-content">
                <h4>Contradiction Detection</h4>
                <p>Automatically flags conflicting hypotheses across uploaded PDFs.</p>
              </div>
            </div>

            <div className="login-feature-card">
              <div className="feature-card-icon">📄</div>
              <div className="feature-card-content">
                <h4>Literature Review Generator</h4>
                <p>Synthesize structured review drafts grounded directly in your bibliography.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Polished Authentication Card */}
        <div className="login-card-wrapper">
          <div className="login-card">
            <div className="login-card-header">
              <h2>{mode === "signin" ? "Sign In to Workspace" : "Create Your Account"}</h2>
              <p className="login-card-sub">
                {mode === "signin"
                  ? "Welcome back. Enter your credentials to access your research libraries."
                  : "Start analyzing and synthesizing papers with citation-grounded AI."}
              </p>
            </div>

            <button
              type="button"
              className="btn-google"
              onClick={handleGoogle}
              disabled={busy}
            >
              <svg className="google-icon" width="18" height="18" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                />
              </svg>
              <span>Continue with Google</span>
            </button>

            <div className="login-divider">
              <span>or continue with email</span>
            </div>

            <form className="login-form" onSubmit={handleEmailSubmit}>
              <div className="form-group">
                <label className="form-label" htmlFor="login-email">Email address</label>
                <input
                  id="login-email"
                  type="email"
                  className="form-input"
                  placeholder="researcher@university.edu"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  disabled={busy}
                />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="login-password">Password</label>
                <input
                  id="login-password"
                  type="password"
                  className="form-input"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  minLength={6}
                  required
                  disabled={busy}
                />
              </div>

              <button className="btn-primary btn-login-submit" type="submit" disabled={busy}>
                {busy
                  ? "Please wait…"
                  : mode === "signin"
                  ? "Sign in to Workspace"
                  : "Create Account"}
              </button>
            </form>

            {error && <div className="login-error-box">{error}</div>}

            <div className="login-footer">
              <button
                type="button"
                className="login-toggle-mode"
                onClick={() => {
                  setMode((m) => (m === "signin" ? "signup" : "signin"));
                  setError("");
                }}
              >
                {mode === "signin" ? (
                  <>Need an account? <strong>Sign up</strong></>
                ) : (
                  <>Already have an account? <strong>Sign in</strong></>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function friendlyError(e) {
  const code = e?.code || "";
  if (code.includes("wrong-password") || code.includes("invalid-credential")) {
    return "Incorrect email or password.";
  }
  if (code.includes("email-already-in-use")) {
    return "That email is already registered — try signing in instead.";
  }
  if (code.includes("weak-password")) {
    return "Password should be at least 6 characters.";
  }
  if (code.includes("popup-closed-by-user")) {
    return "";
  }
  return e?.message || "Something went wrong signing in.";
}
