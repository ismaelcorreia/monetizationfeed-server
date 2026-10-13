from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4

class JobStatus(Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"

class TaskType(Enum):
    NORMALIZE = "normalize"
    ENRICH = "enrich"
    CLUSTER = "cluster"
    INSIGHTS = "insights"
    POST = "post"

class EditorialStatus(Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"

@dataclass
class AIJob:
    task_type: TaskType
    target_id: UUID
    id: UUID = field(default_factory=uuid4)
    status: JobStatus = JobStatus.PENDING
    priority: int = 0
    retries: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class NormalizedNews:
    id: UUID  # Mesmo ID do RawArticle
    title: str
    content: str
    language: str
    detected_topics: List[str]
    word_count: int
    is_valid: bool = True
    is_duplicate: bool = False
    canonical_url: Optional[str] = None
    normalized_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class EnrichedNews:
    id: UUID
    summary_pt: str
    editorial_title: str
    keywords: List[str]
    entities: Dict[str, Any]
    sentiment: str
    relevance_score: float
    impact_economic: str
    impact_social: str
    opportunities: str
    risks: str
    sector: str
    region: str
    enriched_at: datetime = field(default_factory=datetime.utcnow)
