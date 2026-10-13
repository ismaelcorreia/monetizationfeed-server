import sys
import os
import pytest
import json

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from ai_agent.article_processor import ArticleProcessor
from config.settings import AIConfig
from models.entities import RawArticle
from uuid import uuid4

@pytest.fixture
def processor():
    cfg = AIConfig(ollama_base_url="http://localhost:11434", model="mistral")
    return ArticleProcessor(cfg)

def test_parse_response_clean(processor):
    raw_json = '{"title_pt": "Título", "body_pt": "Corpo", "persuasion_hooks": ["hook1"], "topic": "geral"}'
    parsed = processor._parse_response(raw_json)
    assert parsed["title_pt"] == "Título"

def test_parse_response_with_markdown(processor):
    raw_json = '```json\n{"title_pt": "Título Markdown"}\n```'
    parsed = processor._parse_response(raw_json)
    assert parsed["title_pt"] == "Título Markdown"

def test_build_processed(processor):
    article = RawArticle(
        id=uuid4(),
        source_id=uuid4(),
        url="http://test.com",
        title="Original Title",
        raw_text="Original text",
        topic="general",
        language_detected="en",
        published_at=None
    )
    parsed = {
        "title_pt": "Título PT",
        "body_pt": "Este é o corpo do texto traduzido.",
        "persuasion_hooks": ["H1", "H2"],
        "topic": "angola"
    }
    processed = processor._build_processed(article, parsed)
    
    assert processed.title_pt == "Título PT"
    assert processed.word_count == 7
    assert processed.reading_time_minutes > 0
    assert processed.raw_article_id == article.id
