from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.extraction.fixture_provider import FixtureProvider
from app.extraction.gemini_provider import GeminiProvider
from app.extraction.service import ExtractionService
from app.models.schemas import ExtractionResponse, HealthResponse

router = APIRouter()

SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "samples"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()

    if settings.app_mode == "demo":
        status = "ready"
    elif settings.gemini_api_key:
        status = "ready"
    else:
        status = "no_api_key"

    return HealthResponse(status=status, mode=settings.app_mode, model=settings.gemini_model)


@router.post("/api/v1/nid/extract", response_model=ExtractionResponse)
async def extract_nid(
    front: UploadFile = File(..., description="NID front image (JPG/JPEG/PNG)"),
    back: UploadFile = File(..., description="NID back image (JPG/JPEG/PNG)"),
    settings: Settings = Depends(get_settings),
) -> ExtractionResponse:
    front_bytes = await front.read()
    back_bytes = await back.read()

    if settings.app_mode == "live":
        if not settings.gemini_api_key:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "NO_API_KEY",
                    "message": "Live mode requires GEMINI_API_KEY",
                    "suggestion": "Set APP_MODE=demo or add the key to .env",
                },
            )
        provider = GeminiProvider(settings)
    else:
        provider = FixtureProvider()

    service = ExtractionService(provider, settings)
    return await service.extract(front_bytes, back_bytes)


SAMPLE_IMAGE_RESPONSES = {
    200: {
        "content": {"image/png": {"schema": {"type": "string", "format": "binary"}}},
        "description": "Synthetic NID sample image (PNG)",
    }
}


@router.get("/api/v1/samples/front", response_class=FileResponse, responses=SAMPLE_IMAGE_RESPONSES)
async def sample_front() -> FileResponse:
    return FileResponse(SAMPLES_DIR / "nid_front_synthetic.png", media_type="image/png")


@router.get("/api/v1/samples/back", response_class=FileResponse, responses=SAMPLE_IMAGE_RESPONSES)
async def sample_back() -> FileResponse:
    return FileResponse(SAMPLES_DIR / "nid_back_synthetic.png", media_type="image/png")
