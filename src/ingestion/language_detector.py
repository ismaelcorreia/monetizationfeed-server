"""
LanguageDetector — thin wrapper around langdetect.
Single responsibility: detect language of a text string.
"""
from __future__ import annotations

from config.logging_setup import get_logger

logger = get_logger("ingestion.language_detector")


class LanguageDetector:

    def detect(self, text: str) -> str:
        """Returns ISO 639-1 language code, defaults to 'en' on failure."""
        if not text or len(text.strip()) < 20:
            return "en"
        try:
            from langdetect import detect
            return detect(text)
        except Exception as exc:
            logger.debug("Language detection failed: %s", exc)
            return "en"

    def is_portuguese(self, text: str) -> bool:
        return self.detect(text) in ("pt",)
