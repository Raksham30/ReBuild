"""
Embedding generation via Google Gemini API (gemini-embedding-001).
Gemini is the sole, permanent embedding provider -- misconfiguration or
missing GEMINI_API_KEY raises immediately rather than silently degrading.
"""
import time
from google import genai
from app.config import get_settings

GEMINI_BATCH_SIZE = 16
MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 2.0
INTER_BATCH_DELAY_SECONDS = 0.5

_client = None


def _get_gemini_client():
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _retry_with_backoff(fn, max_retries=MAX_RETRIES, base_backoff=BASE_BACKOFF_SECONDS):
    from google.genai.errors import ClientError, ServerError

    for attempt in range(max_retries):
        try:
            return fn()
        except (ClientError, ServerError) as e:
            code = getattr(e, "code", None)
            # 429 = rate limited, 503 = model temporarily overloaded on
            # Google's side ("high demand") -- both worth retrying.
            # Anything else (bad key, invalid request, etc.) fails fast.
            if code not in (429, 503) or attempt == max_retries - 1:
                raise
            wait = base_backoff * (2 ** attempt)
            reason = "Rate limit" if code == 429 else "Model overloaded (503)"
            print(f"[embeddings] {reason} hit (attempt {attempt+1}/{max_retries}). Retrying in {wait:.1f}s...")
            time.sleep(wait)


def _batched(items: list, batch_size: int):
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def _embed_gemini(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    settings = get_settings()
    client = _get_gemini_client()
    model = settings.gemini_embedding_model
    results: list[list[float]] = []

    for batch in _batched(texts, GEMINI_BATCH_SIZE):
        def _call():
            from google.genai import types
            res = client.models.embed_content(
                model=model,
                contents=batch,
                # Explicit, not implicit: gemini-embedding-001 supports MRL
                # truncation to 768/1536/3072. This MUST match the Azure AI
                # Search index's vector_search_dimensions (indexing.py) --
                # relying on the SDK's undeclared default here is exactly
                # the kind of silent mismatch that makes Azure Search
                # reject documents on upload without raising an error.
                config=types.EmbedContentConfig(output_dimensionality=settings.gemini_embedding_dim),
            )
            return [e.values for e in res.embeddings]

        embeddings = _retry_with_backoff(_call)
        results.extend(embeddings)
        print(f"[embeddings] Gemini batch processed ({len(batch)} items, total: {len(results)})")
        if INTER_BATCH_DELAY_SECONDS > 0:
            time.sleep(INTER_BATCH_DELAY_SECONDS)

    return results


def embed_texts(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    if not settings.use_gemini_embeddings:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Embeddings run on Gemini only "
            "(get a free key: https://aistudio.google.com/apikey) -- "
            "there is no fallback in this build."
        )
    return _embed_gemini(texts)


def embedding_dim() -> int:
    return get_settings().gemini_embedding_dim
