import asyncio
from ai_engine.dispatcher import AIDispatcher
from ai_engine.workers.news_worker import NewsWorker
from ai_engine.services.editorial_service import EditorialService
from ai_engine.services.vector_service import VectorService
from ai_engine.gateway.ai_gateway import get_gateway
from ai_engine.models.pipeline_models import TaskType

from config.settings import AppConfig
from config.logging_setup import get_logger

logger = get_logger("ai_engine.pipeline")

class AIOrchestrator:
    def __init__(self, db_pool, config: AppConfig):
        self.config = config
        self.dispatcher = AIDispatcher(db_pool)
        # Gateway preparado para múltiplos providers (Ollama / OpenRouter)
        self.ai_gateway = get_gateway(config.ai)

        self.editorial_service = EditorialService(self.ai_gateway)
        self.vector_service = VectorService(db_pool, config.ai)

        self.worker = NewsWorker(self.dispatcher, self.editorial_service)

    async def run_automatic_pipeline(self):
        """Execução automática completa: Seleciona -> Despacha -> Processa."""
        logger.info("Starting automatic AI pipeline execution")
        
        # 1. Normalização
        self.dispatcher.dispatch_normalization(limit=20)
        await self.worker.process_jobs(TaskType.NORMALIZE)
        
        # 2. Enriquecimento
        self.dispatcher.dispatch_enrichment(limit=20)
        await self.worker.process_jobs(TaskType.ENRICH)
        
        # 3. Clustering (Implementação futura de jobs específicos)
        # 4. Post Generation (Baseado em clusters)
        
        logger.info("Automatic AI pipeline execution finished")

    async def run_step(self, step_name: str, limit: int = 10):
        """Execução manual de uma etapa específica via CLI."""
        logger.info(f"Manually triggering step: {step_name}")
        
        if step_name == "normalize":
            self.dispatcher.dispatch_normalization(limit=limit)
            await self.worker.process_jobs(TaskType.NORMALIZE, limit=limit)
        elif step_name == "enrich":
            self.dispatcher.dispatch_enrichment(limit=limit)
            await self.worker.process_jobs(TaskType.ENRICH, limit=limit)
        else:
            logger.warning(f"Step {step_name} not yet implemented or invalid")
