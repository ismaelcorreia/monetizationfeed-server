-- Migration: Post Scheduling and Comments Support

-- Add scheduling columns to processed_articles if not already present
ALTER TABLE processed_articles ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ;
ALTER TABLE processed_articles ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;

-- Ensure existing published articles have published_at set
UPDATE processed_articles SET published_at = processed_at WHERE status = 'published' AND published_at IS NULL;

-- Create users table for persistent authentication
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Create comments table
CREATE TABLE IF NOT EXISTS comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES processed_articles(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES comments(id) ON DELETE CASCADE,
    author TEXT NOT NULL,
    avatar TEXT,
    content TEXT NOT NULL,
    is_ai BOOLEAN DEFAULT FALSE,
    is_audio BOOLEAN DEFAULT FALSE,
    audio_duration TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for querying comments by post
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
