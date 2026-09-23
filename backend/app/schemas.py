from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict


SectionType = Literal[
    "title", "abstract", "introduction", "related_work", "method",
    "experiments", "results", "discussion", "limitations",
    "conclusion", "references", "other"
]


class Chunk(BaseModel):
    chunk_id: str
    paper_id: str
    text: str
    section_type: SectionType
    page_start: int
    page_end: int
    order: int


class ParsedSection(BaseModel):
    section_type: SectionType
    text: str
    page_start: int
    page_end: int


class StructuredExtraction(BaseModel):
    """The fixed schema every paper gets reduced to. This is what powers
    comparisons, tables, and the literature review generator -- NOT raw
    chunk retrieval."""
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    key_results: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    summary: str = ""


class Workspace(BaseModel):
    workspace_id: str
    owner_uid: str
    name: str
    created_at: str
    updated_at: str


class RenameRequest(BaseModel):
    name: str


class Paper(BaseModel):
    paper_id: str
    workspace_id: str
    filename: str
    title: str = ""
    num_pages: int = 0
    status: Literal["uploaded", "parsing", "indexed", "failed"] = "uploaded"


class AskRequest(BaseModel):
    question: str
    paper_ids: list[str] | None = None  # None = search across whole library


class Citation(BaseModel):
    paper_id: str
    paper_title: str
    section_type: SectionType
    page_start: int
    page_end: int
    snippet: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]


class ChatMessage(BaseModel):
    message_id: str
    workspace_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str
    citations: list[Citation] = Field(default_factory=list)


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessage]


class CompareRequest(BaseModel):
    paper_ids: list[str]
    dimension: Literal["methods", "datasets", "key_results", "limitations"] = "methods"


class RelationshipEdge(BaseModel):
    source: str
    target: str
    relationship: Literal["extends", "contradicts", "uses_same_dataset", "similar_topic", "cites"]
    explanation: str


class LitReviewRequest(BaseModel):
    topic: str
    paper_ids: list[str]


# ---- Feature 2: Research gap finder ----

class GapAnalysisRequest(BaseModel):
    topic: str | None = None  # optional focus; None = analyze the whole workspace


class GapAnalysisResponse(BaseModel):
    found_gap: bool
    analysis: str
    citations: list[Citation]
    caveat: str = "Based only on the papers currently in this workspace."


# ---- Feature 3: Contradiction detector ----

class ContradictionPair(BaseModel):
    paper_a_id: str
    paper_a_title: str
    claim_a: str          # exact line from paper A
    paper_a_citation: Citation
    paper_b_id: str
    paper_b_title: str
    claim_b: str          # exact line from paper B
    paper_b_citation: Citation
    explanation: str


class ContradictionRequest(BaseModel):
    paper_ids: list[str] | None = None  # None = all papers in workspace


class ContradictionResponse(BaseModel):
    contradictions: list[ContradictionPair]
    checked_pairs: int


# ---- Flags (persisted background contradiction findings) ----

class FlagPayload(BaseModel):
    """The inner payload of a stored contradiction flag.
    Field names match exactly what agent.find_new_contradiction_flags builds."""
    paper_a_id: str
    paper_a_title: str
    claim_a: str                  # exact conflicting line from paper A
    paper_a_citation: Citation
    paper_b_id: str
    paper_b_title: str
    claim_b: str                  # exact conflicting line from paper B
    paper_b_citation: Citation
    explanation: str


class Flag(BaseModel):
    """Top-level flag record as stored by storage.save_flag."""
    flag_id: str
    workspace_id: str
    type: str                     # e.g. "contradiction"
    status: Literal["new", "seen", "dismissed"] = "new"
    created_at: str
    paper_ids_involved: List[str]
    payload: FlagPayload


class FlagStatusUpdate(BaseModel):
    status: Literal["new", "seen", "dismissed"]


class ContradictionStatus(BaseModel):
    status: Literal["not_started", "running", "completed", "failed"] = "not_started"
    last_checked_at: Optional[str] = None
    analyzed_paper_count: int = 0
    error: Optional[str] = None


# ---- Feature 4: Research writer ----

class ResearchWriteRequest(BaseModel):
    idea: str
    own_research: str
    instructions: str | None = None
    paper_ids: list[str] | None = None  # None = ground against whole workspace


class ResearchWriteResponse(BaseModel):
    draft: str
    citations: list[Citation]


class ResearchWritePdfRequest(BaseModel):
    idea: str | None = None
    own_research: str | None = None
    instructions: str | None = None
    paper_ids: list[str] | None = None
    draft: str | None = None

