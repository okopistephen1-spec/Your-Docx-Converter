from unittest.mock import patch

import pytest
from flask import Flask

from app import app
from database import db
from models import User, UserSession
from services.google_auth import verify_google_id_token


VALID_GOOGLE_CLAIMS = {
    "sub": "google-user-123",
    "iss": "accounts.google.com",
    "aud": "test-client-id",
    "email": "Alice@example.com",
    "email_verified": True,
    "name": "Alice Example",
    "given_name": "Alice",
    "picture": "https://example.com/avatar.jpg",
}


def test_missing_token_is_rejected():
    with app.test_client() as client:
        response = client.post("/api/auth/google", json={})
        assert response.status_code == 400
        assert response.get_json()["error"] == "Google ID token is required."


def test_empty_token_is_rejected():
    with app.test_client() as client:
        response = client.post("/api/auth/google", json={"id_token": "   "})
        assert response.status_code == 400
        assert response.get_json()["error"] == "Google ID token is required."


def test_malformed_token_is_rejected():
    with app.test_client() as client:
        with patch("services.google_auth.verify_google_id_token", side_effect=ValueError("Invalid Google ID token.")):
            response = client.post("/api/auth/google", json={"id_token": "not-a-real-token"})
            assert response.status_code == 401
            assert response.get_json()["error"] == "Invalid Google ID token."


def test_invalid_signature_is_rejected_by_verifier():
    with patch("services.google_auth.id_token.verify_oauth2_token", side_effect=ValueError("bad signature")):
        with pytest.raises(ValueError, match="Invalid Google ID token"):
            verify_google_id_token("bad-token", client_id="test-client-id")


def test_incorrect_audience_is_rejected_by_verifier():
    with patch("services.google_auth.id_token.verify_oauth2_token", side_effect=ValueError("aud mismatch")):
        with pytest.raises(ValueError, match="Invalid Google ID token"):
            verify_google_id_token("bad-token", client_id="test-client-id")


def test_incorrect_issuer_is_rejected_by_verifier():
    with patch("services.google_auth.id_token.verify_oauth2_token", return_value={**VALID_GOOGLE_CLAIMS, "iss": "https://evil.example.com"}):
        with pytest.raises(ValueError, match="Invalid Google token issuer"):
            verify_google_id_token("token", client_id="test-client-id")


def test_expired_token_is_rejected_by_verifier():
    with patch("services.google_auth.id_token.verify_oauth2_token", side_effect=ValueError("token expired")):
        with pytest.raises(ValueError, match="Invalid Google ID token"):
            verify_google_id_token("expired-token", client_id="test-client-id")


def test_missing_required_claims_are_rejected_by_verifier():
    with patch("services.google_auth.id_token.verify_oauth2_token", return_value={
        "sub": "google-user-123",
        "iss": "accounts.google.com",
        "email_verified": True,
    }):
        with pytest.raises(ValueError, match="Google email is missing"):
            verify_google_id_token("token", client_id="test-client-id")


def test_valid_token_is_verified():
    with patch("services.google_auth.id_token.verify_oauth2_token", return_value=VALID_GOOGLE_CLAIMS):
        payload = verify_google_id_token("valid-token", client_id="test-client-id")

    assert payload["sub"] == "google-user-123"
    assert payload["email"] == "alice@example.com"
    assert payload["name"] == "Alice Example"
    assert payload["given_name"] == "Alice"
    assert payload["picture"] == "https://example.com/avatar.jpg"


