from typing import List, Optional
import httpx
from uuid import UUID

from config.logging_setup import get_logger
from config.settings import AIConfig

logger = get_logger("ai_engine.vector")


class VectorService:
    def __init__(self, db_pool, cfg: AIConfig, model: str | None = None):
        self.pool = db_pool
        self.cfg = cfg
        self.model = model or cfg.model or "nomic-embed-text"

        if getattr(cfg, "provider", "ollama") == "openrouter":
            self.endpoint = f"{cfg.openrouter_base_url.rstrip('/')}/v1/embeddings"
            self.headers = {"Authorization": f"Bearer {cfg.openrouter_api_key}", "Content-Type": "application/json"}
            # OpenRouter embedding model ids might differ; caller can override model param
        else:
            # Ollama local embeddings
            self.endpoint = f"{cfg.ollama_base_url.rstrip('/')}/api/embeddings"
            self.headers = None

    async def generate_embedding(self, text: str) -> List[float]:
        """Gera um vetor (embedding) a partir de um texto via provider configurado."""
        if getattr(self.cfg, "provider", "ollama") == "openrouter":
            payload = {"model": self.model, "input": text}
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(self.endpoint, json=payload, headers=self.headers)
                resp.raise_for_status()
                j = resp.json()
                # OpenRouter/compatible responses often have data[0].embedding
                if "data" in j and isinstance(j["data"], list) and len(j["data"]) > 0:
                    return j["data"][0].get("embedding")
                # Some providers return embedding directly
                if "embedding" in j:
                    return j["embedding"]
                raise ValueError("Unexpected embedding response format")

        else:
            payload = {"model": self.model, "prompt": text}
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(self.endpoint, json=payload)
                response.raise_for_status()
                return response.json()["embedding"]

    def save_embedding(self, article_id: UUID, embedding: List[float]):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO news_embeddings (id, embedding)
                    VALUES (%s, %s)
                    ON CONFLICT (id) DO UPDATE SET embedding = EXCLUDED.embedding
                """, (article_id, embedding))
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def find_similar(self, embedding: List[float], threshold: float = 0.8, limit: int = 10):
        """Usa a similaridade de cosseno do pgvector para encontrar notícias relacionadas."""
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                # O operador <=> no pgvector é para distância de cosseno
                cur.execute("""
                    SELECT id, (1 - (embedding <=> %s::vector)) as similarity
                    FROM news_embeddings
                    WHERE (1 - (embedding <=> %s::vector)) > %s
                    ORDER BY similarity DESC
                    LIMIT %s
                """, (embedding, embedding, threshold, limit))
                return cur.fetchall()
        finally:
            self.pool.putconn(conn)
