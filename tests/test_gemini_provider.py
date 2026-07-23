import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.extraction.gemini_provider as gemini_provider_module
from app.config import Settings
from app.extraction.gemini_provider import GeminiProvider, ProviderError
from app.models.schemas import Confidence, ExtractedFields, GeminiExtractionSchema, RawText


def _settings() -> Settings:
    return Settings(app_mode="live", gemini_api_key="test-key", gemini_model="gemini-flash-latest")


def _provider() -> GeminiProvider:
    provider = GeminiProvider(_settings())
    # Real network access is never exercised — the SDK client is replaced
    # with a mock immediately after construction, so these tests verify
    # GeminiProvider's own parsing/error-handling logic in isolation, not
    # the Gemini API itself.
    provider.client = MagicMock()
    return provider


def test_parses_structured_response_when_sdk_returns_parsed_schema():
    provider = _provider()
    schema = GeminiExtractionSchema(
        data=ExtractedFields(
            name="Md. Rahim Uddin",
            father_name="Md. Abdul Karim",
            mother_name="Amena Begum",
            date_of_birth="1998-01-15",
            nid_number="1234567890",
            present_address="Dhaka",
            permanent_address="Cumilla",
        ),
        confidence=Confidence(name=0.97),
        raw_text=RawText(front="front raw text", back="back raw text"),
        warnings=[],
    )
    provider.client.models.generate_content.return_value = SimpleNamespace(parsed=schema, text=None)

    result = asyncio.run(provider.extract(b"front-bytes", b"back-bytes"))

    assert result["data"]["name"] == "Md. Rahim Uddin"
    assert result["data"]["nidNumber"] == "1234567890"
    assert result["confidence"]["name"] == 0.97
    assert result["rawText"]["front"] == "front raw text"


def test_falls_back_to_json_text_when_sdk_does_not_populate_parsed():
    provider = _provider()
    payload = {
        "data": {
            "name": "Md. Rahim",
            "fatherName": None,
            "motherName": None,
            "dateOfBirth": None,
            "nidNumber": None,
            "presentAddress": None,
            "permanentAddress": None,
        },
        "confidence": {},
        "rawText": {"front": None, "back": None},
        "warnings": [],
    }
    provider.client.models.generate_content.return_value = SimpleNamespace(parsed=None, text=json.dumps(payload))

    result = asyncio.run(provider.extract(b"front-bytes", b"back-bytes"))

    assert result["data"]["name"] == "Md. Rahim"


def test_unparseable_text_raises_sanitized_provider_error():
    provider = _provider()
    provider.client.models.generate_content.return_value = SimpleNamespace(parsed=None, text="not valid json")

    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(provider.extract(b"front-bytes", b"back-bytes"))

    message = str(exc_info.value)
    assert "unexpected response" in message
    # The raw unparseable text must never leak into the client-facing message.
    assert "not valid json" not in message


def test_sdk_exception_is_sanitized_not_leaked_to_client():
    provider = _provider()
    sensitive_detail = "internal-detail-that-should-never-reach-a-client"
    provider.client.models.generate_content.side_effect = RuntimeError(sensitive_detail)

    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(provider.extract(b"front-bytes", b"back-bytes"))

    message = str(exc_info.value)
    assert sensitive_detail not in message
    assert "unavailable" in message


def test_timeout_is_sanitized_and_raises_promptly(monkeypatch, caplog):
    provider = _provider()
    monkeypatch.setattr(gemini_provider_module, "PROVIDER_TIMEOUT_SECONDS", 0.05)

    def _slow_call(*args, **kwargs):
        time.sleep(2)
        return SimpleNamespace(parsed=None, text="{}")

    provider.client.models.generate_content.side_effect = _slow_call

    with caplog.at_level("ERROR"):
        with pytest.raises(ProviderError) as exc_info:
            asyncio.run(provider.extract(b"front-bytes", b"back-bytes"))

    assert "timed out" in str(exc_info.value)
    # `asyncio.run()`'s own cleanup waits for the orphaned background thread
    # to finish (Python 3.9+ shuts down the default executor on exit), so
    # wall-clock time around the whole call isn't a reliable way to prove the
    # *caller* got an answer promptly — the log record's timestamp, written
    # the moment `wait_for` actually times out, is the real signal here.
    assert any("timed out after 0.05s" in record.message for record in caplog.records)
