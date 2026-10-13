-- Habilita a extensão de vetores para clustering semântico
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Controlo de Tarefas de IA (AI Jobs)
CREATE TYPE job_status AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'ERROR');

CREATE TABLE ai_jobs (
    id UUID PRIMARY KEY,
    task_type VARCHAR(50) NOT NULL, -- 'normalize', 'enrich', 'cluster', etc.
    target_id UUID NOT NULL,        -- ID do artigo ou cluster alvo
    status job_status DEFAULT 'PENDING',
    priority INTEGER DEFAULT 0,
    retries INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT,
    execution_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Camada: News Normalized (Dados limpos e estruturados)
CREATE TABLE news_normalized (
    id UUID PRIMARY KEY REFERENCES raw_articles(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    language VARCHAR(10),
    detected_topics TEXT[],
    word_count INTEGER,
    is_valid BOOLEAN DEFAULT TRUE,
    is_duplicate BOOLEAN DEFAULT FALSE,
    canonical_url TEXT,
    normalized_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Camada: News Enriched (IA Enrichment)
CREATE TABLE news_enriched (
    id UUID PRIMARY KEY REFERENCES news_normalized(id) ON DELETE CASCADE,
    summary_pt TEXT,
    enriched_content TEXT,
    editorial_title TEXT,
    keywords TEXT[],
    entities JSONB, -- Pessoas, Organizações, Lugares
    stakeholders JSONB, -- Pessoas, Organizações, Lugares
    sentiment VARCHAR(20),
    relevance_score FLOAT,
    insights TEXT[],
    impact_economic TEXT,
    impact_social TEXT,
    opportunities TEXT,
    risks TEXT,
    sector VARCHAR(100),
    region VARCHAR(100),
    country VARCHAR(100),
    enriched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Camada: Embeddings e Vectors
CREATE TABLE news_embeddings (
    id UUID PRIMARY KEY REFERENCES news_normalized(id) ON DELETE CASCADE,
    embedding vector(768), -- Dimensão para modelos comuns (ajustável)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Camada: semantic Clusters
CREATE TABLE news_clusters (
    id UUID PRIMARY KEY,
    topic_label TEXT,
    representative_title TEXT,
    article_ids UUID[],
    insight_summary TEXT,
    trend_status VARCHAR(20) DEFAULT 'STABLE', -- 'EMERGING', 'HOT', 'FADING'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Camada Final: Posts (Prontos para publicação)
CREATE TYPE editorial_status AS ENUM ('DRAFT', 'READY', 'PUBLISHED', 'ARCHIVED');

CREATE TABLE posts (
    id UUID PRIMARY KEY,
    cluster_id UUID REFERENCES news_clusters(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    subtitle TEXT,
    body TEXT NOT NULL,
    summary TEXT,
    keywords TEXT[],
    insights JSONB,
    author_original TEXT,
    source_url TEXT,
    related_sources TEXT[],
    media_keys TEXT[], -- Chaves do MinIO
    status editorial_status DEFAULT 'DRAFT',
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices para performance
CREATE INDEX idx_ai_jobs_status_priority ON ai_jobs(status, priority);
CREATE INDEX idx_news_normalized_valid ON news_normalized(is_valid, is_duplicate);
CREATE INDEX idx_posts_status ON posts(status);
