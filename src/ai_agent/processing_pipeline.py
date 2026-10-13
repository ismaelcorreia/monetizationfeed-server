"""
ProcessingPipeline — async loop that drains the pending article queue.
Single responsibility: coordinate article_repo ↔ processor ↔ persist result.
Runs one article at a time, marks status appropriately.
"""
from __future__ import annotations

import asyncio

from config.logging_setup import get_logger
from ai_agent.article_processor import ArticleProcessor
from models.entities import ArticleStatus
from storage.article_repository import ArticleRepository

logger = get_logger("ai_agent.processing_pipeline")


class ProcessingPipeline:

    def __init__(
        self,
        processor: ArticleProcessor,
        article_repo: ArticleRepository,
        tts_service=None,
        pause_between_articles: float = 1.0,
    ) -> None:
        self._processor = processor
        self._repo = article_repo
        self._tts_service = tts_service
        self._pause = pause_between_articles

    async def run_once(self, limit: int = 1) -> int:
        """
        Process pending articles, up to `limit` at a time.
        Returns the number successfully processed.
        """
        published = 0

        while published < limit:
            article = await self._repo.get_next_pending()
            if article is None:
                logger.info("No more pending articles — processing cycle complete")
                break

            logger.info("Processing article: %s | %s", article.id, article.title[:60])

            processed = self._processor.process(article)

            if processed is None:
                await self._repo.async_update_raw_status(article.id, ArticleStatus.FAILED)
                logger.warning("Article %s marked as FAILED", article.id)
            else:
                # Gerar áudio se o TTSService estiver disponível
                if self._tts_service:
                    try:
                        audio_url = self._tts_service.generate_audio(processed.body_pt, prefix=f"post_{article.id}")
                        processed.audio_url = audio_url
                        logger.info(f"Áudio gerado com sucesso: {audio_url}")
                    except Exception as e:
                        logger.error(f"Erro ao gerar áudio para o post {article.id}: {e}")

                await self._repo.insert_processed(processed)
                await self._repo.async_update_raw_status(article.id, ArticleStatus.PROCESSED)
                published += 1
                logger.info(
                    "Article %s published — words=%d read=%.1fmin",
                    article.id, processed.word_count, processed.reading_time_minutes,
                )

            await asyncio.sleep(self._pause)

        return published

    async def run_continuous(self, interval_seconds: int = 300) -> None:
        """
        Long-running loop — polls for pending articles every interval_seconds.
        Intended for use as a background service.
        """
        logger.info("Starting continuous processing loop (interval=%ds)", interval_seconds)
        while True:
            try:
                count = await self.run_once()
                if count:
                    logger.info("Cycle done — %d articles published", count)
            except Exception as exc:
                logger.error("Processing cycle error: %s", exc)

            await asyncio.sleep(interval_seconds)
