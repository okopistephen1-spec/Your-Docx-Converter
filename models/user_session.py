import uuid
from datetime import datetime, timedelta, timezone

from database import db
from models.user import UTCDateTime, UUIDType


def utc_now():
    return datetime.now(timezone.utc)


class UserSession(db.Model):
    __tablename__ = "user_sessions"

    id = db.Column(UUIDType, primary_key=True, default=uuid.uuid4, nullable=False)
    user_id = db.Column(UUIDType, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_token_hash = db.Column(db.String(255), unique=True, nullable=False, index=True)
    created_at = db.Column(UTCDateTime, default=utc_now, nullable=False)
    expires_at = db.Column(UTCDateTime, default=lambda: utc_now() + timedelta(days=7), nullable=False)
    last_seen_at = db.Column(UTCDateTime, default=utc_now, onupdate=utc_now, nullable=False)
    revoked_at = db.Column(UTCDateTime, nullable=True)
    user_agent = db.Column(db.String(512), nullable=True)

    user = db.relationship("User", back_populates="sessions")

    __table_args__ = (
        db.Index("ix_user_sessions_user_expires", "user_id", "expires_at"),
    )
