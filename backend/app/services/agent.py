"""
Agent tools -- the four workflow capabilities, not a single-shot chat reply:

  answer_question     -> RAG chat, grounded strictly in this workspace's papers
  find_research_gaps  -> looks across all papers for a genuine unexplored angle
  find_contradictions -> pairwise conflicting-claim detection with exact quotes
  write_research_draft-> drafts using the user's own idea, citing real papers

When Foundry Agent Service is configured (settings.use_foundry_agent),
answer_question runs as a genuine tool-using agent that decides for
itself how many times to search. The other three still do their
retrieval deterministically in Python (they need specific structured
fields, not open-ended search) but route their final synthesis step
through the Foundry agent via generation.generate().
"""
import json
from itertools import combinations
from app.config import get_settings
from app.schemas import Citation
from app.services import indexing, storage, generation


def _truncate_at_word_boundary(text: str, max_chars: int, search_window: int = 40) -> str:
    """Truncates to max_chars without cutting a word in half. Since chunks
    are already word-boundary-safe (chunking.py), this mainly matters for
    long chunks that exceed max_chars on their own."""
    if len(text) <= max_chars:
        return text
    cut = text.rfind(" ", max(0, max_chars - search_window), max_chars)
    if cut == -1:
        cut = max_chars
    return text[:cut].rstrip() + "..."


def _citation_from_chunk(workspace_id: str, chunk: dict) -> Citation:
    paper = storage.get_paper(workspace_id, chunk["paper_id"])
    return Citation(
        paper_id=chunk["paper_id"],
        paper_title=(paper.title or paper.filename) if paper else chunk["paper_id"],
        section_type=chunk["section_type"],
        page_start=chunk["page_start"],
        page_end=chunk["page_end"],
        snippet=_truncate_at_word_boundary(chunk["text"], 280),
    )


def answer_question(workspace_id: str, question: str, paper_ids: list[str] | None) -> tuple[str, list[Citation]]:
    settings = get_settings()
    if settings.use_foundry_agent:
        return _answer_question_agentic(workspace_id, question, paper_ids)
    return _answer_question_direct(workspace_id, question, paper_ids)


def _paper_label(workspace_id: str, paper_id: str, cache: dict) -> str:
    if paper_id not in cache:
        paper = storage.get_paper(workspace_id, paper_id)
        cache[paper_id] = (paper.title or paper.filename) if paper else paper_id
    return cache[paper_id]


