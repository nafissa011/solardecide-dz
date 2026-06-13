from flask import Blueprint, request, jsonify
from db_models import db, Analysis
import jwt
from config import JWT_SECRET, JWT_ALGORITHM

bp = Blueprint('analyses', __name__)


def _get_user_id():
    """Extract user_id from httpOnly auth cookie or Authorization header."""
    token = request.cookies.get("auth_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


@bp.get('/analyses')
def list_analyses():
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required', 'status': 401}), 401

    analyses = Analysis.query.filter_by(user_id=user_id).order_by(Analysis.created_at.desc()).all()

    data = [{
        'id': a.id,
        'name': a.name,
        'capacity_mw': a.capacity_mw,
        'wilaya_code': a.wilaya_code,
        'created_at': a.created_at.isoformat()
    } for a in analyses]

    return jsonify({'data': data, 'status': 200})


@bp.post('/analyses')
def create_analysis():
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required', 'status': 401}), 401

    data = request.get_json(silent=True) or {}
    name = data.get('name', 'Untitled Analysis')
    capacity_mw = data.get('capacity_mw')
    wilaya_code = data.get('wilaya_code')

    if not capacity_mw or not wilaya_code:
        return jsonify({'error': 'Missing required fields', 'status': 400}), 400

    new_analysis = Analysis(
        user_id=user_id,
        name=name,
        capacity_mw=capacity_mw,
        wilaya_code=str(wilaya_code)
    )
    db.session.add(new_analysis)
    db.session.commit()

    return jsonify({
        'data': {'id': new_analysis.id},
        'message': 'Analysis created successfully',
        'status': 201
    }), 201