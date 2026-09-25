from app.db.session import _async_database_url
from app.config import Settings


def test_sqlite_url_is_preserved_and_async():
    assert _async_database_url("sqlite+aiosqlite:///./email_classifier.db") == (
        "sqlite+aiosqlite:///./email_classifier.db"
    )


def test_postgresql_urls_use_asyncpg():
    assert _async_database_url("postgresql://user:password@host/db") == (
        "postgresql+asyncpg://user:password@host/db"
    )
    assert _async_database_url("postgres://user:password@host/db") == (
        "postgresql+asyncpg://user:password@host/db"
    )


def test_render_settings_read_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:password@host/db")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("CORS_ORIGINS", "https://frontend.example.com")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+asyncpg://user:password@host/db"
    assert settings.gemini_api_key == "test-gemini-key"
    assert settings.cors_origins_list == ["https://frontend.example.com"]