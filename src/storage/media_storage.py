"""
MediaStorage — all MinIO operations.
Single responsibility: upload, download, and organise media objects.
Each article gets its own bucket path: news-media/{article_id}/{filename}
"""
from __future__ import annotations

import hashlib
import io
import mimetypes
from pathlib import PurePosixPath
from uuid import UUID

import httpx
from minio import Minio
from minio.error import S3Error

from config.logging_setup import get_logger
from config.settings import MinioConfig

logger = get_logger("storage.media_storage")


class MediaStorage:

    def __init__(self, cfg: MinioConfig) -> None:
        self._client = Minio(
            endpoint=cfg.endpoint,
            access_key=cfg.access_key,
            secret_key=cfg.secret_key,
            secure=cfg.secure,
        )
        self._bucket_prefix = cfg.media_bucket_prefix
        self._ensure_bucket_exists()

    # ── Public interface ──────────────────────────────────────────────────────

    def upload_media_from_url(self, article_id: UUID, media_url: str) -> str | None:
        """
        Download media from URL and store in MinIO.
        Returns the object key on success, None on failure.
        """
        try:
            content, content_type, filename = self._download(media_url)
            object_key = self._build_object_key(article_id, filename)
            self._put_object(object_key, content, content_type)
            logger.debug("Media stored: %s", object_key)
            return object_key
        except Exception as exc:
            logger.warning("Failed to store media %s: %s", media_url, exc)
            return None

    def upload_raw_bytes(
        self,
        article_id: UUID,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        object_key = self._build_object_key(article_id, filename)
        self._put_object(object_key, data, content_type)
        return object_key

    def get_presigned_url(self, object_key: str, expires_hours: int = 24) -> str:
        from datetime import timedelta
        return self._client.presigned_get_object(
            self._bucket_prefix,
            object_key,
            expires=timedelta(hours=expires_hours),
        )

    def delete_article_media(self, article_id: UUID) -> int:
        """Delete all objects for a given article. Returns count deleted."""
        prefix = f"{article_id}/"
        objects = self._client.list_objects(self._bucket_prefix, prefix=prefix, recursive=True)
        count = 0
        for obj in objects:
            self._client.remove_object(self._bucket_prefix, obj.object_name)
            count += 1
        return count

    # ── Private helpers ───────────────────────────────────────────────────────

    def _ensure_bucket_exists(self) -> None:
        try:
            if not self._client.bucket_exists(self._bucket_prefix):
                self._client.make_bucket(self._bucket_prefix)
                logger.info("Created MinIO bucket: %s", self._bucket_prefix)
        except S3Error as exc:
            logger.error("MinIO bucket check failed: %s", exc)
            raise

    def _download(self, url: str) -> tuple[bytes, str, str]:
        from PIL import Image
        
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            resp = client.get(url)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "application/octet-stream").split(";")[0]
        
        # 1. Validação de Formatos
        allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
        if content_type not in allowed_types:
            raise ValueError(f"Formato de imagem não permitido: {content_type}")

        # 2. Validação de Dimensões (Pillow)
        img_data = resp.content
        img = Image.open(io.BytesIO(img_data))
        width, height = img.size
        
        if width < 250:
            raise ValueError(f"Imagem com resolução insuficiente: {width}px de largura (mínimo 250px)")

        ext = mimetypes.guess_extension(content_type) or ".bin"
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        filename = f"{url_hash}{ext}"
        return img_data, content_type, filename

    def _put_object(self, object_key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            bucket_name=self._bucket_prefix,
            object_name=object_key,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    @staticmethod
    def _build_object_key(article_id: UUID, filename: str) -> str:
        return f"{article_id}/{filename}"
