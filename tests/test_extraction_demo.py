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
