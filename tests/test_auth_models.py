import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from database import db
from models import User, UserSession


@pytest.fixture
def auth_db():
    from flask import Flask

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    with app.app_context():
        db.create_all()
        yield db
        db.session.remove()
        db.drop_all()


def test_user_model_creates_uuid_and_normalizes_email(auth_db):
    user = User(
        google_sub="google-sub-123",
        email="Alice.Smith@Example.com",
        name="Alice Smith",
        given_name="Alice",
        picture_url="https://example.com/avatar.png",
    )

    db.session.add(user)
    db.session.commit()

    assert isinstance(user.id, uuid.UUID)
    assert user.email == "alice.smith@example.com"
    assert user.name == "Alice Smith"
    assert user.given_name == "Alice"
    assert user.picture_url == "https://example.com/avatar.png"
    assert user.welcome_email_sent is False


def test_google_sub_and_email_are_unique(auth_db):
    first = User(
        google_sub="google-sub-unique",
        email="first@example.com",
        name="First User",
    )
    second = User(
        google_sub="google-sub-unique",
        email="second@example.com",
        name="Second User",
    )
    third = User(
        google_sub="google-sub-unique-two",
        email="first@example.com",
        name="Third User",
    )

    db.session.add(first)
    db.session.commit()

    db.session.add(second)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    db.session.add(third)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_user_session_model_creates_and_tracks_expiration(auth_db):
    user = User(google_sub="session-google-sub", email="session@example.com", name="Session User")
    db.session.add(user)
    db.session.commit()

    now = datetime.now(timezone.utc)
    session = UserSession(
        user_id=user.id,
        session_token_hash="hash-abc-123",
        created_at=now,
        expires_at=now + timedelta(days=7),
        last_seen_at=now,
        user_agent="Mozilla/5.0",
    )

    db.session.add(session)
    db.session.commit()

    assert session.user_id == user.id
    assert session.session_token_hash == "hash-abc-123"
    assert session.expires_at > now
    assert session.revoked_at is None
    assert session.user_agent == "Mozilla/5.0"
    assert session in user.sessions


def test_user_session_hash_must_be_unique(auth_db):
    user = User(google_sub="hash-sub-1", email="hash1@example.com", name="Hash User")
    db.session.add(user)
    db.session.commit()

    first = UserSession(user_id=user.id, session_token_hash="unique-hash")
    second = UserSession(user_id=user.id, session_token_hash="unique-hash")

    db.session.add(first)
    db.session.commit()

    db.session.add(second)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_user_and_user_session_metadata_are_registered(auth_db):
    assert "users" in db.metadata.tables
    assert "user_sessions" in db.metadata.tables
