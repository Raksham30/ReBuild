# Architecture

## Why this isn't "chat with PDF"

Most PDF-chat demos have one pipeline: chunk → embed → retrieve → answer.
That's fine for Q&A but breaks down for comparisons, tables, and synthesis,
because those tasks need consistent *fields*, not arbitrary retrieved text.

This project runs **two pipelines per paper**:

1. **Chunk index** (Azure AI Search / local vector fallback) — for open-ended
   semantic Q&A across the library.
2. **Structured extraction record** (stored per paper_id) — title, authors,
   datasets, methods, key_results, limitations, summary. This is what powers
   comparisons, the relationship graph, and the literature review generator,
   because those need the *same fields across every paper*, not a fresh
   free-text retrieval each time.

An agent/orchestration layer sits above both and exposes discrete workflow
tools rather than a single chat function:

- `answer_question` — retrieval + citation-grounded synthesis
- `compare_papers` — pulls one structured field across N papers into a table
- `build_relationship_graph` — pairwise embedding similarity + LLM-judged
  relationship classification (extends / contradicts / uses_same_dataset / similar_topic)
- `draft_lit_review` — per-paper summaries → thematic synthesis → cited draft

## Data flow

```
Upload PDF
  → parsing.py        (layout-aware section extraction: headings + page ranges)
  → chunking.py        (section-aware chunks, ~350-400 tokens, tagged with page/section)
  → indexing.py         (embed + push to vector index)
  → extraction.py        (LLM/heuristic reduction to StructuredExtraction schema)
  → storage.py             (persist paper metadata + structured record)

Query time:
  chat.ask           → indexing.search_chunks() → generation.generate() → cited answer
  workflows.compare  → storage.get_extractions() → generation.generate() → table + narrative
  workflows.graph    → embeddings + generation.generate() → relationship edges
  workflows.lit-review → storage + indexing + generation.generate() → cited draft
```

## Every citation is traceable

Every chunk carries `paper_id`, `section_type`, `page_start`, `page_end`.
Every API response that includes generated text also returns a `citations`
list built directly from the chunks used, not invented after the fact.
When you wire in Azure AI Document Intelligence, you additionally get
bounding-box coordinates, which is what lets a real frontend highlight the
exact region of the PDF a claim came from (documented as a TODO in
`parsing.py` — the `bounding_regions` data is already being read, just not
surfaced to the API yet).

## Swappable-by-design

Every Azure-dependent module (`parsing`, `embeddings`, `indexing`,
`extraction`, `generation`) checks `app/config.py`'s `use_*` flags and
transparently falls back to a local/offline implementation. This is not a
demo shortcut you rip out later — it's meant to stay, so you can always
develop and test new features for free before pointing them at billed
Azure resources.
