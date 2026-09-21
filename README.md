# Research Paper Assistant

A research workflow agent, not "chat with PDF": upload papers into a
workspace, get citation-grounded answers across your library, structured
per-paper extraction (datasets/methods/results/limitations), automatic
background contradiction/gap detection on every upload, and a research
writer that drafts using your own ideas while citing real uploaded papers.

End-user auth is Firebase (Google + email/password); everything else is
Azure: Cosmos DB (metadata), Blob Storage (files), Document Intelligence
(parsing), Azure AI Search (retrieval), and Azure AI Foundry Agent Service
(orchestration, itself authenticated via Entra ID -- that's a separate
concern from end-user login). Every Azure service, and Firebase, has a
local/offline fallback so you can develop and test for $0 -- see
`app/config.py`.

## Current status

Real Azure credentials are configured in `backend/.env` (Cosmos DB, Blob
Storage, Document Intelligence, AI Search, Azure OpenAI). Firebase Auth
(project "rebuilder-96244") is wired into the frontend; the backend's
`FIREBASE_SERVICE_ACCOUNT_PATH` still needs the service account JSON
before it verifies real tokens instead of dev-mode passthrough. Two more
things before it's fully live:

1. **Foundry project endpoint** -- `.env`'s `FOUNDRY_PROJECT_ENDPOINT` is
   still blank. Get it from the Foundry portal -> your project ->
   Overview -> "Project endpoint" (shape:
   `https://<account>.services.ai.azure.com/api/projects/<project>`).
   Until this is filled in, the app falls back to calling Azure OpenAI
   directly instead of through the Foundry Agent Service.
2. **`az login`** -- Foundry Agent Service auth is Entra ID only (no API
   key, and unrelated to the Firebase end-user login). Run `az login`
   once on whichever machine runs the backend.

Everything has been verified in offline-fallback mode (temporarily
blanking `.env` and running the full upload -> ask pipeline). The real
Azure paths (Cosmos, Blob, Document Intelligence, AI Search, Foundry)
have NOT been tested end-to-end yet, since they require live network
access this environment doesn't have -- that's the next step on your end.

## Quickstart

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

Check `curl http://127.0.0.1:8010/health` -- it reports which pipeline
stages are running on Azure vs. local fallback, so you can tell at a
glance what's actually wired up.

The real frontend is in `frontend/` (Vite + React) -- see
`frontend/README.md` for setup. The old `frontend/legacy-demo.html`
single-file page is kept only for reference; its API calls predate the
workspace/auth redesign and no longer match the backend.

## Auth in dev vs. real mode

Without `FIREBASE_SERVICE_ACCOUNT_PATH` set, any bearer token is treated
literally as the user id (`Authorization: Bearer alice` and
`Authorization: Bearer bob` simulate two different users) -- useful for
local testing, never safe otherwise. With a real Firebase service account
configured, tokens are verified via the Firebase Admin SDK against the
"rebuilder-96244" project. Note this is separate from `az login` above --
that's the Foundry Agent Service's own identity, not end-user auth.

## Project layout

```
backend/
  app/
    main.py, config.py, schemas.py, auth.py (Firebase token verification)
    services/
      parsing.py        Document Intelligence / pypdf fallback
      chunking.py         citation-taggable chunks
      embeddings.py         Azure OpenAI / offline HashingVectorizer
      indexing.py            Azure AI Search / local cosine index
      extraction.py            paper -> StructuredExtraction
      generation.py             routes through Foundry when configured
      foundry_agent.py           Foundry Agent Service (v2 SDK) integration
      agent.py                    the 4 features + background-flag helper
      storage.py                   Cosmos DB / local JSON fallback
      file_storage.py               Blob Storage / local disk fallback
    api/
      workspaces.py   create/list workspaces (the dashboard "history")
      papers.py         upload (triggers background contradiction+gap flags)
      chat.py             RAG ask, agentic when Foundry is configured
      research.py           gap-analysis, contradictions, write
frontend/
  src/          React app (Vite): Firebase auth, dashboard, workspace view
  legacy-demo.html   OLD single-file demo -- kept for reference only
docs/
  ARCHITECTURE.md
  AZURE_SETUP_COST_SAFE.md
```

## Next steps, in priority order

1. Fill in `FOUNDRY_PROJECT_ENDPOINT`, run `az login`, do a real end-to-end
   test against live Azure resources (upload a paper, ask a question).
2. Download the Firebase service account key and set
   `FIREBASE_SERVICE_ACCOUNT_PATH` so the backend verifies real tokens.
3. Add `GET /workspaces/{id}/flags` + mark-seen/dismiss endpoints -- the
   background jobs already write flags on upload, but nothing reads them
   back yet.
4. Add gap-analysis / contradiction / research-writer screens to the React
   app and a flags panel once (3) exists -- the backend routes are already
   there, just no UI yet.
5. Verify the Cosmos DB cross-partition query in `storage.get_workspace`
   performs acceptably once there's real data volume.
