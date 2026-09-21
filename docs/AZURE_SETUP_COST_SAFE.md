# Azure Setup — Cost-Safe Guide for Student Credits

Turn services on **one at a time, in this order**, and test after each one.
Never enable a service you're not actively testing that day.

## Recommended tiers (fits comfortably in Azure for Students ~$100 credit)

| Service | Tier to pick | Why |
|---|---|---|
| Azure AI Document Intelligence | **Free (F0)** | 500 pages/month free. A project-sized paper set (10-30 papers) fits easily. |
| Azure AI Search | **Free (F0)** | 50MB storage, 3 indexes. Plenty for a few hundred chunks. No hourly cost — F0 is genuinely free, not a trial. |
| Azure OpenAI (via Azure AI Foundry) | **Pay-as-you-go, gpt-4o-mini + text-embedding-3-small** | No free tier, but these two models are extremely cheap per token. This is the only line item that scales with usage — see budget math below. |
| Blob Storage | **Standard LRS, or skip it** | Pennies/month. You can also just keep using local disk (already the default) until the very end. |
| Cosmos DB | **Skip for this project** | Free tier exists but SQLite already does the job for a resume project; don't spend setup time or credit headroom here. |
| Azure AI Foundry Agent Service (managed orchestration) | **Skip** | Bills separately for threads/runs on top of model tokens. The `app/services/agent.py` module in this repo already implements the same tool-calling pattern as plain Python functions calling Azure OpenAI directly — same resume story ("built an agentic workflow using models deployed via Azure AI Foundry"), zero extra platform cost. |

## Rough budget math

gpt-4o-mini is priced per million tokens (check current pricing — it changes).
For a project with ~20 papers:
- Structured extraction: 1 call per paper, ~3-4k input tokens each → ~20 calls total.
- Q&A / compare / lit-review during development and demo: budget ~200 calls.
- Embeddings: 1 call per chunk (~15-25 chunks/paper × 20 papers ≈ 400 calls), each tiny.

This is a few hundred thousand tokens total for the whole project lifecycle —
typically well under $1-2 even before considering the free tiers above.
The Document Intelligence and AI Search free tiers cost $0 regardless of usage
within their limits.

## Setup order

1. **Document Intelligence** — create resource, tier F0. Add endpoint+key to
   `.env`. Re-upload one test paper, confirm `/health` shows
   `"document_intelligence": "azure"` and check that sections now have real
   bounding boxes (inspect the `paragraphs` response if debugging).
2. **Azure AI Foundry → deploy models** — create an Azure OpenAI resource
   (this is what Foundry provisions under the hood), deploy `gpt-4o-mini`
   and `text-embedding-3-small`. Add endpoint+key+deployment names to `.env`.
   Test `/chat/ask` on one paper before doing anything else — this is the
   line item that costs money, so validate it in isolation first.
3. **Azure AI Search** — create resource, tier F0. Add endpoint+key to
   `.env`. Re-index your test papers, confirm `/health` shows
   `"search_index": "azure"`.
4. **(Optional) Blob Storage** — only if you want uploaded PDFs to survive
   redeploys/restarts. Local disk is fine for a demo.

## Guardrails while developing

- Keep `AZURE_OPENAI_*` blank while iterating on prompts for `compare_papers`,
  `build_relationship_graph`, and `draft_lit_review` — perfect the prompt
  logic against the offline fallback's structure first, then flip the flag
  on and do a final pass with a handful of real calls.
- Set a spending limit / budget alert in the Azure portal on the subscription
  the moment you create it, before adding any paid resource.
- Delete the Document Intelligence and AI Search resources between work
  sessions only if you're worried about hitting free-tier request quotas —
  they don't bill hourly, so there's no cost benefit to deleting them, only
  the OpenAI resource has usage-based cost.
