from app.main import app


def test_vercel_preview_origin_regex_is_configured():
    cors_middleware = next(
        middleware for middleware in app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )

    assert cors_middleware.kwargs["allow_origin_regex"] == (
        r"^https://mailmind-ai-email-platform[a-zA-Z0-9-]*\.vercel\.app$"
    )
    assert "http://localhost:5173" in cors_middleware.kwargs["allow_origins"]