def _answer_question_direct(workspace_id: str, question: str, paper_ids: list[str] | None) -> tuple[str, list[Citation]]:
    """Non-Foundry path: retrieve once, then generate."""
    multi = bool(paper_ids) and len(paper_ids) >= 2
    if multi:
        # Cross-paper questions ("what do these have in common?", "summarise each")
        # need evidence from EVERY selected paper, so retrieve per paper.
        per_paper = max(2, min(5, 12 // len(paper_ids)))
        broadened = f"{question}\nmain topic, objective, method and findings"
        chunks = indexing.search_chunks_by_paper(broadened, paper_ids, per_paper_k=per_paper)
    else:
        chunks = indexing.search_chunks(question, paper_ids, top_k=8)
    if not chunks:
        return "No relevant content found in the papers in this workspace.", []

    labels: dict[str, str] = {}
    context = "\n\n".join(
        f"[Source {i+1} | paper=\"{_paper_label(workspace_id, c['paper_id'], labels)}\" | "
        f"{c['section_type']} | p.{c['page_start']}-{c['page_end']}]\n{c['text']}"
        for i, c in enumerate(chunks)
    )

    overviews = ""
    if multi:
        exts = storage.get_extractions(workspace_id, paper_ids)
        lines = []
        for pid, ext in exts.items():
            lines.append(
                f"- \"{_paper_label(workspace_id, pid, labels)}\": "
                f"methods: {', '.join(ext.methods) or 'n/a'}; datasets: {', '.join(ext.datasets) or 'n/a'}; "
                f"key results: {'; '.join(ext.key_results[:3]) or 'n/a'}"
            )
        if lines:
            overviews = "Paper overviews:\n" + "\n".join(lines) + "\n\n"

    system = (
        "You answer questions using ONLY the provided paper excerpts (and paper "
        "overviews, if given). Never use outside/general knowledge. Cite sources "
        "inline like [Source N]. You MAY compare, contrast and summarise across "
        "papers: for questions about what papers have in common, state the "
        "overlap if there is one; if they share nothing substantial, say so and "
        "then give the short per-paper summary the user asked for. Only reply "
        "'The uploaded papers don't cover this.' when the excerpts contain "
        "nothing relevant to the question at all."
    )
    user = f"Question: {question}\n\n{overviews}Sources:\n{context}"
    answer = generation.generate(system, user, max_tokens=1200)
    citations = [_citation_from_chunk(workspace_id, c) for c in chunks]
    return answer, citations


def _answer_question_agentic(workspace_id: str, question: str, paper_ids: list[str] | None) -> tuple[str, list[Citation]]:
    """Foundry path: the agent decides when/how many times to search,
    rather than us pre-fetching a fixed top-k once."""
    from azure.ai.projects.models import FunctionTool
    from app.services import foundry_agent

    seen_chunks: dict[str, dict] = {}

    def search_papers_impl(query: str) -> str:
        chunks = indexing.search_chunks(query, paper_ids, top_k=5)
        for c in chunks:
            seen_chunks[c["chunk_id"]] = c
        return json.dumps([
            {"chunk_id": c["chunk_id"], "paper_id": c["paper_id"], "section": c["section_type"],
             "page_start": c["page_start"], "page_end": c["page_end"], "text": c["text"]}
            for c in chunks
        ])

    tool = FunctionTool(
        name="search_papers",
        description="Search the user's uploaded papers for relevant passages. "
                     "Call this as many times as needed with different queries.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "search query"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        strict=True,
    )

    input_text = (
        "Answer this question using ONLY the search_papers tool -- never use outside "
        "knowledge. Call the tool as many times as needed (different queries) to gather "
        "enough evidence, then cite chunk_ids inline like [chunk_id]. If nothing relevant "
        "is found after searching, say the uploaded papers don't cover this.\n\n"
        f"Question: {question}"
    )
    answer = foundry_agent.run_agent(input_text, tool_defs=[tool], tool_impls={"search_papers": search_papers_impl})
    citations = [_citation_from_chunk(workspace_id, c) for c in seen_chunks.values()]
    return answer, citations


def find_research_gaps(workspace_id: str, paper_ids: list[str], topic: str | None) -> dict:
    """Feature: research gap finder. Reads every indexed paper (extracted
    summary + its limitation / future-work passages) and lists ALL the gaps."""
    papers = []
    for pid in paper_ids:
        paper = storage.get_paper(workspace_id, pid)
        if paper and paper.status == "indexed":
            papers.append(paper)
    if not papers:
        return {
            "found_gap": False,
            "analysis": "There are no processed papers in this workspace yet. "
                        "Upload at least one PDF and wait until it shows 'indexed'.",
            "citations": [],
        }

    ids = [p.paper_id for p in papers]
    extractions = storage.get_extractions(workspace_id, ids)
    gap_query = f"{topic}: " if topic else ""
    gap_query += "limitations, future work, open problems, challenges not addressed, unresolved questions"
    chunks = indexing.search_chunks_by_paper(gap_query, ids, per_paper_k=3)

    blocks = []
    for n, paper in enumerate(papers, start=1):
        ext = extractions.get(paper.paper_id)
        label = paper.title or paper.filename
        lines = [f"### Paper {n}: {label}"]
        if ext:
            lines += [
                f"methods: {', '.join(ext.methods) or '(none extracted)'}",
                f"datasets: {', '.join(ext.datasets) or '(none extracted)'}",
                f"key results: {'; '.join(ext.key_results) or '(none extracted)'}",
                f"stated limitations: {'; '.join(ext.limitations) or '(none extracted)'}",
            ]
        for c in (c for c in chunks if c["paper_id"] == paper.paper_id):
            lines.append(f"excerpt ({c['section_type']}, p.{c['page_start']}): {_truncate_at_word_boundary(c['text'], 700)}")
        blocks.append("\n".join(lines))

    focus = f"Focus specifically on this topic: {topic}\n\n" if topic else ""
    system = (
        "You are a research assistant identifying RESEARCH GAPS across a set of "
        "papers. List ALL distinct, specific gaps you can support from the "
        "material given: problems, populations, datasets, methods or settings "
        "that none of the papers address, limitations they state but do not "
        "resolve, and places where the papers' approaches could be combined or "
        "compared but haven't been. Use only the provided material -- never "
        "invent findings. Refer to papers by their title, never by number.\n"
        "Format as a numbered list. For each gap write: a short bold title in "
        "**double asterisks**, then 'Why it's a gap:' (evidence from the papers), "
        "then 'Possible direction:' (one sentence). Finish with a one-line "
        "summary. If the papers genuinely support no clear gap, reply starting "
        "with 'No clear gap' and explain why. Plain text only, no tables or headers."
    )
    user = f"{focus}Papers in this workspace:\n\n" + "\n\n".join(blocks)
    analysis = generation.generate(system, user, max_tokens=2500)

    citations = [_citation_from_chunk(workspace_id, c) for c in chunks]
    found_gap = not analysis.strip().lower().startswith("no clear gap")
    return {"found_gap": found_gap, "analysis": analysis, "citations": citations}


def find_contradictions(workspace_id: str, paper_ids: list[str]) -> tuple[list[dict], int]:
    """Feature: contradiction detector. Requires 2+ papers."""
    extractions = storage.get_extractions(workspace_id, paper_ids)
    ids = list(extractions.keys())
    contradictions = []
    checked = 0

    for a, b in combinations(ids, 2):
        checked += 1
        ext_a, ext_b = extractions[a], extractions[b]
        shared_datasets = set(ext_a.datasets) & set(ext_b.datasets)
        if not shared_datasets and not (ext_a.key_results and ext_b.key_results):
            continue

        system = (
            "Two papers' extracted results are shown below. Decide if they "
            "report genuinely CONFLICTING findings (not just different topics) "
            "-- e.g. opposing claims about the same method/dataset/metric. "
            "If yes, reply EXACTLY as:\n"
            "CONTRADICTION: <one sentence explanation>\n"
            "QUOTE_A: <the exact line from Paper A's results that shows this>\n"
            "QUOTE_B: <the exact line from Paper B's results that shows this>\n"
            "If no genuine conflict, reply exactly: NONE"
        )
        user = (
            f"Paper A [{a}] results: {'; '.join(ext_a.key_results) or '(none)'}\n"
            f"Paper A limitations: {'; '.join(ext_a.limitations) or '(none)'}\n\n"
            f"Paper B [{b}] results: {'; '.join(ext_b.key_results) or '(none)'}\n"
            f"Paper B limitations: {'; '.join(ext_b.limitations) or '(none)'}"
        )
        result = generation.generate(system, user, max_tokens=300)
        if result.strip().upper().startswith("NONE"):
            continue

        explanation = quote_a = quote_b = ""
        for line in result.split("\n"):
            if line.startswith("CONTRADICTION:"):
                explanation = line.split(":", 1)[1].strip()
            elif line.startswith("QUOTE_A:"):
                quote_a = line.split(":", 1)[1].strip()
            elif line.startswith("QUOTE_B:"):
                quote_b = line.split(":", 1)[1].strip()
        if not (explanation and quote_a and quote_b):
            continue

        chunks_a = indexing.search_chunks(quote_a, [a], top_k=1)
        chunks_b = indexing.search_chunks(quote_b, [b], top_k=1)
        if not chunks_a or not chunks_b:
            continue

        paper_a = storage.get_paper(workspace_id, a)
        paper_b = storage.get_paper(workspace_id, b)
        contradictions.append({
            "paper_a_id": a,
            "paper_a_title": (paper_a.title or paper_a.filename) if paper_a else a,
            "claim_a": quote_a,
            "paper_a_citation": _citation_from_chunk(workspace_id, chunks_a[0]),
            "paper_b_id": b,
            "paper_b_title": (paper_b.title or paper_b.filename) if paper_b else b,
            "claim_b": quote_b,
            "paper_b_citation": _citation_from_chunk(workspace_id, chunks_b[0]),
            "explanation": explanation,
        })

    return contradictions, checked


def write_research_draft(workspace_id: str, idea: str, own_research: str,
                          instructions: str | None, paper_ids: list[str]) -> tuple[str, list[Citation]]:
    """Feature: research writer."""
    chunks = indexing.search_chunks(idea, paper_ids, top_k=10) if paper_ids else []
    context = "\n\n".join(
        f"[{c['paper_id']} | {c['section_type']} | p.{c['page_start']}-{c['page_end']}]\n{c['text']}"
        for c in chunks
    )
    instr = instructions.strip() if instructions else (
        "Use a standard academic structure. Moderate length. Neutral tone."
    )
    system = (
        "You help draft a research paper/section. The user's IDEA and OWN "
        "RESEARCH are their original contribution -- present them as such, "
        "never attribute them to an existing paper. When you reference "
        "EXISTING work, cite it using the bracketed paper_id from the "
        "provided excerpts, e.g. [abc123]. Never invent a citation or claim "
        "about a paper that isn't in the excerpts. Follow the user's "
        "formatting instructions."
    )
    user = (
        f"IDEA:\n{idea}\n\nOWN RESEARCH / FINDINGS:\n{own_research}\n\n"
        f"FORMATTING INSTRUCTIONS:\n{instr}\n\n"
        f"EXISTING WORK EXCERPTS (workspace papers):\n{context or '(none available)'}"
    )
    draft = generation.generate(system, user, max_tokens=1200)
    citations = [_citation_from_chunk(workspace_id, c) for c in chunks]
    return draft, citations


def find_new_contradiction_flags(workspace_id: str, new_paper_id: str, existing_paper_ids: list[str]) -> list[dict]:
    """Background-flag variant of find_contradictions: only checks the
    newly uploaded paper against each existing paper (not all pairs),
    so cost stays linear as the workspace grows."""
    extractions = storage.get_extractions(workspace_id, [new_paper_id] + existing_paper_ids)
    new_ext = extractions.get(new_paper_id)
    if not new_ext:
        return []

    flags = []
    for other_id in existing_paper_ids:
        other_ext = extractions.get(other_id)
        if not other_ext:
            continue
        shared_datasets = set(new_ext.datasets) & set(other_ext.datasets)
        if not shared_datasets and not (new_ext.key_results and other_ext.key_results):
            continue

        pairs, _ = find_contradictions(workspace_id, [new_paper_id, other_id])
        for c in pairs:
            flags.append({
                "type": "contradiction",
                "paper_ids_involved": [new_paper_id, other_id],
                "payload": c,
            })
    return flags
