"""
Thin wrapper for "generate text from a prompt" used by the agent's
synthesis steps (answering, comparison narrative, lit review paragraphs).

Foundry Agent Service (if FOUNDRY_PROJECT_ENDPOINT is set) is checked
first -- it's a genuinely different orchestration mechanism (a managed
tool-calling runtime), not just another model provider, so it stays as
its own path. Otherwise, generation runs on Gemini exclusively: Azure's
free/student subscription tier doesn't grant usable Azure OpenAI quota
for chat completions any more than it does for embeddings, so there is
no Azure OpenAI fallback and no offline/extractive fallback here -- if
GEMINI_API_KEY isn't set, this raises immediately rather than silently
degrading.

Quota handling (shared with extraction.py via run_gemini):
  * per-minute 429  -> wait the delay Google asks for (short waits only)
  * per-DAY 429     -> retrying is pointless, move straight to the next
                       model in GEMINI_CHAT_FALLBACK_MODELS (each model
                       has its own free-tier bucket)
  * everything exhausted -> LLMUnavailableError, which main.py turns into
                       a clean 429/503 instead of a 500 traceback.
"""
from __future__ import annotations
import re
import time
from typing import Callable, TypeVar

from app.config import get_settings

T = TypeVar("T")

GEMINI_CHAT_MAX_RETRIES = 3       # attempts per model for transient errors
GEMINI_CHAT_BASE_BACKOFF = 2.0
GEMINI_MAX_WAIT_SECONDS = 20.0    # never block a request longer than this per wait


class LLMUnavailableError(RuntimeError):
    """Every configured Gemini model is rate-limited or overloaded."""

    def __init__(self, message: str, status_code: int = 429):
        super().__init__(message)
        self.status_code = status_code


def generate(system_prompt: str, user_prompt: str, max_tokens: int = 600) -> str:
    settings = get_settings()
    if settings.use_foundry_agent:
        from app.services import foundry_agent
        combined = f"{system_prompt}\n\n{user_prompt}"
        return foundry_agent.run_agent(combined, tool_defs=[], tool_impls={}, max_tokens=max_tokens)
    return _generate_gemini(system_prompt, user_prompt, max_tokens)


def _is_daily_quota(err: Exception) -> bool:
    # Google names the violated quota, e.g. "...PerDayPerProjectPerModel-FreeTier".
    return "PerDay" in str(err)


def _suggested_delay(err: Exception) -> float | None:
    """Seconds Google asks us to wait ('retryDelay': '37s' / 'retry in 37.6s')."""
    m = re.search(r"retryDelay'?\"?:\s*'?\"?([\d.]+)s", str(err)) or \
        re.search(r"retry in ([\d.]+)s", str(err))
    return float(m.group(1)) if m else None


def run_gemini(call: Callable[[str], T], label: str = "Gemini") -> T:
    """Runs call(model_name) with retry + model fallback. `call` must build
    and send one generate_content request for the given model."""
    from google.genai.errors import ClientError, ServerError

    settings = get_settings()
    last_err: Exception | None = None

    for model in settings.gemini_chat_models:
        for attempt in range(1, GEMINI_CHAT_MAX_RETRIES + 1):
            try:
                return call(model)
            except (ClientError, ServerError) as e:
                code = getattr(e, "code", None)
                if code == 404:
                    # Fallback model name doesn't exist (renamed/retired) -- skip it.
                    print(f"[{label}] Model '{model}' not found; trying next model.")
                    last_err = e
                    break
                if code not in (429, 503):
                    raise  # bad request / bad key / etc. -- a real error
                last_err = e

                if code == 429 and _is_daily_quota(e):
                    print(f"[{label}] Daily quota exhausted for '{model}'; trying next model.")
                    break

                suggested = _suggested_delay(e) if code == 429 else None
                if suggested is not None and suggested > GEMINI_MAX_WAIT_SECONDS:
                    print(f"[{label}] '{model}' asks for a {suggested:.0f}s wait; trying next model.")
                    break
                if attempt == GEMINI_CHAT_MAX_RETRIES:
                    break

                wait = suggested if suggested is not None else GEMINI_CHAT_BASE_BACKOFF * (2 ** (attempt - 1))
                wait = min(wait + 0.5, GEMINI_MAX_WAIT_SECONDS)
                reason = "Rate limit" if code == 429 else "Model overloaded (503)"
                print(f"[{label}] {reason} on '{model}' (attempt {attempt}/{GEMINI_CHAT_MAX_RETRIES}). "
                      f"Retrying in {wait:.1f}s...")
                time.sleep(wait)

    code = getattr(last_err, "code", None)
    if code == 503:
        raise LLMUnavailableError(
            "The AI model is temporarily overloaded. Please try again in a minute.", 503
        ) from last_err
    raise LLMUnavailableError(
        "Gemini API quota exhausted for all configured models (free tier is limited per "
        "day). Try again later, enable billing on the Google AI Studio project, or add "
        "another model to GEMINI_CHAT_FALLBACK_MODELS.", 429
    ) from last_err


def _generate_gemini(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    settings = get_settings()
    if not settings.use_gemini_embeddings:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Chat generation runs on Gemini only "
            "(get a free key: https://aistudio.google.com/apikey) -- there is "
            "no Azure OpenAI fallback in this build."
        )

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)

    def _call(model: str) -> str:
        resp = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
                temperature=0.2,
            ),
        )
        return (resp.text or "").strip()

    return run_gemini(_call, label="Gemini Chat")
