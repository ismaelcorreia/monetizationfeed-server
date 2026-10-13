from flask import Blueprint, jsonify, request
from uuid import UUID
from datetime import datetime

# Importações internas do projeto
from config.logging_setup import get_logger
from storage.article_repository import ArticleRepository
from storage.media_storage import MediaStorage
from config.settings import load_config
from api.utils import dataclass_to_dict # Para converter entidades em dicionários

post_bp = Blueprint('posts', __name__)
logger = get_logger("api.post_controller")

# Dependências
article_repo = ArticleRepository()
cfg = load_config()
media_storage = MediaStorage(cfg.minio)

# Helper para formatar o post para o frontend
def _format_post_for_frontend(raw_article: dict, processed_article: dict) -> dict:
    """
    Formata dados de RawArticle e ProcessedArticle para o formato Post do frontend.
    """
    # Exemplo de mapeamento. Ajustar conforme 'web/types.ts' e lógica de negócio.
    post_id = str(processed_article.get("id"))
    image_url = None
    if raw_article.get("media_keys") and len(raw_article["media_keys"]) > 0:
        first_key = raw_article["media_keys"][0]
        if first_key.startswith("http") or first_key.startswith("blob:"):
            image_url = first_key
        else:
            image_url = media_storage.get_presigned_url(first_key)

    audio_key = processed_article.get("audio_url")
    audio_url = media_storage.get_presigned_url(audio_key) if audio_key else None

    return {
        "id": post_id,
        "title": processed_article.get("title_pt", raw_article.get("title")),
        "excerpt": raw_article.get("summary", ""), # Resumo do RawArticle
        "content": processed_article.get("body_pt", ""),
        "author": ", ".join(raw_article.get("authors", [])),
        "date": processed_article.get("processed_at", raw_article.get("data_publicada")).isoformat() if processed_article.get("processed_at") or raw_article.get("data_publicada") else "",
        "readTime": f"{int(processed_article.get('reading_time_minutes', 0))} min read",
        "category": processed_article.get("topic", raw_article.get("topic", "General")),
        "tags": raw_article.get("tags", []), # Assumindo que RawArticle pode ter tags
        "imageUrl": image_url or "https://picsum.photos/800/600?random=unique", # Fallback image
        "audioUrl": audio_url,
        "impactScore": processed_article.get("impact_score", 0), # Assumindo novo campo ou default
        "likes": 0, # Placeholder para MVP
        "dislikes": 0 # Placeholder para MVP
    }

@post_bp.route('/posts', methods=['GET'])
def get_posts():
    """
    Retorna uma lista de posts formatados para o frontend.
    Suporta paginação e filtros.
    """
    limit = request.args.get('limit', 10, type=int)
    offset = request.args.get('offset', 0, type=int)
    category = request.args.get('category')
    # Adicionar outros filtros conforme necessário (e.g., author, date_range)

    try:
        # Busca artigos processados e seus raw_articles associados
        # Este método precisa ser implementado ou adaptado no ArticleRepository
        posts_data = article_repo.get_published_posts_for_frontend(
            limit=limit,
            offset=offset,
            topic=category, # Mapeia category do frontend para topic do backend
            # ... outros filtros
        )

        formatted_posts = [
            _format_post_for_frontend(p['raw_article'], p['processed_article'])
            for p in posts_data
        ]
        return jsonify(formatted_posts)
    except Exception as e:
        logger.error(f"Error fetching posts: {e}", exc_info=True)
        return jsonify({"error": "Could not retrieve posts"}), 500

@post_bp.route('/posts/<uuid:post_id>', methods=['GET'])
def get_post_detail(post_id: UUID):
    """
    Retorna os detalhes de um post específico formatados para o frontend.
    """
    try:
        post_data = article_repo.get_single_published_post_for_frontend(post_id)

        if not post_data:
            return jsonify({"error": "Post not found"}), 404
        
        formatted_post = _format_post_for_frontend(post_data['raw_article'], post_data['processed_article'])
        return jsonify(formatted_post)
    except Exception as e:
        logger.error(f"Error fetching post {post_id}: {e}", exc_info=True)
        return jsonify({"error": "Could not retrieve post"}), 500

# Rota para criar um post manualmente
from flask_jwt_extended import jwt_required, get_jwt_identity
import uuid
import json
import threading
import time
from storage.database import sync_connection, sync_cursor

