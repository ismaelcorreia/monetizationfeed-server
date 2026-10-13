from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import io
import uuid
import hashlib
import mimetypes

from config.logging_setup import get_logger
from config.settings import load_config
from storage.database import sync_connection, sync_cursor
from minio import Minio
from minio.error import S3Error

user_bp = Blueprint('user', __name__)
logger = get_logger("api.user_controller")
cfg = load_config()

# Initialize MinIO client
minio_client = Minio(
    endpoint=cfg.minio.endpoint,
    access_key=cfg.minio.access_key,
    secret_key=cfg.minio.secret_key,
    secure=cfg.minio.secure,
)
AVATAR_BUCKET = "user-avatars"

def ensure_avatar_bucket():
    try:
        if not minio_client.bucket_exists(AVATAR_BUCKET):
            minio_client.make_bucket(AVATAR_BUCKET)
            # Set bucket policy for public read access if we want URLs to just work
            # For simplicity, we just leave it and generate presigned URLs or make it public
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": ["*"]},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{AVATAR_BUCKET}/*"]
                    }
                ]
            }
            import json
            minio_client.set_bucket_policy(AVATAR_BUCKET, json.dumps(policy))
    except Exception as e:
        logger.error(f"Error ensuring avatar bucket: {e}")

ensure_avatar_bucket()

@user_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    username = get_jwt_identity()
    try:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute("SELECT id, username, email, name, headline, bio, country, avatar_url, google_id, linkedin_id FROM users WHERE username = %s", (username,))
                user = cur.fetchone()
                if user:
                    return jsonify(dict(user)), 200
                return jsonify({"msg": "User not found"}), 404
    except Exception as e:
        logger.error(f"Error getting profile: {e}")
        return jsonify({"msg": "Internal error"}), 500

@user_bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    username = get_jwt_identity()
    data = request.json
    try:
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute(
                    """
                    UPDATE users 
                    SET name = COALESCE(%s, name),
                        headline = COALESCE(%s, headline),
                        bio = COALESCE(%s, bio),
                        country = COALESCE(%s, country)
                    WHERE username = %s
                    RETURNING id, username, email, name, headline, bio, country, avatar_url
                    """,
                    (data.get('name'), data.get('headline'), data.get('bio'), data.get('country'), username)
                )
                user = cur.fetchone()
                if user:
                    return jsonify(dict(user)), 200
                return jsonify({"msg": "User not found"}), 404
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        return jsonify({"msg": "Internal error"}), 500

@user_bp.route('/profile/avatar', methods=['POST'])
@jwt_required()
def upload_avatar():
    username = get_jwt_identity()
    if 'avatar' not in request.files:
        return jsonify({"msg": "No avatar file provided"}), 400
        
    file = request.files['avatar']
    if file.filename == '':
        return jsonify({"msg": "No selected file"}), 400
        
    try:
        file_bytes = file.read()
        content_type = file.content_type
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        filename = f"{username}_{uuid.uuid4().hex[:8]}{ext}"
        
        minio_client.put_object(
            bucket_name=AVATAR_BUCKET,
            object_name=filename,
            data=io.BytesIO(file_bytes),
            length=len(file_bytes),
            content_type=content_type
        )
        
        # Build public URL assuming minio is exposed or use presigned
        # For simplicity, assuming bucket policy makes it public, URL is: endpoint/bucket/filename
        # Local minio url format usually: http://localhost:9000/user-avatars/filename
        protocol = "https" if cfg.minio.secure else "http"
        avatar_url = f"{protocol}://{cfg.minio.endpoint}/{AVATAR_BUCKET}/{filename}"
        
        with sync_connection() as conn:
            with sync_cursor(conn) as cur:
                cur.execute("UPDATE users SET avatar_url = %s WHERE username = %s", (avatar_url, username))
                
        return jsonify({"avatar_url": avatar_url}), 200
    except Exception as e:
        logger.error(f"Error uploading avatar: {e}")
        return jsonify({"msg": "Failed to upload avatar"}), 500
