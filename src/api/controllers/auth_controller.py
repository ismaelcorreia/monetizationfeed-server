from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager
from passlib.hash import pbkdf2_sha256
from datetime import timedelta

from config.logging_setup import get_logger
from config.settings import load_config
from storage.database import sync_connection, sync_cursor

auth_bp = Blueprint('auth', __name__)
logger = get_logger("api.auth_controller")

cfg = load_config()

class UserRepository:
    def add_user(self, username, password=None, email=None, name=None, google_id=None, linkedin_id=None):
        try:
            password_hash = pbkdf2_sha256.hash(password) if password else "oauth_login_no_password"
            with sync_connection() as conn:
                with sync_cursor(conn) as cur:
                    cur.execute("SELECT 1 FROM users WHERE username = %s OR (email = %s AND email IS NOT NULL)", (username, email))
                    if cur.fetchone():
                        return False
                    
                    cur.execute(
                        """
                        INSERT INTO users (username, password_hash, email, name, google_id, linkedin_id) 
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (username, password_hash, email, name, google_id, linkedin_id)
                    )
                    logger.info(f"User '{username}' created in DB.")
                    return True
        except Exception as e:
            logger.error(f"Error adding user {username}: {e}")
            return False

    def get_user_by_email_or_username(self, identifier):
        try:
            with sync_connection() as conn:
                with sync_cursor(conn) as cur:
                    cur.execute("SELECT * FROM users WHERE username = %s OR email = %s", (identifier, identifier))
                    row = cur.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting user {identifier}: {e}")
            return None

    def verify_password(self, username, password):
        user_data = self.get_user_by_email_or_username(username)
        if user_data and user_data["password_hash"] != "oauth_login_no_password":
            return pbkdf2_sha256.verify(password, user_data["password_hash"])
        return False
        
    def link_oauth(self, username, provider, provider_id):
        field = "google_id" if provider == "google" else "linkedin_id"
        try:
            with sync_connection() as conn:
                with sync_cursor(conn) as cur:
                    cur.execute(f"UPDATE users SET {field} = %s WHERE username = %s", (provider_id, username))
                    return True
        except Exception as e:
            logger.error(f"Error linking oauth: {e}")
            return False

user_repo = UserRepository()

@auth_bp.route('/register', methods=['POST'])
def register():
    username = request.json.get('username', None)
    email = request.json.get('email', username)
    password = request.json.get('password', None)
    name = request.json.get('name', None)

    if not username or not password:
        return jsonify({"msg": "Missing username or password"}), 400

    if user_repo.add_user(username, password, email=email, name=name):
        return jsonify({"msg": "User created successfully"}), 201
    else:
        return jsonify({"msg": "User already exists"}), 409

@auth_bp.route('/login', methods=['POST'])
def login():
    username = request.json.get('username', None) # could be email
    password = request.json.get('password', None)

    if not username or not password:
        return jsonify({"msg": "Missing username or password"}), 400

    if user_repo.verify_password(username, password):
        user_data = user_repo.get_user_by_email_or_username(username)
        username_real = user_data["username"]
        access_token = create_access_token(identity=username_real, expires_delta=timedelta(hours=24))
        return jsonify(access_token=access_token, username=username_real, user=user_data), 200
    else:
        return jsonify({"msg": "Bad username or password"}), 401

@auth_bp.route('/<provider>', methods=['POST'])
def oauth_login(provider):
    if provider not in ['google', 'linkedin']:
        return jsonify({"msg": "Unsupported provider"}), 400
        
    email = request.json.get('email')
    provider_id = request.json.get('provider_id')
    name = request.json.get('name', email.split('@')[0] if email else 'User')
    avatar_url = request.json.get('avatar_url')
    
    if not email or not provider_id:
        return jsonify({"msg": "Missing email or provider_id"}), 400
        
    user = user_repo.get_user_by_email_or_username(email)
    
    if not user:
        # Create user if doesn't exist
        username = email.split('@')[0]
        # Append random string to username if needed, but here we just try to insert
        user_repo.add_user(username=username, email=email, name=name, google_id=provider_id if provider=='google' else None, linkedin_id=provider_id if provider=='linkedin' else None)
        user = user_repo.get_user_by_email_or_username(email)
        
        if avatar_url:
             with sync_connection() as conn:
                with sync_cursor(conn) as cur:
                    cur.execute("UPDATE users SET avatar_url = %s WHERE username = %s", (avatar_url, user["username"]))
                    user["avatar_url"] = avatar_url

    else:
        # User exists, link account
        user_repo.link_oauth(user['username'], provider, provider_id)
        
    access_token = create_access_token(identity=user['username'], expires_delta=timedelta(hours=24))
    return jsonify(access_token=access_token, username=user['username'], user=user), 200

@auth_bp.route('/protected', methods=['GET'])
@jwt_required()
def protected():
    return jsonify({"msg": "Access granted"}), 200
