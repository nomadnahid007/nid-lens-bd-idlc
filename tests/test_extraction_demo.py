from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


def _image_bytes(size=(400, 400), color=(200, 200, 200), fmt="PNG"):
    buf = BytesIO()
    Image.new("RGB", size, color=color).save(buf, format=fmt)
    return buf.getvalue()


def test_extract_demo_mode_returns_complete_response():
    front = _image_bytes()
    back = _image_bytes()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/nid/extract",
            files={
                "front": ("front.png", front, "image/png"),
                "back": ("back.png", back, "image/png"),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "complete"
    assert body["data"]["name"] == "Md. Rahim Uddin"
    assert body["model"] == "fixture"
    assert body["promptVersion"] == "v1.0.0"


def test_extract_missing_back_returns_422():
    front = _image_bytes()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/nid/extract",
            files={"front": ("front.png", front, "image/png")},
        )

    assert response.status_code == 422


def test_extract_wrong_image_format_returns_415():
    # A genuinely non-image blob (e.g. plain text) fails to decode at all and
    # correctly maps to 400 INVALID_IMAGE. To exercise the *wrong format*
    # path (415 UNSUPPORTED_MEDIA_TYPE), the upload must be a real image PIL
    # can decode but that isn't JPEG/PNG — a BMP here.
    front = _image_bytes(fmt="BMP")
    back = _image_bytes()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/nid/extract",
            files={
                "front": ("front.bmp", front, "image/bmp"),
                "back": ("back.png", back, "image/png"),
            },
        )

    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_extract_tiny_image_returns_400():
    front = _image_bytes(size=(1, 1))
    back = _image_bytes()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/nid/extract",
            files={
                "front": ("front.png", front, "image/png"),
                "back": ("back.png", back, "image/png"),
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IMAGE"


def test_extract_corrupt_image_returns_400():
    # Not a truncated/malformed image file, garbage bytes with no valid
    # image header at all — must fail at decode, not crash the server.
    front = b"\x00\x01\x02not-an-image\xff\xfe" * 20
    back = _image_bytes()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/nid/extract",
            files={
                "front": ("front.png", front, "image/png"),
                "back": ("back.png", back, "image/png"),
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IMAGE"


def test_extract_empty_image_returns_400():
    front = b""
    back = _image_bytes()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/nid/extract",
            files={
                "front": ("front.png", front, "image/png"),
                "back": ("back.png", back, "image/png"),
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IMAGE"


def test_extract_oversized_image_returns_413():
    from app.config import get_settings

    settings = get_settings()
    oversized = b"\x00" * (settings.max_image_size_mb * 1024 * 1024 + 1)
    back = _image_bytes()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/nid/extract",
            files={
                "front": ("front.png", oversized, "image/png"),
                "back": ("back.png", back, "image/png"),
            },
        )

    assert response.status_code == 413
    assert response.json()["code"] == "IMAGE_TOO_LARGE"


def test_extract_decompression_bomb_returns_400():
    # A flat-color image compresses extremely well — this decodes to well
    # over the 50-megapixel decoded-pixel cap while staying under the
    # byte-size limit, so it specifically exercises the decoded-pixel check
    # rather than the compressed-size check above.
    front = _image_bytes(size=(9000, 9000))  # 81 megapixels decoded
    back = _image_bytes()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/nid/extract",
            files={
                "front": ("front.png", front, "image/png"),
                "back": ("back.png", back, "image/png"),
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IMAGE"
