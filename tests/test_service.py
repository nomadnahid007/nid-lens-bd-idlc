import asyncio
from io import BytesIO

from PIL import Image

from app.config import Settings
from app.extraction.provider import ExtractionProvider
from app.extraction.service import ExtractionService


class _StubProvider(ExtractionProvider):
    def __init__(self, data, warnings=None, confidence=None):
        self._data = data
        self._warnings = warnings or []
        self._confidence = confidence or {}

    async def extract(self, front_bytes: bytes, back_bytes: bytes) -> dict:
        return {
            "data": self._data,
            "confidence": self._confidence,
            "rawText": {"front": "stub front", "back": "stub back"},
            "warnings": self._warnings,
        }


def _valid_png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (400, 400), (200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _settings() -> Settings:
    return Settings(app_mode="demo")


def test_status_is_complete_when_all_fields_present():
    data = {
        "name": "Md. Rahim Uddin",
        "fatherName": "Md. Abdul Karim",
        "motherName": "Amena Begum",
        "dateOfBirth": "1998-01-15",
        "nidNumber": "1234567890",
        "presentAddress": "Dhaka",
        "permanentAddress": "Cumilla",
    }
    service = ExtractionService(_StubProvider(data), _settings())

    response = asyncio.run(service.extract(_valid_png_bytes(), _valid_png_bytes()))

    assert response.status == "complete"


def test_status_is_partial_when_a_field_is_missing():
    data = {
        "name": "Md. Rahim Uddin",
        "fatherName": "Md. Abdul Karim",
        "motherName": "Amena Begum",
        "dateOfBirth": "1998-01-15",
        "nidNumber": "1234567890",
        "presentAddress": "Dhaka",
        "permanentAddress": None,  # unreadable on the card
    }
    service = ExtractionService(_StubProvider(data), _settings())

    response = asyncio.run(service.extract(_valid_png_bytes(), _valid_png_bytes()))

    assert response.status == "partial"
    assert response.data.permanent_address is None
    # The rest of the response is still fully usable, not discarded.
    assert response.data.name == "Md. Rahim Uddin"


def test_provider_warnings_and_image_warnings_are_merged_and_deduped():
    data = {
        "name": "Md. Rahim Uddin",
        "fatherName": "Md. Abdul Karim",
        "motherName": "Amena Begum",
        "dateOfBirth": "1998-01-15",
        "nidNumber": "1234567890",
        "presentAddress": "Dhaka",
        "permanentAddress": "Cumilla",
    }
    provider_warnings = [
        {"code": "not_an_nid", "message": "Card does not look like an NID", "field": None},
        {"code": "not_an_nid", "message": "Duplicate warning", "field": None},
    ]
    service = ExtractionService(_StubProvider(data, provider_warnings), _settings())

    response = asyncio.run(service.extract(_valid_png_bytes(), _valid_png_bytes()))

    codes = [w.code for w in response.warnings]
    assert codes.count("not_an_nid") == 1


def test_low_confidence_field_gets_flagged():
    data = {
        "name": "Md. Rahim Uddin",
        "fatherName": "Md. Abdul Karim",
        "motherName": "Amena Begum",
        "dateOfBirth": "1998-01-15",
        "nidNumber": "1234567890",
        "presentAddress": "Dhaka",
        "permanentAddress": "Cumilla",
    }
    confidence = {"presentAddress": 0.35}
    service = ExtractionService(_StubProvider(data, confidence=confidence), _settings())

    response = asyncio.run(service.extract(_valid_png_bytes(), _valid_png_bytes()))

    low_conf_warnings = [w for w in response.warnings if w.code == "low_confidence"]
    assert len(low_conf_warnings) == 1
    assert low_conf_warnings[0].field == "presentAddress"
    # Status is independent of confidence — a low-confidence-but-present value
    # still counts toward "complete", it's just flagged for human review.
    assert response.status == "complete"


def test_high_confidence_fields_are_not_flagged():
    data = {
        "name": "Md. Rahim Uddin",
        "fatherName": "Md. Abdul Karim",
        "motherName": "Amena Begum",
        "dateOfBirth": "1998-01-15",
        "nidNumber": "1234567890",
        "presentAddress": "Dhaka",
        "permanentAddress": "Cumilla",
    }
    confidence = {k: 0.95 for k in data}
    service = ExtractionService(_StubProvider(data, confidence=confidence), _settings())

    response = asyncio.run(service.extract(_valid_png_bytes(), _valid_png_bytes()))

    assert [w for w in response.warnings if w.code == "low_confidence"] == []
