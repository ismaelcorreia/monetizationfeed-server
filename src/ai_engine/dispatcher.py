from uuid import UUID, uuid4
from datetime import datetime
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

from ai_engine.models.pipeline_models import AIJob, JobStatus, TaskType
from config.logging_setup import get_logger

logger = get_logger("ai_engine.dispatcher")

class AIDispatcher:
    def __init__(self, db_pool):
        self.pool = db_pool

    def _get_conn(self):
        return self.pool.getconn()

    def _put_conn(self, conn):
        self.pool.putconn(conn)

    # ── Job Management ────────────────────────────────────────────────────────

    def create_job(self, task_type: TaskType, target_id: UUID, priority: int = 0) -> AIJob:
        job = AIJob(task_type=task_type, target_id=target_id, priority=priority)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO ai_jobs (id, task_type, target_id, status, priority)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (target_id, task_type) WHERE status != 'COMPLETED' DO NOTHING
                """, (job.id, job.task_type.value, job.target_id, job.status.value, job.priority))
            conn.commit()
            return job
        finally:
            self._put_conn(conn)

    def get_pending_jobs(self, task_type: Optional[TaskType] = None, limit: int = 10) -> List[AIJob]:
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT * FROM ai_jobs WHERE status = 'PENDING'"
                params = []
                if task_type:
                    query += " AND task_type = %s"
                    params.append(task_type.value)
                query += " ORDER BY priority DESC, created_at ASC LIMIT %s"
                params.append(limit)
                
                cur.execute(query, params)
                rows = cur.fetchall()
                return [AIJob(
                    id=r["id"],
                    task_type=TaskType(r["task_type"]),
                    target_id=r["target_id"],
                    status=JobStatus(r["status"]),
                    priority=r["priority"],
                    retries=r["retries"],
                    max_retries=r["max_retries"]
                ) for r in rows]
        finally:
            self._put_conn(conn)

    def update_job_status(self, job_id: UUID, status: JobStatus, error: Optional[str] = None):
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE ai_jobs 
                    SET status = %s, error_message = %s, updated_at = %s
                    WHERE id = %s
                """, (status.value, error, datetime.utcnow(), job_id))
            conn.commit()
        finally:
            self._put_conn(conn)

    # ── Dispatching Logic (Selector) ──────────────────────────────────────────

    def dispatch_normalization(self, limit: int = 50):
        """Seleciona articulos raw que ainda não foram normalizados."""
        conn = self._get_conn()

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM raw_articles 
                    WHERE id NOT IN (SELECT id FROM news_normalized)
                    AND status = 'pending'
                    LIMIT %s
                """, (limit,))
                ids = [r[0] for r in cur.fetchall()]
                
                for target_id in ids:
                    self.create_job(TaskType.NORMALIZE, target_id)
                
                logger.info(f"Dispatched {len(ids)} normalization jobs")
        finally:
            self._put_conn(conn)

    def dispatch_enrichment(self, limit: int = 50):
        """Seleciona notícias normalizadas que ainda não foram enriquecidas."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM news_normalized 
                    WHERE id NOT IN (SELECT id FROM news_enriched)
                    AND is_valid = TRUE
                    LIMIT %s
                """, (limit,))
                ids = [r[0] for r in cur.fetchall()]
                
                for target_id in ids:
                    self.create_job(TaskType.ENRICH, target_id)
                
                logger.info(f"Dispatched {len(ids)} enrichment jobs")
        finally:
            self._put_conn(conn)
