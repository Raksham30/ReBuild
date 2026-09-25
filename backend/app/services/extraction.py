"""
Reduces a full paper (its sections) down to the fixed StructuredExtraction
schema. This is the step that makes comparisons/tables/lit-review possible
without re-reading raw chunks every time.

Runs on Azure OpenAI GPT-4o-mini using structured JSON output and converts
the result into the fixed StructuredExtraction Pydantic model.
"""
from __future__ import annotations
import json
from app.config import get_settings
from app.schemas import ParsedSection, StructuredExtraction
from app.services.generation import _get_azure_openai_client, run_azure_openai

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
    return _extract_azure_openai(sections)


def _extract_azure_openai(sections: list[ParsedSection]) -> StructuredExtraction:
    settings = get_settings()
    client = _get_azure_openai_client()

    # Keep cost down: cap total context sent to the model.
    joined = "\n\n".join(f"[{s.section_type.upper()}]\n{s.text[:3000]}" for s in sections)[:12000]

    def _call() -> StructuredExtraction:
        # Try beta parse (structured outputs) first
        try:
            completion = client.beta.chat.completions.parse(
                model=settings.azure_openai_chat_deployment,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": joined},
                ],
                response_format=StructuredExtraction,
                temperature=0,
            )
            if completion.choices and completion.choices[0].message:
                parsed = completion.choices[0].message.parsed
                if parsed is not None:
                    return parsed
                raw_text = completion.choices[0].message.content or "{}"
                return StructuredExtraction(**json.loads(raw_text))
        except Exception:
            # Fallback to standard json_object mode if beta parse is unsupported
            resp = client.chat.completions.create(
                model=settings.azure_openai_chat_deployment,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": joined},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            raw_text = resp.choices[0].message.content or "{}" if (resp.choices and resp.choices[0].message) else "{}"
            return StructuredExtraction(**json.loads(raw_text))

        return StructuredExtraction()

    return run_azure_openai(_call, label="Azure OpenAI Extraction")
