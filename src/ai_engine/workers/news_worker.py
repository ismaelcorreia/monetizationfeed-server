import asyncio
import json
from uuid import UUID
from ai_engine.dispatcher import AIDispatcher
from ai_engine.services.editorial_service import EditorialService
from ai_engine.models.pipeline_models import TaskType, JobStatus
from config.logging_setup import get_logger

logger = get_logger("ai_engine.workers")

class NewsWorker:
    def __init__(self, dispatcher: AIDispatcher, editorial_service: EditorialService):
        self.dispatcher = dispatcher
        self.editorial = editorial_service

    async def process_jobs(self, task_type: TaskType, limit: int = 5):  
        jobs = self.dispatcher.get_pending_jobs(task_type, limit)
        if not jobs:
            return

        logger.info(f"Worker starting {len(jobs)} jobs of type {task_type.value}")
        
        for job in jobs:
            try:
                # Marcar como em processamento
                self.dispatcher.update_job_status(job.id, JobStatus.PROCESSING)
                
                if task_type == TaskType.NORMALIZE:
                    await self._run_normalization(job)
                elif task_type == TaskType.ENRICH:
                    await self._run_enrichment(job)
                
                self.dispatcher.update_job_status(job.id, JobStatus.COMPLETED)
            except Exception as e:
                logger.error(f"Erro ao processar Job {job.id}: {str(e)}")
                self.dispatcher.update_job_status(job.id, JobStatus.ERROR, error=str(e))

    async def _run_normalization(self, job):
        # 1. Buscar dados raw (Simulado - idealmente via RawRepository)
        conn = self.dispatcher.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT title, raw_text FROM raw_articles WHERE id = %s", (job.target_id,))
                row = cur.fetchone()
                if not row: return
                title, text = row
                
                # 2. IA Normalization
                result = self.editorial.normalize(title, text)
                print(f"\n\n\nAI NORMALIZATION RESULT::: {result}\n\n\n")
                # 3. Guardar news_normalized
                cur.execute("""
                    INSERT INTO news_normalized (id, title, content, language, detected_topics, word_count, is_valid)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET 
                        title = EXCLUDED.title, content = EXCLUDED.content, 
                        is_valid = EXCLUDED.is_valid
                """, (job.target_id, result["title"], result["content"], result["language"], 
                      result["topics"], result["word_count"], result["is_valid"]))

                # Atualiza o status na tabela original para 'normalized'
                cur.execute("UPDATE raw_articles SET status = 'normalized' WHERE id = %s", (job.target_id,))
            conn.commit()
        finally:
            self.dispatcher.pool.putconn(conn)

    async def _run_enrichment(self, job):
        conn = self.dispatcher.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT title, content FROM news_normalized WHERE id = %s", (job.target_id,))
                row = cur.fetchone()
                if not row: return
                title, content = row
                
                # 1. IA Enrichment
                res = self.editorial.enrich(title, content)
                
                # 2. Guardar news_enriched
                cur.execute("""
                    INSERT INTO news_enriched (
                        id, summary_pt, editorial_title, keywords, entities, sentiment, 
                        relevance_score, impact_economic, impact_social, opportunities, risks, sector, region
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                """, (
                    job.target_id, res["summary_pt"], res["editorial_title"], res["keywords"],
                    json.dumps(res["entities"]), res["sentiment"], res["relevance_score"],
                    res["impact_economic"], res["impact_social"], res["opportunities"],
                    res["risks"], res["sector"], res["region"]
                ))
            conn.commit()
        finally:
            self.dispatcher.pool.putconn(conn)
