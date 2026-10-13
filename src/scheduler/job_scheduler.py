"""
JobScheduler — APScheduler wrapper.
Single responsibility: register and run cron jobs.
Knows WHEN to run, delegates HOW to core handlers.
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config.logging_setup import get_logger
from config.settings import SchedulerConfig

logger = get_logger("scheduler.job_scheduler")


class JobScheduler:

    def __init__(self, cfg: SchedulerConfig) -> None:
        self._cfg = cfg
        self._scheduler = BackgroundScheduler(timezone="UTC")

    def register_ingestion_job(self, handler: callable) -> None:
        """handler() is called daily per INGESTION_CRON."""
        self._scheduler.add_job(
            func=handler,
            trigger=CronTrigger.from_crontab(self._cfg.ingestion_cron),
            id="daily_ingestion",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info("Ingestion job scheduled: %s", self._cfg.ingestion_cron)

    def register_discovery_job(self, handler: callable) -> None:
        """handler() is called weekly per DISCOVERY_CRON."""
        self._scheduler.add_job(
            func=handler,
            trigger=CronTrigger.from_crontab(self._cfg.discovery_cron),
            id="weekly_discovery",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info("Discovery job scheduled: %s", self._cfg.discovery_cron)

    def register_publishing_job(self, handler: callable, interval_seconds: int = 10) -> None:
        """handler() is called every interval_seconds to publish scheduled posts."""
        self._scheduler.add_job(
            func=handler,
            trigger="interval",
            seconds=interval_seconds,
            id="scheduled_publishing",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info("Publishing job scheduled every %d seconds", interval_seconds)
    def register_engagement_job(self, handler: callable, interval_minutes: int = 15) -> None:
        """handler() is called every interval_minutes to trigger AI engagement."""
        self._scheduler.add_job(
            func=handler,
            trigger="interval",
            minutes=interval_minutes,
            id="engagement_publishing",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=__import__("datetime").datetime.utcnow()
        )
        logger.info("Engagement job scheduled every %d minutes", interval_minutes)

    def register_ai_processing_job(self, handler: callable, interval_seconds: int = 300) -> None:
        """handler() is called every interval_seconds to trigger AI processing."""
        self._scheduler.add_job(
            func=handler,
            trigger="interval",
            seconds=interval_seconds,
            id="ai_processing",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info("AI Processing job scheduled every %d seconds", interval_seconds)

    def start(self) -> None:
        self._scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self, wait: bool = True) -> None:
        self._scheduler.shutdown(wait=wait)
        logger.info("Scheduler stopped")

    def trigger_ingestion_now(self) -> None:
        """Manual trigger — runs ingestion immediately outside cron schedule."""
        job = self._scheduler.get_job("daily_ingestion")
        if job:
            job.modify(next_run_time=__import__("datetime").datetime.utcnow())
            logger.info("Manual ingestion trigger fired")
        else:
            logger.warning("Ingestion job not found — scheduler may not be started")
