import os
from urllib.parse import urlsplit

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text


db = SQLAlchemy()
migrate = Migrate()

from models import User, UserSession  # noqa: F401


def normalize_database_url(database_url):
    if not database_url:
        return None

    parsed = urlsplit(database_url)
    scheme = parsed.scheme.lower()

    if scheme in {"postgres", "postgresql"}:
        return parsed._replace(scheme="postgresql+psycopg").geturl()

    if scheme == "postgresql+psycopg":
        return database_url

    return database_url


def init_database(app):
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        app.config["DATABASE_CONFIGURED"] = False
        app.config["DATABASE_STATUS"] = "Database not configured. Set DATABASE_URL to enable database-backed features."
        app.logger.warning("Database not configured: set DATABASE_URL to enable database-backed features.")
        return False

    normalized_url = normalize_database_url(database_url)
    app.config["SQLALCHEMY_DATABASE_URI"] = normalized_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    app.config["DATABASE_CONFIGURED"] = True

    db.init_app(app)
    migrate.init_app(app, db)
    app.config["DATABASE_STATUS"] = "Database configured."
    return True


def database_status():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return {
            "configured": False,
            "connected": False,
            "status": "Database not configured. Set DATABASE_URL to enable database-backed features.",
        }

    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {
            "configured": True,
            "connected": True,
            "status": "Database connection successful.",
        }
    except Exception:
        return {
            "configured": True,
            "connected": False,
            "status": "Database connection failed.",
        }
