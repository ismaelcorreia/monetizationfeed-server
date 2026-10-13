-- ============================================================
-- 001 — Initial schema
-- Run once at startup via storage/db_bootstrap.py
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── news_sources ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS news_sources (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url              TEXT NOT NULL UNIQUE,
    name             TEXT NOT NULL,
    source_type      TEXT NOT NULL DEFAULT 'newspaper',
    locale           TEXT NOT NULL DEFAULT 'en-US',
    topic_category   TEXT NOT NULL DEFAULT 'general',
    status           TEXT NOT NULL DEFAULT 'active',
    reliability_score NUMERIC(3,2) NOT NULL DEFAULT 1.0,
    app_hint         TEXT,
    discovered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_fetched_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_news_sources_status ON news_sources(status);
CREATE INDEX IF NOT EXISTS idx_news_sources_topic  ON news_sources(topic_category);

-- ── raw_articles ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw_articles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           UUID NOT NULL REFERENCES news_sources(id) ON DELETE CASCADE,
    url                 TEXT NOT NULL UNIQUE,
    title               TEXT NOT NULL,
    raw_text            TEXT NOT NULL,
    topic               TEXT NOT NULL DEFAULT 'general',
    language_detected   TEXT NOT NULL DEFAULT 'en',
    authors             JSONB NOT NULL DEFAULT '[]',
    summary             TEXT,
    media_keys          JSONB NOT NULL DEFAULT '[]',   -- MinIO object keys
    status              TEXT NOT NULL DEFAULT 'pending',
    published_at        TIMESTAMPTZ,
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_raw_articles_status    ON raw_articles(status);
CREATE INDEX IF NOT EXISTS idx_raw_articles_source    ON raw_articles(source_id);
CREATE INDEX IF NOT EXISTS idx_raw_articles_fetched   ON raw_articles(fetched_at DESC);

-- ── processed_articles ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS processed_articles (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_article_id       UUID NOT NULL REFERENCES raw_articles(id) ON DELETE CASCADE,
    title_pt             TEXT NOT NULL,
    body_pt              TEXT NOT NULL,
    topic                TEXT NOT NULL DEFAULT 'general',
    persuasion_hooks     JSONB NOT NULL DEFAULT '[]',
    word_count           INTEGER NOT NULL DEFAULT 0,
    reading_time_minutes NUMERIC(5,2) NOT NULL DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'published',
    processed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_processed_status     ON processed_articles(status);
CREATE INDEX IF NOT EXISTS idx_processed_raw        ON processed_articles(raw_article_id);
CREATE INDEX IF NOT EXISTS idx_processed_topic      ON processed_articles(topic);
CREATE INDEX IF NOT EXISTS idx_processed_at         ON processed_articles(processed_at DESC);

-- ── discovered_sources ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS discovered_sources (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url              TEXT NOT NULL UNIQUE,
    name             TEXT NOT NULL,
    topic_category   TEXT NOT NULL DEFAULT 'general',
    locale           TEXT NOT NULL DEFAULT 'en-US',
    source_type      TEXT NOT NULL DEFAULT 'discovered',
    app_hint         TEXT,
    promoted         BOOLEAN NOT NULL DEFAULT FALSE,
    discovered_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_discovered_promoted ON discovered_sources(promoted);
CREATE INDEX IF NOT EXISTS idx_discovered_topic    ON discovered_sources(topic_category);

-- ── ingestion_log ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ingestion_log (
    id           BIGSERIAL PRIMARY KEY,
    run_type     TEXT NOT NULL,   -- 'scheduled' | 'manual'
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    articles_fetched   INTEGER NOT NULL DEFAULT 0,
    articles_failed    INTEGER NOT NULL DEFAULT 0,
    error_detail TEXT
);
