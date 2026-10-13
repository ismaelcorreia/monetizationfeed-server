"""
cli.py — Manual control interface.
Run ingestion, AI processing, or discovery on demand.
Usage: python cli.py [ingest|process|discover|seed-source]
"""
from __future__ import annotations

import asyncio
import sys
import argparse

from config.logging_setup import configure_logging
from config.settings import load_config
from core.orchestrator import Orchestrator
from ai_engine.pipeline import AIOrchestrator
from models.entities import NewsSource, SourceType
from storage.database import init_sync_pool, run_migrations
from storage.source_repository import SourceRepository


def _bootstrap_minimal(cfg) -> Orchestrator:
    orch = Orchestrator(cfg)
    orch.bootstrap()
    return orch


def cmd_ingest(keywords: str = None) -> None:
    cfg = load_config()
    configure_logging(cfg.log_level)
    orch = _bootstrap_minimal(cfg)
    
    kw_list = [k.strip() for k in keywords.split(',')] if keywords else None
    result = orch.run_ingestion(run_type="manual", keywords=kw_list)
    print(f"Ingestion complete: {result}")


def cmd_process() -> None:
    cfg = load_config()
    configure_logging(cfg.log_level)
    orch = _bootstrap_minimal(cfg)

    async def _run():
        await orch.bootstrap_async()
        count = await orch.run_ai_processing()
        print(f"AI processing complete — {count} articles published")

    asyncio.run(_run())


def cmd_discover() -> None:
    cfg = load_config()
    configure_logging(cfg.log_level)
    orch = _bootstrap_minimal(cfg)
    result = orch.run_discovery()
    print(f"Discovery complete: {result}")


def cmd_add_source(url: str, name: str, locale: str = "en-US", topic: str = "general") -> None:
    cfg = load_config()
    configure_logging(cfg.log_level)
    init_sync_pool(cfg.db)
    run_migrations(cfg.db)

    repo = SourceRepository()
    source = NewsSource(
        url=url,
        name=name,
        source_type=SourceType.NEWSPAPER,
        locale=locale,
        topic_category=topic,
    )
    repo.upsert_source(source)
    print(f"Source added: {name} ({url})")


def cmd_list_sources(topic: str = None) -> None:
    cfg = load_config()
    init_sync_pool(cfg.db)
    from storage.source_repository import SourceRepository
    repo = SourceRepository()
    sources = repo.get_all_sources(limit=50, topic=topic)
    title = f"--- SITES REGISTADOS (Tópico: {topic}) ---" if topic else "--- SITES REGISTADOS ---"
    print(f"\n{title}")
    for s in sources:
        print(f"[{s.status.value.upper()}] {s.name} - {s.url} ({s.topic_category})")


def cmd_list_discovered() -> None:
    cfg = load_config()
    init_sync_pool(cfg.db)
    from storage.source_repository import SourceRepository
    repo = SourceRepository()
    discovered = repo.get_all_discovered(limit=50)
    print("\n--- SITES DESCOBERTOS (PENDENTES) ---")
    for d in discovered:
        status = "PROMOVIDO" if d.promoted else "NOVO"
        print(f"[{status}] {d.name} - {d.url}")


def cmd_list_articles() -> None:
    cfg = load_config()
    init_sync_pool(cfg.db)
    from storage.article_repository import ArticleRepository
    repo = ArticleRepository()
    articles = repo.get_all_raw_articles(limit=50)
    print("\n--- ÚLTIMOS ARTIGOS RECOLHIDOS ---")
    for a in articles:
        media = f" | Mídia: {len(a.media_keys)} ficheiros" if a.media_keys else ""
        print(f"[{a.status.value.upper()}] {a.title[:60]}... ({a.url}){media}")


def cmd_ai_process(step: str, limit: int = 10):
    cfg = load_config()
    orch = _bootstrap_minimal(cfg)
    # Garante que passamos o objeto de pool real (o property do orchestrator)
    pool = orch.db_pool
    ai_orch = AIOrchestrator(pool, cfg)
    
    if step == "auto":
        asyncio.run(ai_orch.run_automatic_pipeline())
    else:
        asyncio.run(ai_orch.run_step(step, limit))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MonetizationFeed CLI")
    subparsers = parser.add_subparsers(dest="command")

    # Ingest
    p_ingest = subparsers.add_parser("ingest", help="Run news ingestion")
    p_ingest.add_argument("keywords", nargs="?", help="Optional keywords (comma-separated)")

    # Discovery
    p_disc = subparsers.add_parser("discovery", help="Run source discovery")

    # List Sources
    p_list = subparsers.add_parser("list-sources", help="List sources")
    p_list.add_argument("topic", nargs="?", help="Filter by topic")

    # AI Process
    p_ai = subparsers.add_parser("ai-process", help="Run AI editorial pipeline")
    p_ai.add_argument("step", choices=["auto", "normalize", "enrich", "cluster", "post"], help="Step to run")
    p_ai.add_argument("--limit", type=int, default=10, help="Max items to process")

    args = parser.parse_args()

    if args.command == "ingest":
        cmd_ingest(args.keywords)
    elif args.command == "discovery":
        cmd_discover()
    elif args.command == "list-sources":
        cmd_list_sources(args.topic)
    elif args.command == "ai-process":
        cmd_ai_process(args.step, args.limit)
    else:
        parser.print_help()
