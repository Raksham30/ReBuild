# Frontend

Vite + React. Auth is Firebase (Google + email/password); everything else
(the workspace/paper/chat/research data) is served by the FastAPI backend,
which stays on Azure. Replaces the old `legacy-demo.html` (kept for
reference only — its API calls no longer match the backend, which is now
workspace-scoped and auth-gated).

## Setup

```bash
npm install
cp .env.example .env.local
```

`.env.example` is already filled in with the "rebuilder-96244" Firebase
project's public web config — that config isn't a secret, it's fine as-is.
Only change `VITE_API_BASE` if your backend isn't on `http://127.0.0.1:8010`.

In the [Firebase console](https://console.firebase.google.com) for that
project:
- **Authentication → Sign-in method** → enable **Google** and
  **Email/Password**.
- **Authentication → Settings → Authorized domains** → `localhost` is
  there by default; add your real domain once you deploy.

## Run

```bash
# backend, in another terminal
cd ../backend && uvicorn app.main:app --reload --port 8010

# frontend
npm run dev
```

Open `http://localhost:5173`. The backend only verifies real Firebase
tokens once `FIREBASE_SERVICE_ACCOUNT_PATH` is set in `backend/.env`
(Firebase console → Project settings → Service accounts → Generate new
private key) — until then it runs in dev-mode passthrough, which won't
reject a Firebase-issued token but also won't actually check it.

## What's built

- Sign in / sign up with Google or email+password (Firebase Auth)
- Dashboard: list your workspaces, create a new one
- Workspace view: upload PDFs, see indexing status, select which papers to
  scope a question to, ask and see the answer with citations
  (paper / section / page)

## Not yet built (next pass)

- Gap analysis, contradiction detector, and research-writer screens —
  the backend routes exist (`/workspaces/{id}/research/*`) but there's no
  UI for them yet
- Flags panel — blocked on the backend `GET /workspaces/{id}/flags`
  endpoint, which doesn't exist yet either
- Per-paper structured extraction view (`GET .../papers/{id}/extraction`)
- Password reset / forgot-password flow
