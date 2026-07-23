from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def to_camel(field_name: str) -> str:
    first, *rest = field_name.split("_")
    return first + "".join(word.capitalize() for word in rest)


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ExtractedFields(CamelModel):
    name: str | None = None
    father_name: str | None = None
    mother_name: str | None = None
    date_of_birth: str | None = None
    nid_number: str | None = None
    present_address: str | None = None
    permanent_address: str | None = None


class Confidence(CamelModel):
    name: float | None = Field(default=None, ge=0, le=1)
    father_name: float | None = Field(default=None, ge=0, le=1)
    mother_name: float | None = Field(default=None, ge=0, le=1)
    date_of_birth: float | None = Field(default=None, ge=0, le=1)
    nid_number: float | None = Field(default=None, ge=0, le=1)
    present_address: float | None = Field(default=None, ge=0, le=1)
    permanent_address: float | None = Field(default=None, ge=0, le=1)


class RawText(CamelModel):
    front: str | None = None
    back: str | None = None


class Warning(CamelModel):
    code: str
    message: str
    field: str | None = None


class ExtractionResponse(CamelModel):
    request_id: str
    status: Literal["complete", "partial"]
    data: ExtractedFields
    confidence: Confidence
    raw_text: RawText
    warnings: list[Warning] = Field(default_factory=list)
    processing_time_ms: int
    model: str
    prompt_version: str


class GeminiExtractionSchema(CamelModel):
    """Shape Gemini must return. Distinct from ExtractionResponse — the service
    layer adds requestId, processingTimeMs, model, promptVersion, and status."""

    data: ExtractedFields
    confidence: Confidence
    raw_text: RawText
    warnings: list[Warning] = Field(default_factory=list)


class ErrorResponse(CamelModel):
    code: str
    message: str
    field: str | None = None
    suggestion: str | None = None
    details: dict | None = None


class HealthResponse(CamelModel):
    status: Literal["ready", "no_api_key", "starting"]
    mode: Literal["demo", "live"]
    model: str
