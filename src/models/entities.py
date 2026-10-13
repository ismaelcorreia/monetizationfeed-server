"""
Domain entities — pure dataclasses, no ORM coupling.
Each class owns exactly one concept.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


# ── Enumerations ──────────────────────────────────────────────────────────────

class ArticleStatus(str, Enum):
    PENDING   = "pending"     # fetched, not yet processed by AI
    PROCESSED = "processed"   # AI translated/treated
    PUBLISHED = "published"   # ready to consume
    FAILED    = "failed"      # processing error


class SourceStatus(str, Enum):
    ACTIVE   = "active"
    INACTIVE = "inactive"
    UNKNOWN  = "unknown"


class SourceType(str, Enum):
    RSS        = "rss"
    NEWSPAPER  = "newspaper"
    DISCOVERED = "discovered"
    NEWS_AGENCY = "news_agency"
    MAGAZINE = "magazine"
    NEWS_PORTAL = "news_portal"
    FINANCIAL_PORTAL = "financial_portal"
    TECHNOLOGY_PORTAL = "technology_portal"
    SOCIAL_NETWORK = "social_network"
    BLOG = "blog"
    VIDEO_CHANNEL = "video_channel"
    PODCAST = "podcast"
    COMMUNITY = "community"



# ── Core entities ─────────────────────────────────────────────────────────────

@dataclass
class NewsSource:
    url: str
    name: str
    source_type: SourceType
    locale: str                          # e.g. "pt-AO", "en-US"
    topic_category: str                  # e.g. "economy", "politics"
    id: UUID = field(default_factory=uuid4)
    status: SourceStatus = SourceStatus.ACTIVE
    reliability_score: float = 1.0
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    last_fetched_at: Optional[datetime] = None
    app_hint: Optional[str] = None       # e.g. "BBC", "Jornal de Angola"


@dataclass
class RawArticle:
    source_id: UUID
    url: str
    title: str
    raw_text: str
    topic: str
    language_detected: str
    data_publicada: Optional[datetime]
    country: str = "unknown"
    word_count: int = 0
    id: UUID = field(default_factory=uuid4)
    status: ArticleStatus = ArticleStatus.PENDING
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    media_keys: list[str] = field(default_factory=list)   # MinIO object keys
    authors: list[str] = field(default_factory=list)
    summary: Optional[str] = None


@dataclass
class ProcessedArticle:
    raw_article_id: UUID
    title_pt: str
    body_pt: str
    topic: str
    persuasion_hooks: list[str]           # bullet notes from AI treatment
    id: UUID = field(default_factory=uuid4)
    status: ArticleStatus = ArticleStatus.PUBLISHED
    processed_at: datetime = field(default_factory=datetime.utcnow)
    word_count: int = 0
    reading_time_minutes: float = 0.0
    metadata: dict = field(default_factory=dict)
    audio_url: Optional[str] = None


@dataclass
class DiscoveredSource:
    url: str
    name: str
    topic_category: str
    locale: str
    id: UUID = field(default_factory=uuid4)
    source_type: SourceType = SourceType.DISCOVERED
    app_hint: Optional[str] = None
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    promoted: bool = False               # True once moved to news_sources
