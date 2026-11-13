import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests
from google.oauth2 import id_token
from sqlalchemy.exc import IntegrityError

from database import db
from models import User, UserSession

google_auth_bp = Blueprint("google_auth", __name__, url_prefix="/api/auth")

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
CSRF_HEADER_NAME = "X-CSRF-Token"
AUTH_COOKIE_NAME = "docx_auth"
CSRF_COOKIE_NAME = "docx_csrf"
DEFAULT_AUTH_TTL_SECONDS = 30 * 24 * 60 * 60


def _utc_now():
    return datetime.now(timezone.utc)


def _session_ttl_seconds():
    return int(current_app.config.get("AUTH_SESSION_TTL_SECONDS", DEFAULT_AUTH_TTL_SECONDS))


def _cookie_secure():
    return bool(current_app.config.get("SESSION_COOKIE_SECURE", False))


def _hash_value(value):
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _compute_csrf_token(session_token):
    secret_key = current_app.config.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY is not configured.")
    return hmac.new(secret_key.encode("utf-8"), session_token.encode("utf-8"), hashlib.sha256).hexdigest()


def _get_auth_cookie_name():
    return current_app.config.get("AUTH_SESSION_COOKIE", AUTH_COOKIE_NAME)


def _cookie_expiration():
    return _utc_now() + timedelta(seconds=_session_ttl_seconds())


def _user_response_payload(user):
    return {
        "sub": user.google_sub,
        "email": user.email,
        "name": user.name,
        "given_name": user.given_name,
        "picture": user.picture_url,
    }


def _set_auth_cookies(response, session_token, csrf_token):
    ttl_seconds = _session_ttl_seconds()
    expires = _cookie_expiration()
    response.set_cookie(
        key=_get_auth_cookie_name(),
        value=session_token,
        max_age=ttl_seconds,
        expires=expires,
        httponly=True,
        secure=_cookie_secure(),
        samesite="None",
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=ttl_seconds,
        expires=expires,
        httponly=False,
        secure=_cookie_secure(),
        samesite="None",
        path="/",
    )
    return response


def _clear_auth_cookies(response):
    response.set_cookie(key=_get_auth_cookie_name(), value="", expires=0, httponly=True, secure=_cookie_secure(), samesite="None", path="/")
    response.set_cookie(key=CSRF_COOKIE_NAME, value="", expires=0, httponly=False, secure=_cookie_secure(), samesite="None", path="/")
    return response


def _read_auth_token():
    token = request.cookies.get(_get_auth_cookie_name(), "")
    token = token.strip()
    return token if token else None


def _read_session_from_auth_token(raw_token):
    if not raw_token:
        return None
    session = UserSession.query.filter_by(session_token_hash=_hash_value(raw_token)).first()
    if session is None:
        return None
    if session.revoked_at is not None:
        return None
    if session.expires_at <= _utc_now():
        return None
    session.last_seen_at = _utc_now()
    db.session.add(session)
    db.session.commit()
    return session


def _current_authenticated_session():
    token = _read_auth_token()
    if not token:
        return None
    session = _read_session_from_auth_token(token)
    if session is None:
        return None
    return session


def _validate_csrf_token(raw_auth_token):
    if not raw_auth_token:
        return False
    header_token = request.headers.get(CSRF_HEADER_NAME, "")
    if not header_token or not header_token.strip():
        return False
    expected_token = _compute_csrf_token(raw_auth_token)
    return hmac.compare_digest(header_token.strip(), expected_token)


def verify_google_id_token(id_token_value, client_id=None):
    if not isinstance(id_token_value, str):
        raise ValueError("Google ID token is required.")

    token = id_token_value.strip()
    if not token:
        raise ValueError("Google ID token is required.")

    configured_client_id = client_id or os.environ.get("GOOGLE_CLIENT_ID")
    if not configured_client_id:
        raise RuntimeError("Google authentication is not configured.")

    try:
        claims = id_token.verify_oauth2_token(token, requests.Request(), configured_client_id)
    except (ValueError, GoogleAuthError) as exc:
        raise ValueError("Invalid Google ID token.") from exc

    issuer = claims.get("iss")
    if issuer not in GOOGLE_ISSUERS:
        raise ValueError("Invalid Google token issuer.")

    if not claims.get("sub"):
        raise ValueError("Google identity is missing.")

    if not claims.get("email"):
        raise ValueError("Google email is missing.")

    if claims.get("email_verified") is not True:
        raise ValueError("Google email is not verified.")

    return {
        "sub": claims["sub"],
        "email": claims["email"].strip().lower(),
        "name": claims.get("name"),
        "given_name": claims.get("given_name"),
        "picture": claims.get("picture"),
    }


