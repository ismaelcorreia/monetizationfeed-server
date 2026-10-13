"""
Database — connection pool, bootstrap, raw query helpers.
No ORM. Pure psycopg2 for sync operations; asyncpg pool for async paths.
Single responsibility: connectivity and schema initialisation.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import AsyncGenerator, Generator

import asyncpg
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

# Regista o adaptador de UUID para que o psycopg2 saiba lidar com o tipo UUID do Python
psycopg2.extras.register_uuid()

from config.logging_setup import get_logger
from config.settings import DatabaseConfig

logger = get_logger("storage.database")

# ── Sync pool (used by scheduler / bootstrap) ─────────────────────────────────

_sync_pool: ThreadedConnectionPool | None = None


def init_sync_pool(cfg: DatabaseConfig, minconn: int = 2, maxconn: int = 10) -> None:
    global _sync_pool
    _sync_pool = ThreadedConnectionPool(minconn, maxconn, dsn=cfg.sync_dsn)
    logger.info("Sync connection pool initialised (min=%d max=%d)", minconn, maxconn)


def get_sync_pool() -> ThreadedConnectionPool | None:
    return _sync_pool


@contextmanager
def sync_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    assert _sync_pool, "Sync pool not initialised — call init_sync_pool() first"
    conn = _sync_pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _sync_pool.putconn(conn)


@contextmanager
def sync_cursor(conn: psycopg2.extensions.connection):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        yield cur


# ── Async pool (used by AI agent pipeline) ────────────────────────────────────

_async_pool: asyncpg.Pool | None = None


async def init_async_pool(cfg: DatabaseConfig, min_size: int = 2, max_size: int = 10) -> None:
    global _async_pool
    _async_pool = await asyncpg.create_pool(
        dsn=cfg.dsn,
        min_size=min_size,
        max_size=max_size,
    )
    logger.info("Async connection pool initialised")


async def close_async_pool() -> None:
    if _async_pool:
        await _async_pool.close()
        logger.info("Async pool closed")


@asynccontextmanager
async def async_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    assert _async_pool, "Async pool not initialised — call init_async_pool() first"
    async with _async_pool.acquire() as conn:
        yield conn


# ── Schema bootstrap ──────────────────────────────────────────────────────────

def run_migrations(cfg: DatabaseConfig) -> None:
    """Execute *.sql files in migrations/ in order, tracking progress in the DB."""
    migrations_dir = Path(__file__).parent.parent / "migrations"
    if not migrations_dir.exists():
        logger.warning("Migrations directory not found: %s", migrations_dir)
        return

    sql_files = sorted(migrations_dir.glob("*.sql"))

    with sync_connection() as conn:
        with sync_cursor(conn) as cur:
            # 1. Garantir que a tabela de controle existe
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename VARCHAR(255) PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 2. Obter migrações já aplicadas
            cur.execute("SELECT filename FROM schema_migrations")
            applied = {row["filename"] for r in cur.fetchall() for row in [r]}
            # Fix: RealDictRow handle
            applied = {row["filename"] for row in cur.fetchall()} if not applied else applied
            # Simpler way to get the list
            cur.execute("SELECT filename FROM schema_migrations")
            applied = [r["filename"] for r in cur.fetchall()]

            # 3. Executar apenas as novas
            for sql_file in sql_files:
                if sql_file.name in applied:
                    logger.debug("Migration already applied: %s", sql_file.name)
                    continue

                logger.info("Applying migration: %s", sql_file.name)
                try:
                    cur.execute(sql_file.read_text())
                    cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (sql_file.name,))
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error("Failed to apply migration %s: %s", sql_file.name, e)
                    raise

    logger.info("Migration check complete")
