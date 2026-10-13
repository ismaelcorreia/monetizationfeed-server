-- Renomeia o campo apenas se o antigo ainda existir
DO $$ 
BEGIN 
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='raw_articles' AND column_name='published_at') THEN
        ALTER TABLE raw_articles RENAME COLUMN published_at TO data_publicada;
    END IF;
END $$;
