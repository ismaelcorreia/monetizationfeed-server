"""
ArticleRepository — all DB operations for raw_articles and processed_articles.
Single responsibility: persistence of article entities.
"""
from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

from config.logging_setup import get_logger
from models.entities import ArticleStatus, ProcessedArticle, RawArticle
from storage.database import async_connection, sync_connection, sync_cursor

logger = get_logger("storage.article_repository")


class ArticleRepository:

    # ── raw_articles — sync writes (ingestion pipeline) ───────────────────────

    def insert_raw_article(self, article: RawArticle) -> None:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute(
                    """
                    INSERT INTO raw_articles
                        (id, source_id, url, title, raw_text, topic,
                         language_detected, authors, summary, media_keys,
                         status, data_publicada, fetched_at, country, word_count)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (url) DO NOTHING
                    """,
                    (
                        str(article.id), str(article.source_id),
                        article.url, article.title, article.raw_text,
                        article.topic, article.language_detected,
                        json.dumps(article.authors),
                        article.summary,
                        json.dumps(article.media_keys),
                        article.status.value,
                        article.data_publicada,
                        article.fetched_at,
                        article.country,
                        article.word_count
                    ),
                )

    def update_raw_status(self, article_id: UUID, status: ArticleStatus) -> None:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute(
                    "UPDATE raw_articles SET status = %s WHERE id = %s",
                    (status.value, str(article_id)),
                )

    def url_exists(self, url: str) -> bool:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute("SELECT 1 FROM raw_articles WHERE url = %s", (url,))
                return cur.fetchone() is not None

    def get_all_raw_articles(
        self, 
        limit: int = 50, 
        offset: int = 0,
        topic: str = None,
        country: str = None,
        language: str = None
    ) -> list[RawArticle]:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                query = "SELECT * FROM raw_articles WHERE 1=1"
                params = []
                
                if topic:
                    query += " AND topic = %s"
                    params.append(topic)
                if country:
                    query += " AND country = %s"
                    params.append(country)
                if language:
                    query += " AND language_detected = %s"
                    params.append(language)
                    
                query += " ORDER BY fetched_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                
                cur.execute(query, tuple(params))
                return [self._row_to_raw(dict(r)) for r in cur.fetchall()]

    def delete_article(self, article_id: UUID) -> bool:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                # CASCADE handles deleting processed_articles automatically
                cur.execute("DELETE FROM raw_articles WHERE id = %s", (str(article_id),))
                return cur.rowcount > 0

    # ── raw_articles — async reads (AI pipeline) ──────────────────────────────

    async def get_next_pending(self) -> Optional[RawArticle]:
        """Fetch ONE pending article — enables one-at-a-time AI processing."""
        async with async_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM raw_articles
                WHERE status = $1
                ORDER BY fetched_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
                ArticleStatus.PENDING.value,
            )
            return self._row_to_raw(dict(row)) if row else None

    async def async_update_raw_status(self, article_id: UUID, status: ArticleStatus) -> None:
        async with async_connection() as conn:
            await conn.execute(
                "UPDATE raw_articles SET status = $1 WHERE id = $2",
                status.value, str(article_id),
            )

    # ── processed_articles ────────────────────────────────────────────────────

    async def insert_processed(self, processed: ProcessedArticle) -> None:
        async with async_connection() as conn:
            # Estratégia de agendamento: Adicionar um gap de horas desde o último post
            row = await conn.fetchrow("""
                SELECT COALESCE(MAX(scheduled_at), MAX(published_at), NOW()) as last_date
                FROM processed_articles
            """)
            
            import datetime
            last_date = row["last_date"] if row and row["last_date"] else datetime.datetime.now(datetime.timezone.utc)
            
            # Assegurar timezone e impedir agendamento retroativo
            now = datetime.datetime.now(datetime.timezone.utc)
            if last_date.tzinfo is None:
                last_date = last_date.replace(tzinfo=datetime.timezone.utc)
            if last_date < now:
                last_date = now
                
            # Gap estratégico de 4 horas
            scheduled_at = last_date + datetime.timedelta(hours=4)

            await conn.execute(
                """
                INSERT INTO processed_articles
                    (id, raw_article_id, title_pt, body_pt, topic,
                     persuasion_hooks, word_count, reading_time_minutes,
                     status, processed_at, scheduled_at, published_at, audio_url)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                """,
                str(processed.id),
                str(processed.raw_article_id),
                processed.title_pt,
                processed.body_pt,
                processed.topic,
                json.dumps(processed.persuasion_hooks),
                processed.word_count,
                processed.reading_time_minutes,
                "processed", # Fica como 'processed' até o scheduler de publicação atuar
                processed.processed_at,
                scheduled_at,
                None, 
                processed.audio_url
            )

            # Gravar os insights analíticos profundos na tabela news_enriched, se houver metadata
            if processed.metadata:
                m = processed.metadata
                await conn.execute(
                    """
                    INSERT INTO news_enriched (
                        id, summary_pt, editorial_title, keywords, entities, sentiment, 
                        relevance_score, impact_economic, impact_social, opportunities, risks, sector, region
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    str(processed.raw_article_id),
                    m.get("summary_pt"),
                    processed.title_pt,
                    m.get("keywords", []),
                    json.dumps(m.get("entities", {})),
                    m.get("sentiment"),
                    m.get("relevance_score"),
                    m.get("impact_economic"),
                    m.get("impact_social"),
                    m.get("opportunities"),
                    m.get("risks"),
                    m.get("sector"),
                    m.get("region")
                )

    def get_published_articles(
        self, 
        limit: int = 50, 
        offset: int = 0,
        topic: str = None,
        country: str = None,
        language: str = None
    ) -> list[dict]:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                query = """
                    SELECT p.*, r.url, r.media_keys, r.source_id, r.country, r.language_detected
                    FROM processed_articles p
                    JOIN raw_articles r ON r.id = p.raw_article_id
                    WHERE p.status = 'published'
                """
                params = []
                
                if topic:
                    query += " AND r.topic = %s"
                    params.append(topic)
                if country:
                    query += " AND r.country = %s"
                    params.append(country)
                if language:
                    query += " AND r.language_detected = %s"
                    params.append(language)
                    
                query += " ORDER BY p.processed_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                
                cur.execute(query, tuple(params))
                return [dict(r) for r in cur.fetchall()]

    # ── ingestion_log ─────────────────────────────────────────────────────────

    def log_ingestion_run(
        self,
        run_type: str,
        fetched: int,
        failed: int,
        error_detail: Optional[str] = None,
    ) -> None:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute(
                    """
                    INSERT INTO ingestion_log
                        (run_type, finished_at, articles_fetched, articles_failed, error_detail)
                    VALUES (%s, now(), %s, %s, %s)
                    """,
                    (run_type, fetched, failed, error_detail),
                )

    # ── Mapping ───────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_raw(row: dict) -> RawArticle:
        a = RawArticle(
            source_id=UUID(str(row["source_id"])),
            url=row["url"],
            title=row["title"],
            raw_text=row["raw_text"],
            topic=row["topic"],
            language_detected=row["language_detected"],
            data_publicada=row.get("data_publicada"),
            country=row.get("country", "unknown"),
            word_count=row.get("word_count", 0),
        )
        a.id = UUID(str(row["id"]))
        a.status = ArticleStatus(row["status"])
        a.fetched_at = row["fetched_at"]
        a.media_keys = json.loads(row["media_keys"]) if isinstance(row["media_keys"], str) else row["media_keys"] or []
        a.authors = json.loads(row["authors"]) if isinstance(row["authors"], str) else row["authors"] or []
        a.summary = row.get("summary")
        return a

    def get_published_posts_for_frontend(
        self,
        limit: int = 10,
        offset: int = 0,
        topic: Optional[str] = None,
    ) -> list[dict]:
        """
        Busca RawArticles e ProcessedArticles com status PUBLISHED,
        formatados para consumo pelo frontend.
        """
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                query = """
                    SELECT
                        ra.id as raw_article_id,
                        ra.source_id,
                        ra.url,
                        ra.title,
                        ra.raw_text,
                        ra.topic as raw_topic,
                        ra.language_detected,
                        ra.data_publicada,
                        ra.country,
                        ra.word_count,
                        ra.summary,
                        ra.media_keys,
                        ra.authors,
                        pa.id as processed_article_id,
                        pa.title_pt,
                        pa.body_pt,
                        pa.topic as processed_topic,
                        pa.persuasion_hooks,
                        pa.processed_at,
                        pa.reading_time_minutes,
                        pa.word_count as processed_word_count,
                        pa.audio_url
                    FROM processed_articles pa
                    JOIN raw_articles ra ON pa.raw_article_id = ra.id
                    WHERE pa.status = %s
                """
                params = [ArticleStatus.PUBLISHED.value]
                
                if topic:
                    query += " AND pa.topic ILIKE %s"
                    params.append(f"%{topic}%")

                query += " ORDER BY pa.processed_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])

                cur.execute(query, tuple(params))
                results = []
                for row in cur.fetchall():
                    # Mapear colunas para RawArticle e ProcessedArticle
                    # Ajustar conforme as colunas reais retornadas
                    raw_article_data = {
                        "id": row["raw_article_id"],
                        "source_id": row["source_id"],
                        "url": row["url"],
                        "title": row["title"],
                        "raw_text": row["raw_text"],
                        "topic": row["raw_topic"],
                        "language_detected": row["language_detected"],
                        "data_publicada": row["data_publicada"],
                        "country": row["country"],
                        "word_count": row["word_count"],
                        "summary": row["summary"],
                        "media_keys": json.loads(row["media_keys"]) if isinstance(row.get("media_keys"), str) else (row.get("media_keys") or []),
                        "authors": json.loads(row["authors"]) if isinstance(row.get("authors"), str) else (row.get("authors") or []),
                    }
                    processed_article_data = {
                        "id": row["processed_article_id"],
                        "raw_article_id": row["raw_article_id"],
                        "title_pt": row["title_pt"],
                        "body_pt": row["body_pt"],
                        "topic": row["processed_topic"],
                        "persuasion_hooks": json.loads(row["persuasion_hooks"]) if isinstance(row.get("persuasion_hooks"), str) else (row.get("persuasion_hooks") or []),
                        "processed_at": row["processed_at"],
                        "reading_time_minutes": row["reading_time_minutes"],
                        "word_count": row["processed_word_count"],
                        "audio_url": row.get("audio_url"),
                    }
                    results.append({
                        "raw_article": raw_article_data,
                        "processed_article": processed_article_data
                    })
                return results

    def get_single_published_post_for_frontend(self, post_id: UUID) -> Optional[dict]:
        """
        Busca um único RawArticle e ProcessedArticle com status PUBLISHED por post_id,
        formatado para consumo pelo frontend (detalhe).
        """
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                query = """
                    SELECT
                        ra.id as raw_article_id,
                        ra.source_id,
                        ra.url,
                        ra.title,
                        ra.raw_text,
                        ra.topic as raw_topic,
                        ra.language_detected,
                        ra.data_publicada,
                        ra.country,
                        ra.word_count,
                        ra.summary,
                        ra.media_keys,
                        ra.authors,
                        pa.id as processed_article_id,
                        pa.title_pt,
                        pa.body_pt,
                        pa.topic as processed_topic,
                        pa.persuasion_hooks,
                        pa.processed_at,
                        pa.reading_time_minutes,
                        pa.word_count as processed_word_count,
                        pa.audio_url
                    FROM processed_articles pa
                    JOIN raw_articles ra ON pa.raw_article_id = ra.id
                    WHERE pa.id = %s AND pa.status = %s
                """
                cur.execute(query, (str(post_id), ArticleStatus.PUBLISHED.value))
                row = cur.fetchone()
                if not row:
                    return None
                 # Mapear colunas para RawArticle e ProcessedArticle
                raw_article_data = {
                    "id": row["raw_article_id"],
                    "source_id": row["source_id"],
                    "url": row["url"],
                    "title": row["title"],
                    "raw_text": row["raw_text"],
                    "topic": row["raw_topic"],
                    "language_detected": row["language_detected"],
                    "data_publicada": row["data_publicada"],
                    "country": row["country"],
                    "word_count": row["word_count"],
                    "summary": row["summary"],
                    "media_keys": json.loads(row["media_keys"]) if isinstance(row.get("media_keys"), str) else (row.get("media_keys") or []),
                    "authors": json.loads(row["authors"]) if isinstance(row.get("authors"), str) else (row.get("authors") or []),
                }
                processed_article_data = {
                    "id": row["processed_article_id"],
                    "raw_article_id": row["raw_article_id"],
                    "title_pt": row["title_pt"],
                    "body_pt": row["body_pt"],
                    "topic": row["processed_topic"],
                    "persuasion_hooks": json.loads(row["persuasion_hooks"]) if isinstance(row.get("persuasion_hooks"), str) else (row.get("persuasion_hooks") or []),
                    "processed_at": row["processed_at"],
                    "reading_time_minutes": row["reading_time_minutes"],
                    "word_count": row["processed_word_count"],
                    "audio_url": row.get("audio_url"),
                }
                return {
                    "raw_article": raw_article_data,
                    "processed_article": processed_article_data
                }
