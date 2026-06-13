"""Routes /api/reports — PDF generation & persistence."""

import json
import logging
import os
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file
from utils.reports import ReportGenerator
from db_models import db, Report

logger = logging.getLogger(__name__)
bp = Blueprint("reports", __name__)

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'reports')
os.makedirs(REPORTS_DIR, exist_ok=True)


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
        import jwt
        from config import JWT_SECRET, JWT_ALGORITHM
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


@bp.post("/reports/generate")
def generate_report():
    try:
        body = request.get_json(silent=True) or {}

        report_type = (body.get("report_type") or "investor").lower().strip()
        if report_type not in ("investor", "government", "technical"):
            return jsonify({"error": f"Unsupported report_type '{report_type}'", "status": 400}), 400

        wilaya_name = body.get("wilaya") or body.get("wilaya_name")
        region = body.get("region")

        try:
            power_kwc = float(body.get("power_kwc") or body.get("puissance_kwc") or 100.0)
        except (TypeError, ValueError):
            power_kwc = 100.0
        if power_kwc <= 0:
            power_kwc = 100.0

        if report_type == "investor" and not wilaya_name:
            return jsonify({"error": "wilaya is required for investor report", "status": 400}), 400
        if report_type == "technical" and not wilaya_name:
            return jsonify({"error": "wilaya is required for technical report", "status": 400}), 400
        if report_type == "government" and not (region or wilaya_name):
            return jsonify({"error": "region or wilaya is required for government report", "status": 400}), 400

        report_gen = ReportGenerator()
        pdf_buffer = report_gen.generate(
            report_type=report_type,
            wilaya=wilaya_name,
            region=region,
            power_kwc=power_kwc,
            roi_data=body.get("roi_data") or {},
            title=body.get("title"),
        )

        user_id = _get_user_id()
        report_id = None

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        sanitized_title = "".join(
            c for c in body.get("title", "report") if c.isalnum() or c in (' ', '-', '_')
        ).replace(' ', '_')
        filename = f"report_{user_id or 'anon'}_{sanitized_title}_{timestamp}.pdf"
        pdf_path = os.path.join(REPORTS_DIR, filename)

        try:
            with open(pdf_path, 'wb') as f:
                f.write(pdf_buffer.getvalue())
        except Exception as file_err:
            logger.error(f"Failed to write PDF to disk: {file_err}")
            return jsonify({"error": f"Failed to save report: {file_err}", "status": 500}), 500

        if user_id:
            try:
                record = Report(
                    user_id=user_id,
                    title=body.get("title") or f"Rapport {report_type} — {wilaya_name or region or 'Algérie'}",
                    report_type=report_type,
                    wilaya_name=wilaya_name or region or "",
                    capacity_mw=power_kwc / 1000.0,  # schema stores MW, input is kWc
                    data_json=json.dumps({
                        'power_kwc': power_kwc,
                        'region': region,
                        'roi_data': body.get("roi_data", {}),
                    }),
                    pdf_path=pdf_path,
                )
                db.session.add(record)
                db.session.commit()
                report_id = record.id
            except Exception as db_err:
                logger.warning(f"DB save failed, PDF still on disk: {db_err}")
                db.session.rollback()

        try:
            from services.admin_service import log_activity
            log_activity("rapport", user_id=_get_user_id(),
                         details=f"type:{report_type} wilaya:{wilaya_name or region or '—'}")
        except Exception:
            pass

        pdf_buffer.seek(0)
        response = send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"solar_report_{datetime.utcnow().strftime('%Y%m%d')}.pdf",
        )
        if report_id:
            response.headers['X-Report-Id'] = str(report_id)
        return response

    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        return jsonify({"error": str(e), "status": 400}), 400


@bp.get("/reports")
def list_reports():
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required', 'status': 401}), 401

    reports = Report.query.filter_by(user_id=user_id)\
        .order_by(Report.generated_at.desc()).all()

    return jsonify({'data': [r.to_dict() for r in reports], 'total': len(reports), 'status': 200})


@bp.get("/reports/<int:report_id>")
def get_report(report_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required', 'status': 401}), 401

    report = Report.query.filter_by(id=report_id, user_id=user_id).first()
    if not report:
        return jsonify({"error": "Not found", "status": 404}), 404

    return jsonify({'data': report.to_dict(), 'status': 200})


@bp.delete("/reports/<int:report_id>")
def delete_report(report_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required', 'status': 401}), 401

    report = Report.query.filter_by(id=report_id, user_id=user_id).first()
    if not report:
        return jsonify({"error": "Not found", "status": 404}), 404

    if report.pdf_path and os.path.exists(report.pdf_path):
        try:
            os.remove(report.pdf_path)
        except Exception as e:
            logger.warning(f"Failed to delete PDF file: {e}")

    db.session.delete(report)
    db.session.commit()
    return jsonify({'message': 'Deleted', 'status': 200})


@bp.get("/reports/<int:report_id>/download")
def download_report(report_id):
    user_id = _get_user_id()
    if not user_id:
        return jsonify({'error': 'Authentication required', 'status': 401}), 401

    report = Report.query.filter_by(id=report_id, user_id=user_id).first()
    if not report:
        return jsonify({"error": "Not found", "status": 404}), 404

    if not report.pdf_path or not os.path.exists(report.pdf_path):
        return jsonify({"error": "PDF file not found on disk", "status": 404}), 404

    try:
        return send_file(
            report.pdf_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{report.title or 'report'}_{report_id}.pdf",
        )
    except Exception as e:
        logger.error(f"Failed to send report file: {e}")
        return jsonify({"error": str(e), "status": 500}), 500