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


def test_not_an_nid_warning_forces_partial_even_with_all_fields_present():
    # All seven fields technically have a value, but the provider itself says
    # the card doesn't look like an NID — a critical warning must override
    # field-completeness and keep this out of "complete".
    data = {
        "name": "Md. Rahim Uddin",
        "fatherName": "Md. Abdul Karim",
        "motherName": "Amena Begum",
        "dateOfBirth": "1998-01-15",
        "nidNumber": "1234567890",
        "presentAddress": "Dhaka",
        "permanentAddress": "Cumilla",
    }
    provider_warnings = [{"code": "not_an_nid", "message": "Does not look like an NID", "field": None}]
    service = ExtractionService(_StubProvider(data, provider_warnings), _settings())

    response = asyncio.run(service.extract(_valid_png_bytes(), _valid_png_bytes()))

    assert response.status == "partial"


def test_duplicate_address_forces_partial():
    data = {
        "name": "Md. Rahim Uddin",
        "fatherName": "Md. Abdul Karim",
        "motherName": "Amena Begum",
        "dateOfBirth": "1998-01-15",
        "nidNumber": "1234567890",
        "presentAddress": "House 12, Dhaka",
        "permanentAddress": "House 12, Dhaka",  # identical to presentAddress
    }
    service = ExtractionService(_StubProvider(data), _settings())

    response = asyncio.run(service.extract(_valid_png_bytes(), _valid_png_bytes()))

    assert response.status == "partial"
    codes = [w.code for w in response.warnings]
    assert "duplicate_address" in codes


def test_cross_field_name_collision_forces_partial():
    data = {
        "name": "Md. Rahim Uddin",
        "fatherName": "Md. Rahim Uddin",  # identical to name
        "motherName": "Amena Begum",
        "dateOfBirth": "1998-01-15",
        "nidNumber": "1234567890",
        "presentAddress": "Dhaka",
        "permanentAddress": "Cumilla",
    }
    service = ExtractionService(_StubProvider(data), _settings())

    response = asyncio.run(service.extract(_valid_png_bytes(), _valid_png_bytes()))

    assert response.status == "partial"
    codes = [w.code for w in response.warnings]
    assert "cross_field_collision" in codes


def test_low_confidence_alone_does_not_force_partial():
    # Confirms low_confidence stays informational-only, unlike the critical
    # codes above — this is a deliberate distinction, not an oversight.
    data = {
        "name": "Md. Rahim Uddin",
        "fatherName": "Md. Abdul Karim",
        "motherName": "Amena Begum",
        "dateOfBirth": "1998-01-15",
        "nidNumber": "1234567890",
        "presentAddress": "Dhaka",
        "permanentAddress": "Cumilla",
    }
    service = ExtractionService(_StubProvider(data, confidence={"name": 0.1}), _settings())

    response = asyncio.run(service.extract(_valid_png_bytes(), _valid_png_bytes()))

    assert response.status == "complete"


def test_demo_mode_response_is_labeled_simulated():
    data = {
        "name": "Md. Rahim Uddin",
        "fatherName": "Md. Abdul Karim",
        "motherName": "Amena Begum",
        "dateOfBirth": "1998-01-15",
        "nidNumber": "1234567890",
        "presentAddress": "Dhaka",
        "permanentAddress": "Cumilla",
    }
    service = ExtractionService(_StubProvider(data), Settings(app_mode="demo"))

    response = asyncio.run(service.extract(_valid_png_bytes(), _valid_png_bytes()))

    codes = [w.code for w in response.warnings]
    assert "simulated_response" in codes
    # Being labeled simulated doesn't itself force partial — the fixture data
    # is genuinely complete, it's just not a live read of the uploaded images.
    assert response.status == "complete"
