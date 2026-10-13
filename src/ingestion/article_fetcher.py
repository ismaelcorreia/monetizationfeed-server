"""
ArticleFetcher — wraps Crawl4AI (v0.3.x compatible).
Single responsibility: extract structured article data from a URL using AI-optimized crawling.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from urllib.parse import urljoin

from crawl4ai import AsyncWebCrawler
from config.logging_setup import get_logger

logger = get_logger("ingestion.article_fetcher")


@dataclass
class FetchedArticleData:
    url: str
    title: str
    text: str
    authors: list[str]
    summary: str
    top_image: Optional[str]
    images: list[str]
    publish_date: Optional[datetime]
    language: str
    keywords: list[str]


class ArticleFetcher:

    def __init__(self, language: str = "en", request_timeout: int = 30) -> None:
        self._language = language
        self._timeout = request_timeout

    def fetch(self, url: str) -> Optional[FetchedArticleData]:
        """Synchronous wrapper for async fetch."""
        try:
            # Garante que criamos um loop limpo para cada chamada síncrona
            # Isto evita erros de thread/loop persistentes em v0.3.x
            import asyncio
            return asyncio.run(self.fetch_async(url))
        except Exception as exc:
            logger.error("Failed to fetch %s synchronously: %s", url, exc)
            return None

    async def fetch_async(self, url: str) -> Optional[FetchedArticleData]:
        """Fetch article content using Crawl4AI v0.3.x."""
        async with AsyncWebCrawler() as crawler:
            # Na v0.3.x, passamos os parâmetros diretamente no arun
            result = await crawler.arun(
                url=url,
                bypass_cache=False,
                remove_overlay_elements=True, # Suportado via kwargs
                # Headless e outros são configurados internamente por defeito
            )

            if not result.success:
                logger.warning("Crawl4AI failed for %s: %s", url, result.error_message)
                return None

            metadata = result.metadata or {}
            
            # Extração de Data de Publicação
            publish_date = None
            date_str = (
                metadata.get("article:published_time") or 
                metadata.get("article:published") or 
                metadata.get("datePublished") or
                metadata.get("pubdate")
            )
            
            if date_str:
                try:
                    from dateutil import parser
                    publish_date = parser.parse(date_str)
                    if publish_date.tzinfo:
                        publish_date = publish_date.replace(tzinfo=None)
                except Exception:
                    logger.debug("Could not parse date: %s", date_str)

            return FetchedArticleData(
                url=url,
                title=metadata.get("title") or metadata.get("og:title") or "No Title",
                text=result.markdown or "",
                authors=[metadata.get("author")] if metadata.get("author") else [],
                summary=metadata.get("og:description") or "",
                top_image=metadata.get("og:image") or None,
                images=[],
                publish_date=publish_date,
                language=self._language,
                keywords=[]
            )

    def fetch_source_urls(self, source_url: str, limit: int = 30) -> list[str]:
        """Discover article URLs from a news site using Crawl4AI v0.3.x."""
        try:
            import asyncio
            return asyncio.run(self.fetch_source_urls_async(source_url, limit))
        except Exception as exc:
            logger.error("Failed to discover URLs from %s: %s", source_url, exc)
            return []

    async def fetch_source_urls_async(self, source_url: str, limit: int = 30) -> list[str]:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(
                url=source_url,
                remove_overlay_elements=True
            )
            
            if not result.success:
                return []

            urls = []
            # Na v0.3.73, os links estão no dicionário 'links'
            internal_links = result.links.get("internal", [])
            
            for link in internal_links:
                href = link.get("href", "")
                if any(x in href.lower() for x in ["/artigo", "/noticia", "/p/", "/2024/", "/2025/", "/news/"]):
                    urls.append(urljoin(source_url, href))
            
            unique_urls = list(dict.fromkeys(urls))[:limit]
            logger.info("Crawl4AI discovered %d URLs from %s", len(unique_urls), source_url)
            return unique_urls
