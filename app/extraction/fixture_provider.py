import asyncio
import json
from pathlib import Path

from app.extraction.provider import ExtractionProvider

FIXTURE_PATH = Path(__file__).resolve().parent.parent.parent / "fixtures" / "demo_response.json"


class FixtureProvider(ExtractionProvider):
    async def extract(self, front_bytes: bytes, back_bytes: bytes) -> dict:
        await asyncio.sleep(0.8)
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        return {
            "data": payload["data"],
            "rawText": payload["rawText"],
            "confidence": payload["confidence"],
            "warnings": [],
        }
