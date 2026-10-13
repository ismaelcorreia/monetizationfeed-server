-- Migration: Add Audio URLs for TTS
ALTER TABLE processed_articles ADD COLUMN IF NOT EXISTS audio_url TEXT;
ALTER TABLE comments ADD COLUMN IF NOT EXISTS audio_url TEXT;
