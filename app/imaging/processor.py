from io import BytesIO

from PIL import Image, ImageOps, ImageStat

from app.config import Settings

MAX_DIMENSION = 2000
MIN_UPSCALE_DIMENSION = 900  # images smaller than this are upscaled so the model has more pixels to work with
SUPPORTED_FORMATS = {"JPEG", "PNG"}


class ImageValidationError(Exception):
    pass


class InvalidImageError(ImageValidationError):
    pass


class ImageTooLargeError(ImageValidationError):
    pass


class UnsupportedMediaTypeError(ImageValidationError):
    pass


def validate_and_prepare(image_bytes: bytes, side: str, settings: Settings) -> tuple[bytes, dict]:
    if len(image_bytes) == 0:
        raise InvalidImageError(f"{side} image is empty")

    max_bytes = settings.max_image_size_mb * 1024 * 1024
    if len(image_bytes) > max_bytes:
        raise ImageTooLargeError(f"{side} image exceeds {settings.max_image_size_mb} MB")

    try:
        img = Image.open(BytesIO(image_bytes))
        img.load()
    except Exception:
        raise InvalidImageError(f"{side} image could not be decoded")

    original_format = img.format
    if original_format not in SUPPORTED_FORMATS:
        raise UnsupportedMediaTypeError(f"{side} image must be JPG, JPEG, or PNG, got {original_format}")

    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")

    if img.width < settings.min_image_dimension or img.height < settings.min_image_dimension:
        raise InvalidImageError(
            f"{side} image is too small to process; minimum {settings.min_image_dimension}px per side"
        )

    # Deliberately no pixel-dimension or contrast "this might be unclear"
    # warning here. An earlier version guessed at a resolution threshold and
    # a contrast threshold, but both are unvalidated proxies that fire on
    # images the model reads just fine — a fixed pixel count or grayscale
    # variance doesn't actually predict extraction quality. The model's own
    # per-field confidence score (see ExtractionService) is the real signal
    # for "this field might need a re-upload", since it reflects what Gemini
    # itself found ambiguous rather than a guess made before it even looked.
    longest_side = max(img.width, img.height)
    if longest_side > MAX_DIMENSION:
        scale = MAX_DIMENSION / longest_side
        new_size = (round(img.width * scale), round(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)
    elif longest_side < MIN_UPSCALE_DIMENSION:
        # Small-but-valid images are upscaled rather than rejected — gives the
        # model more working pixels instead of a hard cutoff on "too small".
        scale = MIN_UPSCALE_DIMENSION / longest_side
        new_size = (round(img.width * scale), round(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    gray = img.convert("L")
    stddev = ImageStat.Stat(gray).stddev[0]

    output = BytesIO()
    img.save(output, format="JPEG", quality=90)

    meta = {
        "originalFormat": original_format,
        "width": img.width,
        "height": img.height,
        "contrastScore": round(stddev, 1),
        "warnings": [],
    }

    return output.getvalue(), meta
