"""
IngestionPipeline — orchestrates the full ingestion flow for one source.
Single responsibility: coordinate fetcher → classifier → media → repository.
Does NOT call external AI. Does NOT know about scheduling.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from config.logging_setup import get_logger
from ingestion.article_fetcher import ArticleFetcher
from ingestion.language_detector import LanguageDetector
from ingestion.topic_classifier import TopicClassifier
from models.entities import ArticleStatus, NewsSource, RawArticle
from storage.article_repository import ArticleRepository
from storage.media_storage import MediaStorage
from storage.source_repository import SourceRepository

logger = get_logger("ingestion.pipeline")


@dataclass
class IngestionResult:
    source_url: str
    fetched: int = 0
    skipped: int = 0
    failed: int = 0


class IngestionPipeline:

    def __init__(
        self,
        fetcher: ArticleFetcher,
        detector: LanguageDetector,
        classifier: TopicClassifier,
        article_repo: ArticleRepository,
        source_repo: SourceRepository,
        media_storage: MediaStorage,
    ) -> None:
        self._fetcher = fetcher
        self._detector = detector
        self._classifier = classifier
        self._article_repo = article_repo
        self._source_repo = source_repo
        self._media = media_storage

    # ── Public entry point ────────────────────────────────────────────────────

    def ingest_source(self, source: NewsSource, keywords: list[str] = None) -> IngestionResult:
        result = IngestionResult(source_url=source.url)
        logger.info("Starting ingestion for source: %s (Filter: %s)", source.url, keywords)

        article_urls = self._fetcher.fetch_source_urls(source.url)

        for url in article_urls:
            outcome = self._process_one_url(url, source, keywords)
            if outcome == "fetched":
                result.fetched += 1
            elif outcome == "skipped":
                result.skipped += 1
            else:
                result.failed += 1

        self._source_repo.mark_fetched(source.id)
        logger.info(
            "Ingestion done for %s — fetched=%d skipped=%d failed=%d",
            source.url, result.fetched, result.skipped, result.failed,
        )
        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    def _process_one_url(self, url: str, source: NewsSource, keywords: list[str] = None) -> str:
        if self._article_repo.url_exists(url):
            return "skipped"

        data = self._fetcher.fetch(url)
        if not data or not data.text.strip():
            return "failed"

        # --- Filtro de Palavras-Chave (Interesse específico) ---
        title_text = f"{data.title} {data.text}".lower()
        if keywords:
            match = any(k.lower() in title_text for k in keywords)
            if not match:
                logger.debug("Artigo ignorado (não contém palavras-chave): %s", url)
                return "skipped"

        # --- Inteligência e Qualidade ---
        # 1. Filtro de Extensão (mínimo 500 caracteres para ser considerado um artigo real)
        text_content = data.text.strip()
        word_count = len(text_content.split())
        if len(text_content) < 500 or word_count < 80:
            logger.info("Artigo ignorado por ser demasiado curto: %s (%d chars)", url, len(text_content))
            return "skipped"

        # 2. Detecção de Idioma e Tópico
        language = self._detector.detect(text_content)
        topic = self._classifier.classify(data.title, text_content, data.keywords)
        
        # 3. Detecção de País (Infre a partir do locale da fonte, ex: pt-AO -> AO)
        country = source.locale.split('-')[-1].upper() if '-' in source.locale else "unknown"

        # 4. Filtro de Recência (Obrigatório ter data e ser dos últimos 7 dias)
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        if not data.publish_date:
            logger.info("Artigo ignorado (sem data de publicação): %s", url)
            return "skipped"
        
        # Garante que publish_date não tem timezone para comparação se necessário,
        # ou lida com offset-aware datetimes.
        pub_date = data.publish_date.replace(tzinfo=None) if data.publish_date.tzinfo else data.publish_date
        if pub_date < (now - timedelta(days=7)) or pub_date > now:
            logger.info("Artigo ignorado por ser antigo ou futuro: %s (%s)", url, pub_date)
            return "skipped"

        article = RawArticle(
            source_id=source.id,
            url=url,
            title=data.title,
            raw_text=text_content,
            topic=topic,
            language_detected=language,
            data_publicada=pub_date,
            country=country,
            word_count=word_count,
            authors=data.authors,
            summary=data.summary,
        )

        media_keys = self._download_media(article.id, data.top_image, data.images)
        article.media_keys = media_keys

        self._article_repo.insert_raw_article(article)
        return "fetched"

    def _download_media(
        self, article_id: UUID, top_image: str | None, images: list[str]
    ) -> list[str]:
        keys: list[str] = []
        candidates = []
        
        # Filtro de inteligência para imagens (evitar logos, ícones, trackers)
        def is_real_image(url: str) -> bool:
            garbage = ["logo", "icon", "placeholder", "avatar", "ads", "pixel", "banner"]
            url_lower = url.lower()
            return not any(g in url_lower for g in garbage)

        if top_image and is_real_image(top_image):
            candidates.append(top_image)

        # limit additional images to avoid abuse
        for img_url in images[:6]:
            if img_url not in candidates and is_real_image(img_url):
                candidates.append(img_url)

        for media_url in candidates:
            key = self._media.upload_media_from_url(article_id, media_url)
            if key:
                keys.append(key)

        return keys
