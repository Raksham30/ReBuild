"""Tests for Azure OpenAI chat generation, structured extraction, and retry/rate-limit handling."""
import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas import ParsedSection, StructuredExtraction
from app.services import generation, extraction
from app.services.generation import LLMUnavailableError
from openai import RateLimitError, InternalServerError, APIStatusError


def test_azure_openai_chat_generation(monkeypatch):
    """Test standard chat generation with Azure OpenAI."""
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test-resource.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key-not-real")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "This is an Azure OpenAI response."
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp

    monkeypatch.setattr(generation, "_get_azure_openai_client", lambda: mock_client)

    result = generation.generate("System prompt", "User prompt", max_tokens=100)
    assert result == "This is an Azure OpenAI response."
    mock_client.chat.completions.create.assert_called_once()
    kwargs = mock_client.chat.completions.create.call_args[1]
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["messages"] == [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "User prompt"},
    ]


def test_azure_openai_structured_extraction(monkeypatch):
    """Test structured extraction returns a valid StructuredExtraction Pydantic object."""
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test-resource.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key-not-real")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")

    expected_struct = StructuredExtraction(
        title="Attention Is All You Need",
        authors=["Vaswani et al."],
        datasets=["WMT 2014"],
        methods=["Transformer"],
        key_results=["28.4 BLEU"],
        limitations=["Computation cost"],
        summary="Introduces the Transformer model based solely on attention mechanisms.",
    )

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.parsed = expected_struct
    mock_choice.message.content = None
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.beta.chat.completions.parse.return_value = mock_resp

    monkeypatch.setattr(generation, "_get_azure_openai_client", lambda: mock_client)
    monkeypatch.setattr(extraction, "_get_azure_openai_client", lambda: mock_client)

    sections = [
        ParsedSection(section_type="abstract", text="We propose the Transformer.", page_start=1, page_end=1)
    ]
    extracted = extraction.extract_structured_fields("test_paper", sections)

    assert isinstance(extracted, StructuredExtraction)
    assert extracted.title == "Attention Is All You Need"
    assert extracted.authors == ["Vaswani et al."]
    assert extracted.summary == "Introduces the Transformer model based solely on attention mechanisms."


def test_azure_openai_structured_extraction_json_mode_fallback(monkeypatch):
    """Test structured extraction fallback to JSON object mode when beta parse raises."""
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test-resource.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_KEY", "test-key-not-real")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")

    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse.side_effect = Exception("Beta parse not supported")

    json_payload = {
        "title": "Fallback Paper Title",
        "authors": ["Author One"],
        "datasets": ["Dataset A"],
        "methods": ["Method B"],
        "key_results": ["99% accuracy"],
        "limitations": ["Small sample"],
        "summary": "This is a summary of the fallback extraction."
    }
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(json_payload)
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp

    monkeypatch.setattr(generation, "_get_azure_openai_client", lambda: mock_client)
    monkeypatch.setattr(extraction, "_get_azure_openai_client", lambda: mock_client)

    sections = [
        ParsedSection(section_type="abstract", text="Abstract text.", page_start=1, page_end=1)
    ]
    extracted = extraction.extract_structured_fields("test_paper", sections)

    assert isinstance(extracted, StructuredExtraction)
    assert extracted.title == "Fallback Paper Title"
    assert extracted.summary == "This is a summary of the fallback extraction."


def test_azure_openai_rate_limit_retry_and_exhaustion(monkeypatch):
    """Test that RateLimitError triggers retries and ultimately raises LLMUnavailableError(429)."""
    monkeypatch.setattr(generation, "AZURE_OPENAI_BASE_BACKOFF", 0.01)
    monkeypatch.setattr(generation, "AZURE_OPENAI_MAX_WAIT_SECONDS", 0.05)

    mock_client = MagicMock()
    request_obj = httpx.Request("POST", "https://test.openai.azure.com")
    response_obj = httpx.Response(429, request=request_obj, headers={"retry-after": "0.01"})
    rate_err = RateLimitError("Rate limit exceeded", response=response_obj, body=None)

    mock_client.chat.completions.create.side_effect = rate_err
    monkeypatch.setattr(generation, "_get_azure_openai_client", lambda: mock_client)

    with pytest.raises(LLMUnavailableError) as excinfo:
        generation.generate("System", "User")

    assert excinfo.value.status_code == 429
    assert "rate limit" in str(excinfo.value).lower()
    assert mock_client.chat.completions.create.call_count == generation.AZURE_OPENAI_MAX_RETRIES


def test_azure_openai_server_error_retry_and_exhaustion(monkeypatch):
    """Test that 503/InternalServerError triggers retries and raises LLMUnavailableError(503)."""
    monkeypatch.setattr(generation, "AZURE_OPENAI_BASE_BACKOFF", 0.01)
    monkeypatch.setattr(generation, "AZURE_OPENAI_MAX_WAIT_SECONDS", 0.05)

    mock_client = MagicMock()
    request_obj = httpx.Request("POST", "https://test.openai.azure.com")
    response_obj = httpx.Response(503, request=request_obj)
    server_err = InternalServerError("Server Overloaded", response=response_obj, body=None)

    mock_client.chat.completions.create.side_effect = server_err
    monkeypatch.setattr(generation, "_get_azure_openai_client", lambda: mock_client)

    with pytest.raises(LLMUnavailableError) as excinfo:
        generation.generate("System", "User")

    assert excinfo.value.status_code == 503
    assert "unavailable" in str(excinfo.value).lower() or "overloaded" in str(excinfo.value).lower()
    assert mock_client.chat.completions.create.call_count == generation.AZURE_OPENAI_MAX_RETRIES
