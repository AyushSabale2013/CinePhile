
import os
from datetime import timedelta


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///cinephile.db")

    # Support legacy PostgreSQL URLs.
    if url.startswith("postgres://"):
        url = url.replace(
            "postgres://",
            "postgresql+psycopg2://",
            1,
        )
    # Explicitly use psycopg2 for standard PostgreSQL URLs.
    elif url.startswith("postgresql://"):
        url = url.replace(
            "postgresql://",
            "postgresql+psycopg2://",
            1,
        )

    return url


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")

    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PERMANENT_SESSION_LIFETIME = timedelta(days=365)
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_HTTPONLY = True

    TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()
