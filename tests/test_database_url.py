from database import normalize_database_url


def test_postgres_scheme_is_rewritten_for_psycopg():
    original = "postgres://user:pass@db.example.com:5432/app_db?sslmode=require"
    expected = "postgresql+psycopg://user:pass@db.example.com:5432/app_db?sslmode=require"
    assert normalize_database_url(original) == expected


def test_postgresql_scheme_is_rewritten_for_psycopg():
    original = "postgresql://user:pass@db.example.com:5432/app_db?sslmode=require"
    expected = "postgresql+psycopg://user:pass@db.example.com:5432/app_db?sslmode=require"
    assert normalize_database_url(original) == expected


def test_already_normalized_url_is_preserved():
    original = "postgresql+psycopg://user:pass@db.example.com:5432/app_db?sslmode=require"
    assert normalize_database_url(original) == original


def test_missing_url_returns_none():
    assert normalize_database_url(None) is None
    assert normalize_database_url("") is None


def test_query_parameters_are_preserved():
    original = "postgres://user:pass@db.example.com:5432/app_db?sslmode=require&application_name=myapp"
    expected = "postgresql+psycopg://user:pass@db.example.com:5432/app_db?sslmode=require&application_name=myapp"
    assert normalize_database_url(original) == expected


def test_unsupported_scheme_is_left_unchanged():
    original = "sqlite:///tmp/app.db"
    assert normalize_database_url(original) == original
