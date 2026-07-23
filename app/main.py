import logging
import mimetypes
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import get_settings
from app.extraction.gemini_provider import ProviderError
from app.imaging.processor import ImageTooLargeError, InvalidImageError, UnsupportedMediaTypeError

logger = logging.getLogger("nid_lens_bd")
logging.basicConfig(level=logging.INFO)

# The slim base image's mimetypes database doesn't know modern font/SVG
# extensions, so StaticFiles falls back to text/plain — some browsers refuse
# to load a font whose Content-Type isn't a font type. Register explicitly.
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("image/svg+xml", ".svg")

app = FastAPI(title="NID Lens BD", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.exception_handler(UnsupportedMediaTypeError)
async def unsupported_media(request: Request, exc: UnsupportedMediaTypeError):
    return JSONResponse(
        status_code=415,
        content={
            "code": "UNSUPPORTED_MEDIA_TYPE",
            "message": str(exc),
            "suggestion": "Upload JPG, JPEG, or PNG only",
        },
    )


@app.exception_handler(ImageTooLargeError)
async def image_too_large(request: Request, exc: ImageTooLargeError):
    return JSONResponse(
        status_code=413,
        content={
            "code": "IMAGE_TOO_LARGE",
            "message": str(exc),
            "suggestion": "Compress the image or use a smaller resolution",
        },
    )


@app.exception_handler(InvalidImageError)
async def invalid_image(request: Request, exc: InvalidImageError):
    return JSONResponse(
        status_code=400,
        content={
            "code": "INVALID_IMAGE",
            "message": str(exc),
            "suggestion": "Check the file is a readable image and meets minimum resolution",
        },
    )


@app.exception_handler(ProviderError)
async def provider_error(request: Request, exc: ProviderError):
    return JSONResponse(
        status_code=503,
        content={
            "code": "PROVIDER_UNAVAILABLE",
            "message": str(exc),
            "suggestion": "Retry in a moment or switch APP_MODE=demo",
        },
    )

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


@app.on_event("startup")
async def on_startup() -> None:
    settings = get_settings()
    logger.info("NID Lens BD starting | mode=%s | model=%s", settings.app_mode, settings.gemini_model)
