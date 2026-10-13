"""
Orchestrator — the single assembly point of the entire engine.
Single responsibility: build the dependency graph and expose clean public methods.
No business logic lives here — it delegates to domain modules.
"""
from __future__ import annotations

import asyncio

from config.logging_setup import get_logger
from config.settings import AppConfig
from ai_agent.article_processor import ArticleProcessor
from ai_agent.processing_pipeline import ProcessingPipeline
from discovery.source_discovery import SourceDiscovery
from ingestion.article_fetcher import ArticleFetcher
from ingestion.ingestion_pipeline import IngestionPipeline
from ingestion.language_detector import LanguageDetector
from ingestion.topic_classifier import TopicClassifier
from models.entities import NewsSource, SourceStatus, SourceType
from scheduler.job_scheduler import JobScheduler
from storage.article_repository import ArticleRepository
from storage.database import init_async_pool, init_sync_pool, run_migrations, get_sync_pool, sync_connection, sync_cursor
from storage.media_storage import MediaStorage
from storage.source_repository import SourceRepository
from ai_engine.pipeline import AIOrchestrator
from ai_engine.services.tts_service import TTSService
from ai_engine.workers.engagement_worker import EngagementWorker

logger = get_logger("core.orchestrator")


class Orchestrator:

    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._built = False

        # Repositories
        self._source_repo: SourceRepository
        self._article_repo: ArticleRepository

        # Domain services
        self._ingestion_pipeline: IngestionPipeline
        self._processing_pipeline: ProcessingPipeline
        self._discovery: SourceDiscovery
        self._scheduler: JobScheduler
        self._ai_orch: AIOrchestrator

    # ── Bootstrap ─────────────────────────────────────────────────────────────
    @property
    def db_pool(self):
        return get_sync_pool()

    def bootstrap(self) -> None:
        """Initialise DB pools, run migrations, wire dependencies."""
        logger.info("Bootstrapping engine...")

        init_sync_pool(self._cfg.db)
        run_migrations(self._cfg.db)

        self._build_components()
        self._register_default_sources()
        self._scheduler.start()
        self._built = True

        self._generate_missing_audios_bg()

        logger.info("Engine ready")

    def _generate_missing_audios_bg(self):
        def worker():
            import threading
            import time
            from storage.database import sync_connection, sync_cursor
            
            time.sleep(5) # Wait for server to be fully ready
            logger.info("A verificar audios em falta...")
            
            try:
                with sync_connection() as conn:
                    with sync_cursor(conn) as cur:
                        # Posts
                        cur.execute("SELECT id, body_pt FROM processed_articles WHERE status = 'published' AND audio_url IS NULL")
                        posts = cur.fetchall()
                        for p in posts:
                            if hasattr(self, '_tts_service') and self._tts_service:
                                try:
                                    logger.info(f"Gerando audio em falta para post {p['id']}")
                                    url = self._tts_service.generate_audio(p["body_pt"], prefix=f"post_{p['id']}")
                                    cur.execute("UPDATE processed_articles SET audio_url = %s WHERE id = %s", (url, p["id"]))
                                    conn.commit()
                                except Exception as e:
                                    logger.error(f"Erro TTS post {p['id']}: {e}")
                        
                        # Comments
                        cur.execute("SELECT id, content FROM comments WHERE is_ai = TRUE AND audio_url IS NULL")
                        comments = cur.fetchall()
                        for c in comments:
                            if hasattr(self, '_tts_service') and self._tts_service:
                                try:
                                    logger.info(f"Gerando audio em falta para comment {c['id']}")
                                    url = self._tts_service.generate_audio(c["content"], prefix=f"comment_{c['id']}")
                                    cur.execute("UPDATE comments SET audio_url = %s, is_audio = TRUE WHERE id = %s", (url, c["id"]))
                                    conn.commit()
                                except Exception as e:
                                    logger.error(f"Erro TTS comment {c['id']}: {e}")
                logger.info("Verificação de audios concluída.")
            except Exception as e:
                logger.error(f"Erro bg audio: {e}")

        import threading
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    async def bootstrap_async(self) -> None:
        """Initialise async pool (call after bootstrap())."""
        await init_async_pool(self._cfg.db)
        # Initialise new AI Engine with the established global pool
        pool = get_sync_pool()
        self._ai_orch = AIOrchestrator(pool, self._cfg)

    # ── Public manual triggers ────────────────────────────────────────────────

    def run_ingestion(self, run_type: str = "manual", keywords: list[str] = None) -> dict:
        """Trigger ingestion across all active sources. Thread-safe."""
        logger.info("Running ingestion (%s) [Keywords: %s]", run_type, keywords)
        sources = self._source_repo.get_active_sources()
        totals = {"fetched": 0, "skipped": 0, "failed": 0, "sources": len(sources)}

        for source in sources:
            try:
                result = self._ingestion_pipeline.ingest_source(source, keywords=keywords)
                totals["fetched"] += result.fetched
                totals["skipped"] += result.skipped
                totals["failed"] += result.failed
            except Exception as exc:
                logger.error("Ingestion failed for %s: %s", source.url, exc)
                totals["failed"] += 1

        self._article_repo.log_ingestion_run(run_type, totals["fetched"], totals["failed"])
        logger.info("Ingestion complete: %s", totals)
        return totals

    async def run_ai_processing(self) -> int:
        """Process all pending articles through AI. Returns published count."""
        return await self._processing_pipeline.run_once()

    def run_discovery(self) -> dict:
        """Discover new sources from the web."""
        result = self._discovery.run_discovery()
        return {
            "discovered": result.discovered,
            "skipped": result.skipped_duplicates,
            "failed": result.failed,
        }

    async def start_continuous_ai_loop(self) -> None:
        """Long-running async AI processing loop. Blocks until cancelled."""
        await self._processing_pipeline.run_continuous(
            interval_seconds=self._cfg.scheduler.ai_processing_interval_seconds
        )

    def trigger_scheduled_ingestion(self) -> None:
        """Fire the scheduled ingestion job manually."""
        self._scheduler.trigger_ingestion_now()

    # ── Wiring ────────────────────────────────────────────────────────────────

    def _build_components(self) -> None:
        media = MediaStorage(self._cfg.minio)

        self._source_repo = SourceRepository()
        self._article_repo = ArticleRepository()

        fetcher    = ArticleFetcher()
        detector   = LanguageDetector()
        classifier = TopicClassifier()

        self._ingestion_pipeline = IngestionPipeline(
            fetcher=fetcher,
            detector=detector,
            classifier=classifier,
            article_repo=self._article_repo,
            source_repo=self._source_repo,
            media_storage=media,
        )

        try:
            tts_service = TTSService(media, self._cfg)
        except Exception as e:
            logger.error(f"Erro ao inicializar TTSService: {e}")
            tts_service = None
            
        processor = ArticleProcessor(self._cfg.ai)
        self._processing_pipeline = ProcessingPipeline(
            processor=processor,
            article_repo=self._article_repo,
            tts_service=tts_service,
            pause_between_articles=5.0
        )
        self._tts_service = tts_service

        self._discovery = SourceDiscovery(
            source_repo=self._source_repo,
            classifier=classifier,
            search_terms=self._cfg.discovery_search_terms,
        )

        self._scheduler = JobScheduler(self._cfg.scheduler)
        self._scheduler.register_ingestion_job(
            lambda: self.run_ingestion("scheduled")
        )
        self._scheduler.register_discovery_job(self.run_discovery)
        self._scheduler.register_publishing_job(self.publish_scheduled_posts, interval_seconds=10)
        self._scheduler.register_engagement_job(self.run_engagement_analysis, interval_minutes=60)
        self._scheduler.register_ai_processing_job(self.run_sync_ai_processing, interval_seconds=self._cfg.scheduler.ai_processing_interval_seconds)

    def run_sync_ai_processing(self) -> None:
        """Runs the AI processing pipeline synchronously via the scheduler."""
        import asyncio
        from storage.database import init_async_pool, close_async_pool

        async def _run():
            await init_async_pool(self._cfg.db)
            try:
                return await self._processing_pipeline.run_once()
            finally:
                await close_async_pool()

        try:
            logger.info("[JOB START] Iniciando processamento de IA em background...")
            count = asyncio.run(_run())
            if count:
                logger.info("[JOB DONE] O Processamento de IA publicou %d artigos.", count)
            else:
                logger.info("[JOB DONE] O Processamento de IA não encontrou artigos pendentes.")
        except Exception as exc:
            logger.error("[JOB ERROR] Falha no processamento de IA: %s", exc)

    def run_engagement_analysis(self) -> None:
        """Runs the background job to measure post heat and interact using AI."""
        try:
            logger.info("[JOB START] Iniciando análise de calor/engajamento dos posts...")
            worker = EngagementWorker(self._cfg.ai, tts_service=getattr(self, '_tts_service', None))
            worker.analyze_and_engage()
            logger.info("[JOB DONE] Análise de calor/engajamento terminada.")
        except Exception as exc:
            logger.error("[JOB ERROR] Falha no job de engajamento: %s", exc)

    def publish_scheduled_posts(self) -> None:
        """Finds processed articles/posts with status 'processed' and schedules them to 'published' if due."""
        try:
            # Descomenta se quiseres log de início a cada 10 seg. (Pode ser demasiado ruidoso)
            # logger.info("[JOB START] Verificando se existem posts agendados para publicar...")
            with sync_connection() as conn:
                with sync_cursor(conn) as cur:
                    cur.execute(
                        """
                        UPDATE processed_articles
                        SET status = 'published', published_at = now()
                        WHERE status = 'processed' AND (scheduled_at IS NULL OR scheduled_at <= now())
                        RETURNING id, title_pt
                        """
                    )
                    rows = cur.fetchall()
                    if rows:
                        for row in rows:
                            logger.info("[PUBLISH] Post agendado publicado agora: %s (ID: %s)", row["title_pt"], row["id"])
                    # Descomenta para log final
                    # else:
                    #     logger.info("[JOB DONE] Sem posts agendados para publicar no momento.")
        except Exception as exc:
            logger.error("[JOB ERROR] Falha na publicação agendada: %s", exc)

    def _register_default_sources(self) -> None:
        """Seed the DB with a minimal set of known good sources if none exist."""
        existing = self._source_repo.get_active_sources()
        if existing:
            return

        channels = [
            NewsSource(url="https://www.angop.ao", name="ANGOP",
                    source_type=SourceType.NEWSPAPER, locale="pt-AO", topic_category="general"),
            NewsSource(url="https://www.jornaldeangola.ao", name="Jornal de Angola",
                    source_type=SourceType.NEWSPAPER, locale="pt-AO", topic_category="general"),
            NewsSource(url="https://www.verangola.net", name="Ver Angola",
                    source_type=SourceType.NEWSPAPER, locale="pt-AO", topic_category="general"),
            NewsSource(url="https://www.economiaemercado.com", name="Economia & Mercado",
                    source_type=SourceType.NEWSPAPER, locale="pt-AO", topic_category="economy"),
            NewsSource(url="https://www.mercado.co.ao", name="Mercado",
                    source_type=SourceType.NEWSPAPER, locale="pt-AO", topic_category="economy"),
            NewsSource(url="https://www.expansao.co.ao", name="Expansão Angola",
                    source_type=SourceType.NEWSPAPER, locale="pt-AO", topic_category="finance"),
            NewsSource(url="https://opais.co.mz", name="O País",
                    source_type=SourceType.NEWSPAPER, locale="pt-MZ", topic_category="general"),
            NewsSource(url="https://www.jornalnoticias.co.mz", name="Jornal Notícias",
                    source_type=SourceType.NEWSPAPER, locale="pt-MZ", topic_category="general"),
            NewsSource(url="https://www.cartamz.com", name="Carta de Moçambique",
                    source_type=SourceType.NEWSPAPER, locale="pt-MZ", topic_category="business"),
            NewsSource(url="https://www.inforpress.cv", name="Inforpress",
                    source_type=SourceType.NEWSPAPER, locale="pt-CV", topic_category="general"),
            NewsSource(url="https://expressodasilhas.cv", name="Expresso das Ilhas",
                    source_type=SourceType.NEWSPAPER, locale="pt-CV", topic_category="general"),
            NewsSource(url="https://www.telanon.info", name="Tela Non",
                    source_type=SourceType.NEWSPAPER, locale="pt-ST", topic_category="general"),
            NewsSource(url="https://eco.sapo.pt", name="ECO",
                    source_type=SourceType.NEWSPAPER, locale="pt-PT", topic_category="finance"),
            NewsSource(url="https://jornaleconomico.sapo.pt", name="Jornal Económico",
                    source_type=SourceType.NEWSPAPER, locale="pt-PT", topic_category="finance"),
            NewsSource(url="https://www.jornaldenegocios.pt", name="Jornal de Negócios",
                    source_type=SourceType.NEWSPAPER, locale="pt-PT", topic_category="finance"),
            NewsSource(url="https://expresso.pt", name="Expresso",
                    source_type=SourceType.NEWSPAPER, locale="pt-PT", topic_category="business"),
            NewsSource(url="https://observador.pt", name="Observador",
                    source_type=SourceType.NEWSPAPER, locale="pt-PT", topic_category="general"),
            NewsSource(url="https://tek.sapo.pt", name="SAPO Tek",
                    source_type=SourceType.NEWSPAPER, locale="pt-PT", topic_category="technology"),
            NewsSource(url="https://valor.globo.com", name="Valor Económico",
                    source_type=SourceType.NEWSPAPER, locale="pt-BR", topic_category="finance"),
            NewsSource(url="https://exame.com", name="Exame",
                    source_type=SourceType.NEWSPAPER, locale="pt-BR", topic_category="business"),
            NewsSource(url="https://www.infomoney.com.br", name="InfoMoney",
                    source_type=SourceType.NEWSPAPER, locale="pt-BR", topic_category="finance"),
            NewsSource(url="https://www.startse.com", name="StartSe",
                    source_type=SourceType.NEWSPAPER, locale="pt-BR", topic_category="startups"),
            NewsSource(url="https://www.forbesafrica.com", name="Forbes Africa",
                    source_type=SourceType.NEWSPAPER, locale="en-AF", topic_category="business"),
            NewsSource(url="https://www.africanews.com", name="AfricaNews",
                    source_type=SourceType.NEWSPAPER, locale="en-AF", topic_category="africa"),
            NewsSource(url="https://www.reuters.com", name="Reuters",
                    source_type=SourceType.NEWSPAPER, locale="en-US", topic_category="economy"),
            NewsSource(url="https://www.bbc.com/news/world/africa", name="BBC Africa",
                    source_type=SourceType.NEWSPAPER, locale="en-GB", topic_category="africa"),
            NewsSource(url="https://www.linkedin.com/news", name="LinkedIn News",
                    source_type=SourceType.SOCIAL_NETWORK, locale="pt", topic_category="business"),
            NewsSource(url="https://www.linkedin.com/company/angop", name="ANGOP LinkedIn",
                    source_type=SourceType.SOCIAL_NETWORK, locale="pt-AO", topic_category="general"),
            NewsSource(url="https://www.linkedin.com/company/eco-online", name="ECO LinkedIn",
                    source_type=SourceType.SOCIAL_NETWORK, locale="pt-PT", topic_category="finance"),
            NewsSource(url="https://medium.com/tag/fintech", name="Medium Fintech",
                    source_type=SourceType.BLOG, locale="pt", topic_category="fintech"),
            NewsSource(url="https://www.youtube.com/@EuronewsPortugues", name="Euronews Português",
                    source_type=SourceType.VIDEO_CHANNEL, locale="pt", topic_category="international"),
            NewsSource(url="https://www.youtube.com/@InfoMoney", name="InfoMoney YouTube",
                    source_type=SourceType.VIDEO_CHANNEL, locale="pt-BR", topic_category="finance")
        ]

        for source in channels:
            try:
                self._source_repo.upsert_source(source)
            except Exception as exc:
                logger.warning("Could not seed source %s: %s", source.url, exc)

        logger.info("Default sources seeded (%d)", len(channels))
