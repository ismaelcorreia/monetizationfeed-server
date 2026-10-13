from flask import Blueprint, jsonify, request
from uuid import UUID
from datetime import datetime
from storage.article_repository import ArticleRepository
from storage.media_storage import MediaStorage
from config.settings import load_config
from api.utils import dataclass_to_dict

article_bp = Blueprint('articles', __name__)
article_repo = ArticleRepository()

# Inicializa média storage para gerar URLs
cfg = load_config()
media_storage = MediaStorage(cfg.minio)

def _enrich_with_media_urls(item: dict):
    """Substitui media_keys por URLs reais do MinIO."""
    keys = item.get("media_keys", [])
    if keys:
        item["media_urls"] = [media_storage.get_presigned_url(k) for k in keys]
    else:
        item["media_urls"] = []
    return item

@article_bp.route('/articles/raw', methods=['GET'])
def list_raw_articles():
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    # Novos filtros inteligentes
    topic = request.args.get('topic')
    country = request.args.get('country')
    language = request.args.get('lang')
    
    articles = article_repo.get_all_raw_articles(
        limit=limit, 
        offset=offset,
        topic=topic,
        country=country,
        language=language
    )
    results = []
    for a in articles:
        d = dataclass_to_dict(a)
        results.append(_enrich_with_media_urls(d))
    return jsonify(results)

@article_bp.route('/articles/raw', methods=['POST'])
def add_raw_article():
    data = request.json
    try:
        from models.entities import RawArticle
        from uuid import uuid4
        article = RawArticle(
            source_id=UUID(data['source_id']),
            url=data['url'],
            title=data['title'],
            raw_text=data['raw_text'],
            topic=data.get('topic', 'general'),
            language_detected=data.get('language', 'pt'),
            country=data.get('country', 'unknown'),
            word_count=len(data['raw_text'].split()),
            published_at=datetime.utcnow()
        )
        article_repo.insert_raw_article(article)
        return jsonify(dataclass_to_dict(article)), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@article_bp.route('/articles/processed', methods=['GET'])
def list_processed_articles():
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    # Novos filtros inteligentes
    topic = request.args.get('topic')
    country = request.args.get('country')
    language = request.args.get('lang')
    
    articles = article_repo.get_published_articles(
        limit=limit, 
        offset=offset,
        topic=topic,
        country=country,
        language=language
    )
    
    # helper for dict conversion
    results = []
    for a in articles:
        for k, v in a.items():
            if isinstance(v, (UUID, datetime)):
                a[k] = str(v)
        results.append(_enrich_with_media_urls(a))
    return jsonify(results)

@article_bp.route('/articles/<uuid:article_id>', methods=['DELETE'])
def delete_article(article_id):
    success = article_repo.delete_article(article_id)
    return jsonify({"success": success}), 200 if success else 404
