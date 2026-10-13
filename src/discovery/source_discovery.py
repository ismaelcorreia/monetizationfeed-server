"""
SourceDiscovery — finds new news sources using DuckDuckGo search + Newspaper3k analysis.
Single responsibility: discover candidate source URLs and persist them.
No Anthropic API dependency — fully offline capable with DDG.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from duckduckgo_search import DDGS

from config.logging_setup import get_logger
from ingestion.topic_classifier import TopicClassifier
from models.entities import DiscoveredSource, SourceType
from storage.source_repository import SourceRepository

logger = get_logger("discovery.source_discovery")

# Patterns to detect locale from URL/content
_LOCALE_HINTS: dict[str, str] = {
    "angola": "pt-AO", "luanda": "pt-AO", ".ao": "pt-AO",
    "portugal": "pt-PT", ".pt": "pt-PT",
    "brasil": "pt-BR", "brazil": "pt-BR", ".br": "pt-BR",
    "nigeria": "en-NG", "kenya": "en-KE", "ghana": "en-GH",
    "africa": "en-AF",
}

_MAX_RESULTS_PER_TERM = 10


@dataclass
class DiscoveryResult:
    discovered: int = 0
    skipped_duplicates: int = 0
    failed: int = 0


class SourceDiscovery:

    def __init__(
        self,
        source_repo: SourceRepository,
        classifier: TopicClassifier,
        search_terms: list[str],
    ) -> None:
        self._repo = source_repo
        self._classifier = classifier
        self._search_terms = search_terms

    # ── Public interface ──────────────────────────────────────────────────────

    def run_discovery(self) -> DiscoveryResult:
        result = DiscoveryResult()
        existing_urls = self._load_existing_urls()

        for term in self._search_terms:
            logger.info("Discovering sources for term: %s", term)
            hits = self._search_web(term)

            for hit in hits:
                base_url = self._extract_base_url(hit["href"])
                if not base_url or base_url in existing_urls:
                    result.skipped_duplicates += 1
                    continue

                try:
                    ds = self._build_discovered_source(base_url, hit, term)
                    self._repo.upsert_discovered(ds)
                    existing_urls.add(base_url)
                    result.discovered += 1
                    logger.debug("Discovered: %s (%s)", ds.name, ds.url)
                except Exception as exc:
                    logger.warning("Failed to persist discovered source %s: %s", base_url, exc)
                    result.failed += 1

        logger.info(
            "Discovery complete — new=%d skipped=%d failed=%d",
            result.discovered, result.skipped_duplicates, result.failed,
        )
        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    def _search_web(self, term: str) -> list[dict]:
        try:
            with DDGS() as ddgs:
                return list(ddgs.text(term + " site:news OR site:journal OR site:.com/news",
                                      max_results=_MAX_RESULTS_PER_TERM))
        except Exception as exc:
            logger.error("DuckDuckGo search failed for '%s': %s", term, exc)
            return []

    def _build_discovered_source(
        self, base_url: str, hit: dict, search_term: str
    ) -> DiscoveredSource:
        title = hit.get("title", base_url)
        body = hit.get("body", "")
        topic = self._classifier.classify(title, body, search_term.split())
        locale = self._infer_locale(base_url, body)
        app_hint = self._infer_app_name(base_url, title)

        return DiscoveredSource(
            url=base_url,
            name=app_hint or title[:80],
            topic_category=topic,
            locale=locale,
            source_type=SourceType.DISCOVERED,
            app_hint=app_hint,
        )

    def _load_existing_urls(self) -> set[str]:
        sources = self._repo.get_active_sources()
        discovered = self._repo.get_unpromoted_discovered()
        return {s.url for s in sources} | {d.url for d in discovered}

    @staticmethod
    def _extract_base_url(url: str) -> str | None:
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return None
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return None

    @staticmethod
    def _infer_locale(url: str, body: str) -> str:
        combined = (url + " " + body).lower()
        for hint, locale in _LOCALE_HINTS.items():
            if hint in combined:
                return locale
        return "en-US"

    @staticmethod
    def _infer_app_name(url: str, title: str) -> str | None:
        try:
            netloc = urlparse(url).netloc
            name = netloc.replace("www.", "").split(".")[0]
            return name.title() if name else title[:40]
        except Exception:
            return None
