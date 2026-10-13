"""
SourceRepository — all DB operations for news_sources and discovered_sources.
Single responsibility: persistence of source entities.
"""
from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

import psycopg2

from config.logging_setup import get_logger
from models.entities import DiscoveredSource, NewsSource, SourceStatus, SourceType
from storage.database import sync_connection, sync_cursor

logger = get_logger("storage.source_repository")


class SourceRepository:

    # ── news_sources ──────────────────────────────────────────────────────────

    def get_active_sources(self) -> list[NewsSource]:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM news_sources WHERE status = %s ORDER BY last_fetched_at ASC NULLS FIRST",
                    (SourceStatus.ACTIVE.value,),
                )
                return [self._row_to_source(r) for r in cur.fetchall()]

    def upsert_source(self, source: NewsSource) -> None:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute(
                    """
                    INSERT INTO news_sources
                        (id, url, name, source_type, locale, topic_category,
                         status, reliability_score, app_hint, discovered_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (url) DO UPDATE SET
                        name             = EXCLUDED.name,
                        source_type      = EXCLUDED.source_type,
                        locale           = EXCLUDED.locale,
                        topic_category   = EXCLUDED.topic_category,
                        status           = EXCLUDED.status,
                        reliability_score = EXCLUDED.reliability_score,
                        app_hint         = EXCLUDED.app_hint
                    """,
                    (
                        str(source.id), source.url, source.name,
                        source.source_type.value, source.locale,
                        source.topic_category, source.status.value,
                        source.reliability_score, source.app_hint,
                        source.discovered_at,
                    ),
                )

    def mark_fetched(self, source_id: UUID) -> None:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute(
                    "UPDATE news_sources SET last_fetched_at = now() WHERE id = %s",
                    (str(source_id),),
                )

    def get_source_by_url(self, url: str) -> Optional[NewsSource]:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute("SELECT * FROM news_sources WHERE url = %s", (url,))
                row = cur.fetchone()
                return self._row_to_source(row) if row else None

    def get_all_sources(self, limit: int = 100, offset: int = 0, topic: str = None) -> list[NewsSource]:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                query = "SELECT * FROM news_sources"
                params = []
                if topic:
                    query += " WHERE topic_category = %s"
                    params.append(topic)
                
                query += " ORDER BY name ASC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                
                cur.execute(query, tuple(params))
                return [self._row_to_source(r) for r in cur.fetchall()]

    def delete_source(self, source_id: UUID) -> bool:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute("DELETE FROM news_sources WHERE id = %s", (str(source_id),))
                return cur.rowcount > 0

    # ── discovered_sources ────────────────────────────────────────────────────

    def upsert_discovered(self, ds: DiscoveredSource) -> None:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute(
                    """
                    INSERT INTO discovered_sources
                        (id, url, name, topic_category, locale, source_type, app_hint, discovered_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (url) DO NOTHING
                    """,
                    (
                        str(ds.id), ds.url, ds.name, ds.topic_category,
                        ds.locale, ds.source_type.value, ds.app_hint, ds.discovered_at,
                    ),
                )

    def get_unpromoted_discovered(self) -> list[DiscoveredSource]:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM discovered_sources WHERE promoted = FALSE ORDER BY discovered_at DESC"
                )
                return [self._row_to_discovered(r) for r in cur.fetchall()]

    def mark_promoted(self, ds_id: UUID) -> None:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute(
                    "UPDATE discovered_sources SET promoted = TRUE WHERE id = %s",
                    (str(ds_id),),
                )

    def get_all_discovered(self, limit: int = 100, offset: int = 0) -> list[DiscoveredSource]:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute(
                    "SELECT * FROM discovered_sources ORDER BY discovered_at DESC LIMIT %s OFFSET %s",
                    (limit, offset),
                )
                return [self._row_to_discovered(r) for r in cur.fetchall()]

    def delete_discovered(self, ds_id: UUID) -> bool:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute("DELETE FROM discovered_sources WHERE id = %s", (str(ds_id),))
                return cur.rowcount > 0

    # ── Mapping helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _row_to_source(row: dict) -> NewsSource:
        s = NewsSource(
            url=row["url"],
            name=row["name"],
            source_type=SourceType(row["source_type"]),
            locale=row["locale"],
            topic_category=row["topic_category"],
        )
        s.id = UUID(str(row["id"]))
        s.status = SourceStatus(row["status"])
        s.reliability_score = float(row["reliability_score"])
        s.app_hint = row.get("app_hint")
        s.discovered_at = row["discovered_at"]
        s.last_fetched_at = row.get("last_fetched_at")
        return s

    @staticmethod
    def _row_to_discovered(row: dict) -> DiscoveredSource:
        ds = DiscoveredSource(
            url=row["url"],
            name=row["name"],
            topic_category=row["topic_category"],
            locale=row["locale"],
        )
        ds.id = UUID(str(row["id"]))
        ds.source_type = SourceType(row["source_type"])
        ds.app_hint = row.get("app_hint")
        ds.discovered_at = row["discovered_at"]
        ds.promoted = row["promoted"]
        return ds
