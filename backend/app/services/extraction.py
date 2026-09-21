"""
Reduces a full paper (its sections) down to the fixed StructuredExtraction
schema. This is the step that makes comparisons/tables/lit-review possible
without re-reading raw chunks every time.

Runs on Gemini exclusively, using response_schema for constrained JSON
output -- no Azure OpenAI fallback and no heuristic/offline fallback.
Azure's free/student subscription tier doesn't grant usable Azure OpenAI
quota for chat completions, so extraction gets the same treatment as
generation.py and embeddings.py: if GEMINI_API_KEY isn't set, this raises
immediately rather than silently degrading to weaker regex heuristics.
"""
import json
from app.config import get_settings
from app.schemas import ParsedSection, StructuredExtraction

EXTRACTION_SYSTEM_PROMPT = """You are a research-paper information extraction system.
Given the sections of an academic paper, extract ONLY information explicitly stated
in the text. Do not infer or hallucinate. Respond with strict JSON matching this schema:
{
  "title": string,
  "authors": [string],
  "datasets": [string],
  "methods": [string],
  "key_results": [string],
  "limitations": [string],
  "summary": string (3-5 sentences)
}
If a field cannot be found, return an empty list or empty string for it."""


def extract_structured_fields(paper_id: str, sections: list[ParsedSection]) -> StructuredExtraction:
    return _extract_gemini(sections)


def _extract_gemini(sections: list[ParsedSection]) -> StructuredExtraction:
    settings = get_settings()
    if not settings.use_gemini_embeddings:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Extraction runs on Gemini only "
            "(get a free key: https://aistudio.google.com/apikey) -- there is "
            "no Azure OpenAI fallback in this build."
        )

    from google import genai
    from google.genai import types
    from app.services.generation import run_gemini

    client = genai.Client(api_key=settings.gemini_api_key)
    # Keep cost down: cap total context sent to the model.
    joined = "\n\n".join(f"[{s.section_type.upper()}]\n{s.text[:3000]}" for s in sections)[:12000]

    def _call(model: str) -> StructuredExtraction:
        resp = client.models.generate_content(
            model=model,
            contents=joined,
            config=types.GenerateContentConfig(
                system_instruction=EXTRACTION_SYSTEM_PROMPT,
                temperature=0,
                response_mime_type="application/json",
                response_schema=StructuredExtraction,
            ),
        )
        if resp.parsed is not None:
            return resp.parsed
        return StructuredExtraction(**json.loads(resp.text))

    return run_gemini(_call, label="Gemini Extraction")
