"""
Routes /auth (Refactored with real JWT + httpOnly cookies)
"""

import os
import json
import logging
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import jwt
from flask import Blueprint, request, jsonify, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_HOURS
from db_models import db, User

bp = Blueprint('auth', __name__)

logger = logging.getLogger(__name__)


def _generate_jwt(user_id: int, email: str, role: str = "user") -> str:
    """Generate a real JWT token (role included for Phase 3 / admin gating)."""
    payload = {
        "sub":   str(user_id),
        "email": email,
        "role":  role or "user",
        "iat":   datetime.now(timezone.utc),
        "exp":   datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        "jti":   secrets.token_hex(16),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _verify_jwt(token: str) -> dict | None:
    """Verify a JWT token and return the payload."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT expired")
        return None
    except jwt.InvalidTokenError:
        logger.warning("Invalid JWT token")
        return None


def _set_auth_cookie(response, token: str):
    """Set httpOnly secure cookie with the JWT."""
    is_prod = os.environ.get("FLASK_ENV") == "production"
    # For production: SameSite=None requires Secure=True
    # For development: Use SameSite=Lax (allows same-site requests like localhost:3000 -> localhost:5000)
    response.set_cookie(
        "auth_token",
        token,
        httponly=True,
        secure=is_prod,
        samesite="Lax" if not is_prod else "None",
        max_age=JWT_EXPIRATION_HOURS * 3600,
        path="/",
    )


def _clear_auth_cookie(response):
    """Clear the auth cookie."""
    response.delete_cookie("auth_token", path="/")


def _get_user_id_from_cookie() -> int | None:
    """Extract user_id from httpOnly auth cookie or Authorization header."""
    token = request.cookies.get("auth_token")
    token_source = "cookie"
    
    # Fallback to Authorization header for API clients
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            token_source = "header"
    
    if not token:
        logger.debug(
            f"No auth token found. "
            f"Cookies: {list(request.cookies.keys())}, "
            f"Authorization: {bool(request.headers.get('Authorization'))}"
        )
        return None
    
    payload = _verify_jwt(token)
    if payload:
        subject = payload.get("sub")
        try:
            user_id = int(subject)
            logger.info(f"Auth token verified from {token_source}, user_id={user_id}")
            return user_id
        except (TypeError, ValueError):
            logger.warning(f"Invalid user_id in token: {subject}")
            return None
    else:
        logger.warning(f"Token verification failed (from {token_source})")
        return None


@bp.post("/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")

    if not name:
        return jsonify({"error": "Name is required", "status": 400}), 400
    if not email or not password:
        return jsonify({"error": "Email and password required", "status": 400}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters", "status": 400}), 400
    if len(name) < 2 or len(name) > 100:
        return jsonify({"error": "Name must be between 2 and 100 characters", "status": 400}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "User already exists", "status": 409}), 409

    new_user = User(
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
        role='user',  # Phase 1 — default role for every newly-registered user
    )
    db.session.add(new_user)
    db.session.commit()

    token = _generate_jwt(new_user.id, new_user.email, getattr(new_user, 'role', 'user'))
    resp = make_response(jsonify({
        "data":         new_user.to_public_dict(),
        "access_token": token,
        "message":      "User created successfully",
        "status":       201,
    }))
    _set_auth_cookie(resp, token)
    return resp, 201


@bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password required", "status": 400}), 400

    user = User.query.filter_by(email=email).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid credentials", "status": 401}), 401

    # Phase 3 — deny login to deactivated accounts
    if int(getattr(user, "is_active", 1) or 0) == 0:
        return jsonify({"error": "account_deactivated", "status": 403}), 403

    token = _generate_jwt(user.id, user.email, getattr(user, 'role', 'user'))
    # Lazy month rollover: reset counters if the calendar month changed.
    try:
        from services.plan_service import reset_counters_if_new_month
        reset_counters_if_new_month(user)
    except Exception:  # noqa: BLE001
        pass
    # Phase 3 — update last_login + log
    try:
        from datetime import datetime as _dt
        user.last_login = _dt.utcnow()
        from db_models import db as _db
        _db.session.commit()
    except Exception:  # noqa: BLE001
        pass
    try:
        from services.admin_service import log_activity
        log_activity("login", user_id=user.id, details=f"email={user.email}")
    except Exception:  # noqa: BLE001
        pass
    resp = make_response(jsonify({
        "data":         user.to_public_dict(),
        "access_token": token,
        "message":      "Login successful",
        "status":       200,
    }))
    _set_auth_cookie(resp, token)
    return resp, 200


@bp.post("/auth/logout")
def logout():
    resp = make_response(jsonify({"message": "Logged out", "status": 200}))
    _clear_auth_cookie(resp)
    return resp, 200


@bp.get("/auth/verify")
def verify():
    """Verify current session token."""
    user_id = _get_user_id_from_cookie()
    if user_id:
        user = User.query.get(user_id)
        if user:
            try:
                from services.plan_service import reset_counters_if_new_month
                reset_counters_if_new_month(user)
            except Exception:  # noqa: BLE001
                pass
            return jsonify({
                "data":          user.to_public_dict(),
                "authenticated": True,
                "status":        200,
            })
        # Token valide mais user supprimé de la DB — effacer le cookie
        resp = make_response(jsonify({"authenticated": False, "status": 401}))
        _clear_auth_cookie(resp)
        return resp, 401
    return jsonify({"authenticated": False, "status": 401}), 401


@bp.get("/auth/user")
def get_current_user():
    """Get current authenticated user info."""
    user_id = _get_user_id_from_cookie()
    if not user_id:
        return jsonify({"error": "Not authenticated", "status": 401}), 401
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found", "status": 404}), 404
    try:
        from services.plan_service import reset_counters_if_new_month
        reset_counters_if_new_month(user)
    except Exception:  # noqa: BLE001
        pass
    return jsonify({"data": user.to_public_dict(), "status": 200})