def test_valid_token_route_returns_minimal_verified_payload(auth_test_app):
    with patch("services.google_auth.verify_google_id_token", return_value={
        "sub": "google-user-123",
        "email": "alice@example.com",
        "name": "Alice Example",
        "given_name": "Alice",
        "picture": "https://example.com/avatar.jpg",
    }):
        with auth_test_app.test_client() as client:
            response = client.post("/api/auth/google", json={"id_token": "valid-google-id-token"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["verified"] is True
    assert payload["user"]["sub"] == "google-user-123"
    assert payload["user"]["email"] == "alice@example.com"
    assert payload["user"]["name"] == "Alice Example"
    assert "id_token" not in str(payload)


def test_missing_google_client_id_is_rejected():
    with patch.dict("os.environ", {}, clear=False):
        import os
        if "GOOGLE_CLIENT_ID" in os.environ:
            del os.environ["GOOGLE_CLIENT_ID"]
        with pytest.raises(RuntimeError, match="not configured"):
            verify_google_id_token("token")


@pytest.fixture
def auth_test_app():
    test_app = Flask(__name__)
    test_app.config["TESTING"] = True
    test_app.config["SECRET_KEY"] = "test-secret-key"
    test_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    test_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    test_app.config["SESSION_COOKIE_SECURE"] = False
    test_app.config["AUTH_SESSION_COOKIE"] = "docx_auth"
    test_app.config["AUTH_SESSION_TTL_SECONDS"] = 30 * 24 * 60 * 60

    db.init_app(test_app)
    test_app.register_blueprint(__import__("services.google_auth", fromlist=["google_auth_bp"]).google_auth_bp)

    with test_app.app_context():
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()


def test_registers_new_google_user_and_sets_auth_cookie(auth_test_app):
    with patch("services.google_auth.id_token.verify_oauth2_token", return_value={
        "sub": "google-new-user-1",
        "iss": "accounts.google.com",
        "email": "Alice@Example.com",
        "email_verified": True,
        "name": "Alice Example",
        "given_name": "Alice",
        "picture": "https://example.com/avatar.jpg",
    }):
        with auth_test_app.test_client() as client:
            response = client.post("/api/auth/google", json={"id_token": "valid-google-token"})

    assert response.status_code == 200
    assert response.get_json()["user"]["email"] == "alice@example.com"
    user = User.query.filter_by(google_sub="google-new-user-1").one()
    assert user.email == "alice@example.com"
    assert user.last_login_at is not None
    assert UserSession.query.filter_by(user_id=user.id).count() == 1
    assert "docx_auth=" in response.headers["Set-Cookie"]
    assert "HttpOnly" in response.headers["Set-Cookie"]


def test_existing_google_user_signin_updates_profile(auth_test_app):
    existing = User(
        google_sub="google-existing-1",
        email="existing@example.com",
        name="Old Name",
        given_name="Old",
        picture_url="https://example.com/old.png",
    )
    db.session.add(existing)
    db.session.commit()

    with patch("services.google_auth.id_token.verify_oauth2_token", return_value={
        "sub": "google-existing-1",
        "iss": "accounts.google.com",
        "email": "Existing@Example.com",
        "email_verified": True,
        "name": "Updated Name",
        "given_name": "Updated",
        "picture": "https://example.com/new.png",
    }):
        with auth_test_app.test_client() as client:
            response = client.post("/api/auth/google", json={"id_token": "signin-token"})

    assert response.status_code == 200
    updated = User.query.filter_by(google_sub="google-existing-1").one()
    assert updated.email == "existing@example.com"
    assert updated.name == "Updated Name"
    assert updated.given_name == "Updated"
    assert updated.picture_url == "https://example.com/new.png"
    assert updated.last_login_at is not None


def test_conflicting_email_with_different_google_identity_is_rejected(auth_test_app):
    existing = User(
        google_sub="google-other-user",
        email="alice@example.com",
        name="Alice Existing",
    )
    db.session.add(existing)
    db.session.commit()

    with patch("services.google_auth.id_token.verify_oauth2_token", return_value={
        "sub": "google-new-user-2",
        "iss": "accounts.google.com",
        "email": "alice@example.com",
        "email_verified": True,
        "name": "Alice New",
        "given_name": "Alice",
        "picture": "https://example.com/new.png",
    }):
        with auth_test_app.test_client() as client:
            response = client.post("/api/auth/google", json={"id_token": "conflict-token"})

    assert response.status_code == 409
    assert User.query.filter_by(google_sub="google-new-user-2").count() == 0


def test_me_and_logout_require_valid_session(auth_test_app):
    with patch("services.google_auth.id_token.verify_oauth2_token", return_value={
        "sub": "google-me-user",
        "iss": "accounts.google.com",
        "email": "me@example.com",
        "email_verified": True,
        "name": "Me User",
        "given_name": "Me",
        "picture": "https://example.com/me.png",
    }):
        with auth_test_app.test_client() as client:
            login_response = client.post("/api/auth/google", json={"id_token": "me-token"})
            cookie_value = login_response.headers["Set-Cookie"].split("docx_auth=")[1].split(";", 1)[0]
            csrf_token = login_response.get_json()["csrf_token"]

            me_response = client.get("/api/auth/me", headers={"X-CSRF-Token": csrf_token}, cookies={"docx_auth": cookie_value})
            assert me_response.status_code == 200
            assert me_response.get_json()["user"]["email"] == "me@example.com"

            logout_response = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token}, cookies={"docx_auth": cookie_value})
            assert logout_response.status_code == 200

            after_logout = client.get("/api/auth/me", headers={"X-CSRF-Token": csrf_token}, cookies={"docx_auth": cookie_value})
            assert after_logout.status_code == 401


def test_missing_or_invalid_csrf_is_rejected(auth_test_app):
    with patch("services.google_auth.id_token.verify_oauth2_token", return_value={
        "sub": "google-csrf-user",
        "iss": "accounts.google.com",
        "email": "csrf@example.com",
        "email_verified": True,
        "name": "CSRF User",
        "given_name": "CSRF",
        "picture": "https://example.com/csrf.png",
    }):
        with auth_test_app.test_client() as client:
            login_response = client.post("/api/auth/google", json={"id_token": "csrf-token"})
            cookie_value = login_response.headers["Set-Cookie"].split("docx_auth=")[1].split(";", 1)[0]

            missing = client.post("/api/auth/logout", cookies={"docx_auth": cookie_value})
            assert missing.status_code == 403

            bad = client.post("/api/auth/logout", headers={"X-CSRF-Token": "bad-token"}, cookies={"docx_auth": cookie_value})
            assert bad.status_code == 403


def test_production_requires_secret_key():
    import app as app_module
    with patch.dict("os.environ", {"APP_ENV": "production", "SECRET_KEY": ""}, clear=False):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            app_module.resolve_secret_key()
