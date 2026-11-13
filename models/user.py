import uuid
from datetime import datetime, timezone

from sqlalchemy import String, TypeDecorator
from sqlalchemy.orm import validates

from database import db


class UUIDType(TypeDecorator):
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(uuid.UUID(str(value)))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return uuid.UUID(str(value))


class UTCDateTime(TypeDecorator):
    impl = db.DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def utc_now():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(UUIDType, primary_key=True, default=uuid.uuid4, nullable=False)
    google_sub = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    given_name = db.Column(db.String(255), nullable=True)
    picture_url = db.Column(db.String(512), nullable=True)
    avatar_storage_key = db.Column(db.String(512), nullable=True)
    created_at = db.Column(UTCDateTime, default=utc_now, nullable=False)
    updated_at = db.Column(UTCDateTime, default=utc_now, onupdate=utc_now, nullable=False)
    last_login_at = db.Column(UTCDateTime, nullable=True)
    welcome_email_sent = db.Column(db.Boolean, default=False, nullable=False)

    sessions = db.relationship("UserSession", back_populates="user", cascade="all, delete-orphan")

    @validates("email")
    def normalize_email(self, key, value):
        if value is None:
            return value
        return value.strip().lower()
