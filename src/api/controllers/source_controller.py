from flask import Blueprint, jsonify, request
from storage.source_repository import SourceRepository
from models.entities import NewsSource, SourceType
from api.utils import dataclass_to_dict

source_bp = Blueprint('sources', __name__)
source_repo = SourceRepository()

@source_bp.route('/sources', methods=['GET'])
def list_sources():
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    sources = source_repo.get_all_sources(limit=limit, offset=offset)
    return jsonify([dataclass_to_dict(s) for s in sources])

@source_bp.route('/sources', methods=['POST'])
def add_source():
    data = request.json
    try:
        source = NewsSource(
            url=data['url'],
            name=data['name'],
            source_type=SourceType(data.get('source_type', 'newspaper')),
            locale=data.get('locale', 'en-US'),
            topic_category=data.get('topic', 'general')
        )
        source_repo.upsert_source(source)
        return jsonify(dataclass_to_dict(source)), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@source_bp.route('/sources/<uuid:source_id>', methods=['DELETE'])
def delete_source(source_id):
    success = source_repo.delete_source(source_id)
    return jsonify({"success": success}), 200 if success else 404

@source_bp.route('/discovered', methods=['GET'])
def list_discovered():
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    discovered = source_repo.get_all_discovered(limit=limit, offset=offset)
    return jsonify([dataclass_to_dict(d) for d in discovered])
