"""
Thin wrapper for "generate text from a prompt" used by the agent's
synthesis steps (answering, comparison narrative, lit review paragraphs).

Foundry Agent Service (if FOUNDRY_PROJECT_ENDPOINT is set) is checked
first -- it's a genuinely different orchestration mechanism (a managed
tool-calling runtime), not just another model provider, so it stays as
its own path. Otherwise, generation runs on Azure OpenAI GPT-4o-mini.

Retry and rate limit handling:
  * HTTP 429 (RateLimitError) -> bounded exponential backoff or wait Retry-After header
  * HTTP 500/502/503/504 / connection timeouts -> bounded retry with exponential backoff
  * Retries exhausted -> LLMUnavailableError, which main.py turns into
                         a clean 429/503 response instead of a 500 traceback.
"""
from __future__ import annotations
import re
import time
from typing import Callable, TypeVar

from openai import (
    AzureOpenAI,
    RateLimitError,
    APIStatusError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
)

from app.config import get_settings

T = TypeVar("T")

AZURE_OPENAI_MAX_RETRIES = 3       # attempts for transient errors
AZURE_OPENAI_BASE_BACKOFF = 2.0
AZURE_OPENAI_MAX_WAIT_SECONDS = 20.0    # never block a request longer than this per wait


class LLMUnavailableError(RuntimeError):
    """Azure OpenAI model deployment is rate-limited or unavailable."""

    def __init__(self, message: str, status_code: int = 429):
        super().__init__(message)
        self.status_code = status_code


def _get_azure_openai_client() -> AzureOpenAI:
    settings = get_settings()
    if not (settings.azure_openai_endpoint and settings.azure_openai_key and settings.azure_openai_chat_deployment):
        raise RuntimeError(
            "Azure OpenAI is not configured. Please set AZURE_OPENAI_ENDPOINT, "
            "AZURE_OPENAI_KEY, and AZURE_OPENAI_CHAT_DEPLOYMENT in backend/.env."
        )
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_key,
        api_version=settings.azure_openai_api_version,
    )


def _suggested_retry_delay(err: Exception) -> float | None:
    """Extract Retry-After delay in seconds if provided by headers or error message."""
    response = getattr(err, "response", None)
    if response is not None:
        headers = getattr(response, "headers", {})
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass

    msg = str(err)
    m = re.search(r"retry[- ]after[:\s]+([\d.]+)", msg, re.IGNORECASE) or \
        re.search(r"try again in ([\d.]+)s", msg, re.IGNORECASE) or \
        re.search(r"retry in ([\d.]+)s", msg, re.IGNORECASE)
    return float(m.group(1)) if m else None


def run_azure_openai(call: Callable[[], T], label: str = "Azure OpenAI") -> T:
    """Runs call() with retry and rate-limit handling for Azure OpenAI."""
    last_err: Exception | None = None

    for attempt in range(1, AZURE_OPENAI_MAX_RETRIES + 1):
        try:
            return call()
        except RateLimitError as e:
            last_err = e
            if attempt == AZURE_OPENAI_MAX_RETRIES:
                break
            suggested = _suggested_retry_delay(e)
            wait = suggested if suggested is not None else AZURE_OPENAI_BASE_BACKOFF * (2 ** (attempt - 1))
            wait = min(wait + 0.5, AZURE_OPENAI_MAX_WAIT_SECONDS)
            print(f"[{label}] Rate limit (429) hit (attempt {attempt}/{AZURE_OPENAI_MAX_RETRIES}). Retrying in {wait:.1f}s...")
            time.sleep(wait)
        except (InternalServerError, APIConnectionError, APITimeoutError) as e:
            last_err = e
            if attempt == AZURE_OPENAI_MAX_RETRIES:
                break
            wait = min(AZURE_OPENAI_BASE_BACKOFF * (2 ** (attempt - 1)) + 0.5, AZURE_OPENAI_MAX_WAIT_SECONDS)
            print(f"[{label}] Transient error ({type(e).__name__}) (attempt {attempt}/{AZURE_OPENAI_MAX_RETRIES}). Retrying in {wait:.1f}s...")
            time.sleep(wait)
        except APIStatusError as e:
            code = getattr(e, "status_code", None)
            if code == 429:
                last_err = e
                if attempt == AZURE_OPENAI_MAX_RETRIES:
                    break
                suggested = _suggested_retry_delay(e)
                wait = suggested if suggested is not None else AZURE_OPENAI_BASE_BACKOFF * (2 ** (attempt - 1))
                wait = min(wait + 0.5, AZURE_OPENAI_MAX_WAIT_SECONDS)
                print(f"[{label}] Rate limit (429) hit (attempt {attempt}/{AZURE_OPENAI_MAX_RETRIES}). Retrying in {wait:.1f}s...")
                time.sleep(wait)
            elif code in (500, 502, 503, 504):
                last_err = e
                if attempt == AZURE_OPENAI_MAX_RETRIES:
                    break
                wait = min(AZURE_OPENAI_BASE_BACKOFF * (2 ** (attempt - 1)) + 0.5, AZURE_OPENAI_MAX_WAIT_SECONDS)
                print(f"[{label}] Server error ({code}) (attempt {attempt}/{AZURE_OPENAI_MAX_RETRIES}). Retrying in {wait:.1f}s...")
                time.sleep(wait)
            else:
                # 400, 401, 403, 404 etc. are non-retryable
                raise

    code = getattr(last_err, "status_code", None)
    if isinstance(last_err, RateLimitError) or code == 429:
        raise LLMUnavailableError(
            "Azure OpenAI rate limit exceeded. Please try again in a few moments.", 429
        ) from last_err
    if isinstance(last_err, (InternalServerError, APIConnectionError, APITimeoutError)) or code in (500, 502, 503, 504):
        raise LLMUnavailableError(
            "Azure OpenAI is temporarily overloaded or unavailable. Please try again in a minute.", 503
        ) from last_err

    if last_err is not None:
        raise last_err
    raise LLMUnavailableError("Azure OpenAI generation failed.", 500)


def generate(system_prompt: str, user_prompt: str, max_tokens: int = 600) -> str:
    settings = get_settings()
    if settings.use_foundry_agent:
        from app.services import foundry_agent
        combined = f"{system_prompt}\n\n{user_prompt}"
        return foundry_agent.run_agent(combined, tool_defs=[], tool_impls={}, max_tokens=max_tokens)
    return _generate_azure_openai(system_prompt, user_prompt, max_tokens)


def _generate_azure_openai(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    settings = get_settings()
    client = _get_azure_openai_client()

    def _call() -> str:
        resp = client.chat.completions.create(
            model=settings.azure_openai_chat_deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.2,
        )
        if resp.choices and resp.choices[0].message:
            return (resp.choices[0].message.content or "").strip()
        return ""

    return run_azure_openai(_call, label="Azure OpenAI Chat")
