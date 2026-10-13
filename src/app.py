import sys
from pathlib import Path

# Adiciona a pasta 'src' ao sys.path automaticamente
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from datetime import datetime
import os

from config.settings import load_config
from storage.database import init_sync_pool
from api.controllers.source_controller import source_bp
from api.controllers.article_controller import article_bp
from api.controllers.post_controller import post_bp # Novo: Importa o blueprint de posts
from api.controllers.auth_controller import auth_bp # Novo: Importa o blueprint de auth
from api.controllers.user_controller import user_bp # Adicionado para gestão de perfis

def create_app():
    app = Flask(__name__)
    CORS(app)
    
    # JWT Configuration
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "super-secret-key-change-me")
    jwt = JWTManager(app)
    
    # Config and DB via Orchestrator (starts JobScheduler and AI pipeline)
    cfg = load_config()
    from core.orchestrator import Orchestrator
    orchestrator = Orchestrator(cfg)
    orchestrator.bootstrap()
    
    # Register Controllers (Blueprints)
    app.register_blueprint(source_bp, url_prefix='/api')
    app.register_blueprint(article_bp, url_prefix='/api')
    app.register_blueprint(post_bp, url_prefix='/api') # Novo: Registra o blueprint de posts
    app.register_blueprint(auth_bp, url_prefix='/api') # Novo: Registra o blueprint de auth
    app.register_blueprint(user_bp, url_prefix='/api/users') # User profile and avatars

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({
            "status": "healthy", 
            "timestamp": datetime.utcnow().isoformat(),
            "service": "news-engine-api"
        })

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
