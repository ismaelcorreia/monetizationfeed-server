-- Adiciona campos apenas se não existirem
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='raw_articles' AND column_name='country') THEN
        ALTER TABLE raw_articles ADD COLUMN country varchar(10) DEFAULT 'unknown';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='raw_articles' AND column_name='word_count') THEN
        ALTER TABLE raw_articles ADD COLUMN word_count integer DEFAULT 0;
    END IF;
END $$;

-- Índice (o Postgres não tem 'IF NOT EXISTS' direto para índices em todas as versões, mas podemos usar este truque)
CREATE INDEX IF NOT EXISTS idx_raw_country_topic ON raw_articles(country, topic);
