from abc import ABC, abstractmethod


class ExtractionProvider(ABC):
    @abstractmethod
    async def extract(self, front_bytes: bytes, back_bytes: bytes) -> dict:
        """Extract NID fields from front/back image bytes.

        Returns a dict with keys: data, rawText, confidence — conforming to
        ExtractedFields, RawText, and Confidence respectively.
        """
        raise NotImplementedError