@post_bp.route('/posts', methods=['POST'])
@jwt_required(optional=True)
def create_manual_post():
    """
    Cria um post manualmente e associa a um RawArticle placeholder.
    """
    data = request.json
    if not data or not data.get("title") or not data.get("content"):
        return jsonify({"error": "Missing title or content"}), 400

    author_name = get_jwt_identity() or "Autor"
    post_id = uuid.uuid4()
    raw_id = uuid.uuid4()
    title = data.get("title")
    content = data.get("content")
    excerpt = data.get("excerpt", "")
    category = data.get("category", "General")
    tags = data.get("tags", [])
    cover_image = data.get("coverImage")
    audio_url = data.get("audioUrl")

    try:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                # 1. Pega ou cria uma fonte padrão
                cur.execute("SELECT id FROM news_sources LIMIT 1")
                row = cur.fetchone()
                source_id = row["id"] if row else None
                if not source_id:
                    source_id = uuid.uuid4()
                    cur.execute(
                        "INSERT INTO news_sources (id, url, name, status) VALUES (%s, %s, %s, %s)",
                        (str(source_id), "https://makeitclever.space", "Make It Clever", "active")
                    )

                # 2. Cria o RawArticle placeholder
                media_keys = [cover_image] if cover_image else []
                cur.execute(
                    """
                    INSERT INTO raw_articles (id, source_id, url, title, raw_text, summary, media_keys, authors, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(raw_id),
                        str(source_id),
                        f"manual://{post_id}",
                        title,
                        content,
                        excerpt,
                        json.dumps(media_keys),
                        json.dumps([author_name]),
                        "processed"
                    )
                )

                # 3. Cria o ProcessedArticle como publicado
                cur.execute(
                    """
                    INSERT INTO processed_articles 
                    (id, raw_article_id, title_pt, body_pt, topic, persuasion_hooks, word_count, reading_time_minutes, status, processed_at, scheduled_at, published_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now(), now())
                    """,
                    (
                        str(post_id),
                        str(raw_id),
                        title,
                        content,
                        category,
                        json.dumps(tags),
                        len(content.split()),
                        round(len(content.split()) / 200, 2),
                        "published"
                    )
                )

        return jsonify({"msg": "Post created successfully", "id": str(post_id)}), 201
    except Exception as e:
        logger.error(f"Error creating manual post: {e}", exc_info=True)
        return jsonify({"error": f"Could not create post: {str(e)}"}), 500


# Helpers para Comentários
def insert_comment(post_id, parent_id, author, avatar, content, is_ai=False):
    with sync_connection() as conn:
        with sync_cursor(conn) as cur:
            cur.execute(
                """
                INSERT INTO comments (post_id, parent_id, author, avatar, content, is_ai)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (post_id, parent_id, author, avatar, content, is_ai)
            )
            return cur.fetchone()

def get_comments_for_post(post_id):
    with sync_connection() as conn:
        with sync_cursor(conn) as cur:
            cur.execute(
                """
                SELECT id, post_id, parent_id, author, avatar, content, is_ai, is_audio, audio_duration, audio_url, created_at
                FROM comments
                WHERE post_id = %s
                ORDER BY created_at ASC
                """,
                (str(post_id),)
            )
            rows = cur.fetchall()
            comments_map = {}
            top_level = []
            for r in rows:
                audio_key = r.get("audio_url")
                c = {
                    "id": str(r["id"]),
                    "author": r["author"],
                    "avatar": r["avatar"] or f"https://ui-avatars.com/api/?name={r['author']}&background=7CFF00&color=0B0B0B",
                    "content": r["content"],
                    "timestamp": r["created_at"].strftime("%Y-%m-%d %H:%M"),
                    "isAi": r["is_ai"],
                    "isAudio": r["is_audio"] or bool(audio_key),
                    "audioDuration": r["audio_duration"],
                    "audioUrl": media_storage.get_presigned_url(audio_key) if audio_key else None,
                    "replies": []
                }
                comments_map[c["id"]] = c
                if r["parent_id"] is None:
                    top_level.append(c)
                else:
                    parent_uuid = str(r["parent_id"])
                    if parent_uuid in comments_map:
                        comments_map[parent_uuid]["replies"].append(c)
                    else:
                        top_level.append(c)
            return top_level


# Rotas de Comentários
@post_bp.route('/posts/<uuid:post_id>/comments', methods=['GET'])
def get_comments(post_id: UUID):
    try:
        comments = get_comments_for_post(post_id)
        return jsonify(comments), 200
    except Exception as e:
        logger.error(f"Error fetching comments for post {post_id}: {e}", exc_info=True)
        return jsonify({"error": "Could not retrieve comments"}), 500

@post_bp.route('/posts/<uuid:post_id>/comments', methods=['POST'])
@jwt_required(optional=True)
def add_comment(post_id: UUID):
    data = request.json
    if not data or not data.get("content"):
        return jsonify({"error": "Missing content"}), 400

    author = data.get("author") or get_jwt_identity() or "Anónimo"
    avatar = data.get("avatar")
    content = data.get("content")
    parent_id = data.get("parentId") # Pode ser nulo

    try:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute("SELECT id, title_pt, body_pt FROM processed_articles WHERE id = %s", (str(post_id),))
                post = cur.fetchone()
                if not post:
                    return jsonify({"error": "Post not found"}), 404

        comment_row = insert_comment(str(post_id), parent_id, author, avatar, content, is_ai=False)
        comment_id = str(comment_row["id"])
        created_at = comment_row["created_at"].strftime("%Y-%m-%d %H:%M")

        # A geração de comentários pela IA passará a ser gerida por um worker
        # offline (Engagement Worker) em vez de ser despoletada imediatamente.

        return jsonify({
            "id": comment_id,
            "author": author,
            "avatar": avatar or f"https://ui-avatars.com/api/?name={author}&background=7CFF00&color=0B0B0B",
            "content": content,
            "timestamp": created_at,
            "replies": []
        }), 201
    except Exception as e:
        logger.error(f"Error adding comment: {e}", exc_info=True)
        return jsonify({"error": "Could not add comment"}), 500
