from __future__ import annotations

import csv
import io
import logging
from flask import Blueprint, jsonify, request, Response

from db_models import db, ZoneAnalysisHistory, ForecastHistory, ROIHistory, Report

logger = logging.getLogger(__name__)
bp = Blueprint("history", __name__)


def _get_user_id():
    """Extract user_id from auth cookie or Authorization header."""
    token = request.cookies.get("auth_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        return None
    try:
        import jwt as _jwt
        from config import JWT_SECRET
        payload = _jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload.get("user_id")
    except Exception:
        return None


_TYPE_MODEL = {
    "zone_analysis": ZoneAnalysisHistory,
    "forecast":      ForecastHistory,
    "roi":           ROIHistory,
    "report":        Report,
}


def _serialize(item):
    if hasattr(item, "to_dict"):
        return item.to_dict()
    return {"id": getattr(item, "id", None)}


def _query_for_type(model, user_id, limit, offset):
    q = model.query
    if hasattr(model, "user_id") and user_id is not None:
        q = q.filter_by(user_id=user_id)
    # Models use either created_at or generated_at depending on the table schema
    if hasattr(model, "created_at"):
        q = q.order_by(model.created_at.desc())
    elif hasattr(model, "generated_at"):
        q = q.order_by(model.generated_at.desc())
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return rows, total


@bp.get("/history")
def list_history():
    """
    GET /api/history?type=all|zone_analysis|forecast|roi|report&limit=50&offset=0

    For type=all, fetches from all tables then merges and sorts in Python
    since the models live in different tables with no common base query.
    """
    user_id = _get_user_id()
    qtype = (request.args.get("type") or "all").lower()
    try:
        limit  = max(1, min(int(request.args.get("limit", 50)), 200))
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        return jsonify({"error": "limit/offset invalides", "status": 400}), 400

    items: list = []
    total = 0

    if qtype == "all":
        for model in _TYPE_MODEL.values():
            try:
                rows, t = _query_for_type(model, user_id, limit, offset=0)
                items.extend(rows)
                total += t
            except Exception as exc:
                logger.warning("history list_all skip %s: %s", model.__name__, exc)
        items.sort(
            key=lambda r: getattr(r, "created_at", None) or getattr(r, "generated_at", None),
            reverse=True,
        )
        items = items[offset:offset + limit]
    else:
        model = _TYPE_MODEL.get(qtype)
        if not model:
            return jsonify({"error": f"Type inconnu: {qtype}", "status": 400}), 400
        items, total = _query_for_type(model, user_id, limit, offset)

    return jsonify({
        "data":   [_serialize(it) for it in items],
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "type":   qtype,
        "status": 200,
    })


@bp.get("/history/export")
def export_history():
    """
    GET /api/history/export?type=all|zone_analysis|forecast|roi|report&format=json|csv

    CSV columns are derived from the union of all serialised keys, sorted
    alphabetically so the output is stable across exports.
    """
    user_id = _get_user_id()
    qtype = (request.args.get("type") or "all").lower()

    rows_out: list[dict] = []
    targets = _TYPE_MODEL.values() if qtype == "all" else [_TYPE_MODEL.get(qtype)]
    targets = [m for m in targets if m is not None]

    for model in targets:
        try:
            rows, _ = _query_for_type(model, user_id, limit=10_000, offset=0)
            for r in rows:
                rows_out.append(_serialize(r))
        except Exception as exc:
            logger.warning("history export skip %s: %s", model.__name__, exc)

    fmt = (request.args.get("format") or "json").lower()
    if fmt == "csv":
        buf = io.StringIO()
        if rows_out:
            keys = sorted({k for r in rows_out for k in r.keys()})
            w = csv.DictWriter(buf, fieldnames=keys)
            w.writeheader()
            for r in rows_out:
                w.writerow({k: r.get(k) for k in keys})
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=history.csv"},
        )
    return jsonify({"data": rows_out, "total": len(rows_out), "status": 200})


@bp.get("/history/<int:item_id>")
def get_history_item(item_id: int):
    """GET /api/history/<id>?type=zone_analysis|forecast|roi|report"""
    qtype = (request.args.get("type") or "").lower()
    model = _TYPE_MODEL.get(qtype)
    if not model:
        return jsonify({"error": "Paramètre 'type' requis (zone_analysis|forecast|roi|report)"}), 400
    user_id = _get_user_id()
    item = model.query.filter_by(id=item_id).first()
    if not item:
        return jsonify({"error": "Not found", "status": 404}), 404
    if hasattr(item, "user_id") and user_id is not None and item.user_id != user_id:
        return jsonify({"error": "Forbidden", "status": 403}), 403
    return jsonify({"data": _serialize(item), "status": 200})


@bp.delete("/history/<int:item_id>")
def delete_history_item(item_id: int):
    """DELETE /api/history/<id>?type=zone_analysis|forecast|roi|report"""
    qtype = (request.args.get("type") or "").lower()
    model = _TYPE_MODEL.get(qtype)
    if not model:
        return jsonify({"error": "Paramètre 'type' requis"}), 400
    user_id = _get_user_id()
    item = model.query.filter_by(id=item_id).first()
    if not item:
        return jsonify({"error": "Not found", "status": 404}), 404
    if hasattr(item, "user_id") and user_id is not None and item.user_id != user_id:
        return jsonify({"error": "Forbidden", "status": 403}), 403
    try:
        db.session.delete(item)
        db.session.commit()
        return jsonify({"status": 200, "deleted": True, "id": item_id})
    except Exception as exc:
        db.session.rollback()
        logger.exception("history delete failed: %s", exc)
        return jsonify({"error": str(exc), "status": 500}), 500