"""
Tests for Review Paper Generation:
1. Mode A (Default format with empty instructions -> 17-section structure & Paper C / Paper D comparison)
2. Mode B (Custom format with instructions -> follows custom structure without 17 sections)
3. PDF Generation endpoint (/workspaces/{id}/research/write/pdf) with existing draft parameter (0 additional LLM calls)
4. PDF bytes validity & header layout
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from test_delete import client, _add_paper  # noqa: F401


def test_review_paper_mode_a_default(client, monkeypatch):
    from app.services import generation
    ws = client.post("/workspaces", json={"name": "Mode A Workspace"}).json()["workspace_id"]
    _add_paper(ws, "paper_c", text="Paper C studies transformer perplexity on WikiText-103", title="Paper C Title")
    _add_paper(ws, "paper_d", text="Paper D studies sparse attention efficiency on WikiText-103", title="Paper D Title")

    captured = {}
    def fake_generate(system, user, max_tokens=1200):
        captured["system"] = system
        captured["user"] = user
        return "# Title & Executive Summary\n\n## 1. Introduction & Background\nText...\n\n## 7. Paper C vs Paper D Comparative Synthesis\nComparison..."

    monkeypatch.setattr(generation, "generate", fake_generate)

    res = client.post(
        f"/workspaces/{ws}/research/write",
        json={
            "idea": "Hybrid sparse attention",
            "own_research": "We evaluate layer depth thresholds",
            "instructions": "",  # Empty -> Mode A
            "paper_ids": ["paper_c", "paper_d"]
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert "draft" in data
    assert "MODE A: DEFAULT 17-SECTION ACADEMIC REVIEW STRUCTURE" in captured["user"]
    assert "Paper C vs Paper D Comparative Synthesis" in captured["user"]
    assert "STRICT EVIDENCE GROUNDING RULES" in captured["system"]


def test_review_paper_mode_b_custom(client, monkeypatch):
    from app.services import generation
    ws = client.post("/workspaces", json={"name": "Mode B Workspace"}).json()["workspace_id"]
    _add_paper(ws, "p1", text="Paper 1 content", title="Paper 1")

    captured = {}
    def fake_generate(system, user, max_tokens=1200):
        captured["system"] = system
        captured["user"] = user
        return "# Introduction\n\n# Custom Methodology\n\n# Conclusion"

    monkeypatch.setattr(generation, "generate", fake_generate)

    custom_instructions = "Use custom structure: 1. Introduction, 2. Custom Methodology, 3. Conclusion."
    res = client.post(
        f"/workspaces/{ws}/research/write",
        json={
            "idea": "Custom idea",
            "own_research": "Custom research",
            "instructions": custom_instructions,
            "paper_ids": ["p1"]
        }
    )
    assert res.status_code == 200
    assert "MODE B: CUSTOM FORMATTING INSTRUCTIONS" in captured["user"]
    assert custom_instructions in captured["user"]
    # Verify default 17-section title is NOT present in custom mode prompt
    assert "MODE A: DEFAULT 17-SECTION ACADEMIC REVIEW STRUCTURE" not in captured["user"]
    assert "STRICT EVIDENCE GROUNDING RULES" in captured["system"]


def test_review_paper_pdf_generation_without_extra_llm_call(client, monkeypatch):
    from app.services import generation
    ws = client.post("/workspaces", json={"name": "PDF Workspace"}).json()["workspace_id"]
    _add_paper(ws, "p1", text="Paper 1 content", title="Paper 1")

    llm_called = False
    def fake_generate(system, user, max_tokens=1200):
        nonlocal llm_called
        llm_called = True
        return "Draft text"

    monkeypatch.setattr(generation, "generate", fake_generate)

    existing_draft = """# Literature Review: Hybrid Sparse Attention

## 1. Introduction
This review evaluates sparse attention performance on benchmark datasets.

| Model | Perplexity | Memory |
| --- | --- | --- |
| Dense | 18.2 | 100% |
| Sparse | 18.5 | 30% |

- High efficiency
- Low memory footprint
"""

    res = client.post(
        f"/workspaces/{ws}/research/write/pdf",
        json={
            "idea": "Hybrid Sparse Attention",
            "own_research": "Our findings",
            "instructions": None,
            "paper_ids": ["p1"],
            "draft": existing_draft  # Passing existing draft
        }
    )

    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert len(res.content) > 500
    assert res.content.startswith(b"%PDF")
    # Verify LLM generation function was NOT called when draft was supplied
    assert llm_called is False