@google_auth_bp.route("/google", methods=["POST"])
def google_auth():
    payload = request.get_json(silent=True) or {}
    token = payload.get("id_token")

    if not isinstance(token, str) or not token.strip():
        return jsonify({"error": "Google ID token is required."}), 400

    try:
        verified_identity = verify_google_id_token(token)
    except RuntimeError:
        return jsonify({"error": "Google authentication is not configured."}), 500
    except ValueError:
        return jsonify({"error": "Invalid Google ID token."}), 401

    normalized_email = verified_identity["email"]
    user = User.query.filter_by(google_sub=verified_identity["sub"]).first()

    if user is None:
        existing_email_user = User.query.filter_by(email=normalized_email).first()
        if existing_email_user and existing_email_user.google_sub != verified_identity["sub"]:
            return jsonify({"error": "Account conflict detected."}), 409
        user = User(
            google_sub=verified_identity["sub"],
            email=normalized_email,
            name=verified_identity.get("name") or verified_identity.get("email") or "Google User",
            given_name=verified_identity.get("given_name"),
            picture_url=verified_identity.get("picture"),
        )
        db.session.add(user)
    else:
        if existing_email_user := User.query.filter_by(email=normalized_email).first():
            if existing_email_user.id != user.id:
                return jsonify({"error": "Account conflict detected."}), 409
        user.name = verified_identity.get("name") or user.name or verified_identity.get("email") or "Google User"
        user.given_name = verified_identity.get("given_name") or user.given_name
        user.picture_url = verified_identity.get("picture") or user.picture_url
        user.email = normalized_email

    user.last_login_at = _utc_now()

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Account registration failed."}), 409

    session_token = secrets.token_urlsafe(32)
    csrf_token = _compute_csrf_token(session_token)
    session = UserSession(
        user_id=user.id,
        session_token_hash=_hash_value(session_token),
        created_at=_utc_now(),
        expires_at=_utc_now() + timedelta(seconds=_session_ttl_seconds()),
        last_seen_at=_utc_now(),
        user_agent=request.user_agent.string[:512] if request.user_agent else None,
    )
    db.session.add(session)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Session creation failed."}), 409

    response = jsonify({
        "verified": True,
        "user": _user_response_payload(user),
        "csrf_token": csrf_token,
    })
    return _set_auth_cookies(response, session_token, csrf_token)


@google_auth_bp.route("/me", methods=["GET"])
def current_user():
    session = _current_authenticated_session()
    if session is None or session.user is None:
        return jsonify({"error": "Unauthorized."}), 401

    raw_token = _read_auth_token()
    csrf_token = _compute_csrf_token(raw_token) if raw_token else None
    return jsonify({"user": _user_response_payload(session.user), "csrf_token": csrf_token})


@google_auth_bp.route("/logout", methods=["POST"])
def logout():
    raw_token = _read_auth_token()
    if raw_token is None:
        return jsonify({"error": "Unauthorized."}), 401

    if not _validate_csrf_token(raw_token):
        return jsonify({"error": "Invalid CSRF token."}), 403

    session = _read_session_from_auth_token(raw_token)
    if session is None:
        return jsonify({"error": "Unauthorized."}), 401

    session.revoked_at = _utc_now()
    db.session.add(session)
    db.session.commit()

    response = jsonify({"logged_out": True})
    return _clear_auth_cookies(response)


@google_auth_bp.route("/csrf", methods=["GET"])
def csrf_token():
    raw_token = _read_auth_token()
    if raw_token is None:
        return jsonify({"error": "Unauthorized."}), 401
    session = _read_session_from_auth_token(raw_token)
    if session is None:
        return jsonify({"error": "Unauthorized."}), 401
    return jsonify({"csrf_token": _compute_csrf_token(raw_token)})
