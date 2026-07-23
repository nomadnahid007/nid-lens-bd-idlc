import time
import uuid

from app.config import Settings
from app.extraction.gemini_provider import PROMPT_VERSION
from app.extraction.normalizer import normalize
from app.extraction.provider import ExtractionProvider
from app.imaging.processor import validate_and_prepare
from app.models.schemas import ExtractionResponse

REQUIRED_FIELDS = [
    "name", "fatherName", "motherName", "dateOfBirth",
    "nidNumber", "presentAddress", "permanentAddress",
]

# Below this, a field is flagged for review even if Gemini returned a value —
# the model itself was told to lower confidence for blurred/cropped/ambiguous
# text, so this reflects what it actually found unclear, not a guess made
# before anyone looked at the image.
LOW_CONFIDENCE_THRESHOLD = 0.6

# Warning codes strong enough that the response can never be reported
# "complete" while one is present, even if every field technically has a
# value — each of these means specific data is very likely wrong, not just
# imprecise or worth a second look. (low_confidence, unusual_nid_length, etc.
# are NOT in this set on purpose: they're informational flags for a human
# reviewer, not evidence the extraction itself failed.)
CRITICAL_WARNING_CODES = {"not_an_nid", "duplicate_address", "cross_field_collision"}


class ExtractionService:
    def __init__(self, provider: ExtractionProvider, settings: Settings):
        self.provider = provider
        self.settings = settings

    async def extract(self, front_bytes: bytes, back_bytes: bytes) -> ExtractionResponse:
        start = time.perf_counter()
        request_id = str(uuid.uuid4())
        all_warnings = []

        # Image validation
        front_prepared, front_meta = validate_and_prepare(front_bytes, "front", self.settings)
        back_prepared, back_meta = validate_and_prepare(back_bytes, "back", self.settings)

        # "field" doubles as "which image this is about" here (front/back)
        # rather than one of the seven data fields — this also keeps the
        # (code, field) dedup key below from collapsing two genuinely
        # different warnings (e.g. both images being low-resolution) into one.
        for w in front_meta.get("warnings", []):
            all_warnings.append({"code": w["code"], "message": w["message"], "field": "front"})
        for w in back_meta.get("warnings", []):
            all_warnings.append({"code": w["code"], "message": w["message"], "field": "back"})

        # Provider extraction
        raw = await self.provider.extract(front_prepared, back_prepared)

        # Normalization
        normalized_data, norm_warnings = normalize(raw.get("data", {}))
        all_warnings.extend(norm_warnings)
        all_warnings.extend(raw.get("warnings", []))

        # Flag individually low-confidence fields. Only for fields that DO
        # have a value — a null field already has a more specific warning
        # (missing_nid, unparseable_dob, ...) from normalization above.
        confidence = raw.get("confidence", {})
        for field in REQUIRED_FIELDS:
            value = normalized_data.get(field)
            field_confidence = confidence.get(field)
            if value and field_confidence is not None and field_confidence < LOW_CONFIDENCE_THRESHOLD:
                all_warnings.append({
                    "code": "low_confidence",
                    "message": (
                        f"{field} was read with low confidence ({field_confidence:.0%}) — "
                        "double-check this value, or re-upload a clearer image if it looks wrong."
                    ),
                    "field": field,
                })

        # Demo mode returns the same pre-recorded fixture regardless of what
        # was uploaded — it exists to exercise the rest of the system (UI,
        # validation, error handling) without an API key, not to simulate
        # per-image OCR. Every demo-mode response says so explicitly, so a
        # fixture result can never be mistaken for real analysis of the
        # uploaded images.
        if self.settings.app_mode == "demo":
            all_warnings.append({
                "code": "simulated_response",
                "message": (
                    "This is pre-recorded demo data, not a live analysis of the uploaded images. "
                    "Set APP_MODE=live with a Gemini API key for real extraction."
                ),
                "field": None,
            })

        # Deduplicate warnings by code
        seen = set()
        deduped = []
        for w in all_warnings:
            key = (w.get("code"), w.get("field"))
            if key not in seen:
                seen.add(key)
                deduped.append(w)

        # Status — "complete" requires both a value in every field AND no
        # critical warning; a critical warning means the values present are
        # not trustworthy even though they're non-null.
        has_critical_warning = any(w.get("code") in CRITICAL_WARNING_CODES for w in deduped)
        all_fields_present = all(normalized_data.get(f) for f in REQUIRED_FIELDS)
        status = "complete" if (all_fields_present and not has_critical_warning) else "partial"

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        return ExtractionResponse(
            requestId=request_id,
            status=status,
            data=normalized_data,
            confidence=raw.get("confidence", {}),
            rawText=raw.get("rawText", {}),
            warnings=deduped,
            processingTimeMs=elapsed_ms,
            model=self.settings.gemini_model if self.settings.app_mode == "live" else "fixture",
            promptVersion=PROMPT_VERSION,
        )
