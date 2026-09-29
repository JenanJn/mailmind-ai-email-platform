import logging
import threading
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import init_db
from app.main import app
from app.services.email_service import EmailService, analyze_email_in_background


@pytest_asyncio.fixture
async def client():
    import app.db.session as db_module

    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    db_module.engine = test_engine
    db_module.AsyncSessionLocal = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await test_engine.dispose()


async def register_user(client: AsyncClient, email: str) -> dict:
    response = await client.post("/auth/register", json={
        "name": "Incoming User",
        "email": email,
        "password": "pass1234",
    })
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def mock_analysis_results():
    from app.nlp.entity_extractor import ExtractedEntity
    from app.nlp.pipeline import NLPResult
    from app.priority.engine import PriorityResult

    nlp = NLPResult(
        category="Job / Career",
        category_slug="job_career",
        category_confidence=0.92,
        intent="Interview Invitation",
        entities=[ExtractedEntity("DATE", "tomorrow", 0.9, 10)],
        deadline_text="tomorrow",
    )
    priority = PriorityResult(
        score=85,
        level="high",
        urgency_level="elevated",
        action_required=True,
        explanations=["Interview within 24 hours"],
        factors_json='{"deadline_proximity": 22, "action_required": 15}',
    )
    return nlp, priority


@pytest.mark.asyncio
async def test_incoming_email_returns_pending_then_background_analysis_completes(client):
    headers = await register_user(client, "incoming@test.com")
    mock_nlp, mock_priority = mock_analysis_results()
    main_thread_id = threading.get_ident()
    analysis_thread_ids = []

    with patch("app.api.routes.emails.analyze_email_in_background", new_callable=AsyncMock) as task, \
         patch("app.services.email_service.get_pipeline") as pipeline, \
         patch("app.services.email_service.compute_priority", return_value=mock_priority), \
         patch("app.genai.reply_generator.generate_reply", return_value="Interview reply") as generate_reply:
        pipeline.return_value.process.return_value = mock_nlp
        response = await client.post("/api/emails/incoming", json={
            "sender": "hr@company.com",
            "recipient": "incoming@test.com",
            "subject": "Interview Invitation",
            "body": "Please confirm your availability.",
            "received_at": "2026-09-25T10:00:00Z",
        }, headers=headers)

    assert response.status_code == 201
    data = response.json()
    assert data["sender_email"] == "hr@company.com"
    assert data["is_analyzed"] is False
    assert data["analysis"] is None
    assert data["entities"] is None
    assert data["reply"] is None
    task.assert_awaited_once_with(data["id"], task.await_args.args[1])

    user_id = task.await_args.args[1]
    with patch("app.services.email_service.get_pipeline") as pipeline, \
         patch("app.services.email_service.compute_priority", return_value=mock_priority), \
         patch("app.genai.reply_generator.generate_reply", return_value="Interview reply") as generate_reply:
        pipeline.return_value.process.side_effect = lambda *_: (
            analysis_thread_ids.append(threading.get_ident()) or mock_nlp
        )
        await analyze_email_in_background(data["id"], user_id)

    result = await client.get(f"/emails/{data['id']}", headers=headers)
    assert result.status_code == 200
    assert result.json()["is_analyzed"] is True
    assert result.json()["analysis"]["category_name"] == "Job / Career"
    assert analysis_thread_ids[0] != main_thread_id
    pipeline.return_value.process.assert_called_once()
    generate_reply.assert_called_once()

    with patch.object(EmailService, "analyze_email", new_callable=AsyncMock) as analyze:
        await analyze_email_in_background(data["id"], user_id)
        analyze.assert_not_awaited()

    inbox = await client.get("/emails", headers=headers)
    assert inbox.json()["total"] == 1
    assert inbox.json()["items"][0]["subject"] == "Interview Invitation"


@pytest.mark.asyncio
async def test_background_analysis_logs_failure_and_keeps_email_pending(client, caplog):
    headers = await register_user(client, "analysis-failure@test.com")
    with patch("app.api.routes.emails.analyze_email_in_background", new_callable=AsyncMock) as task:
        response = await client.post("/api/emails/incoming", json={
            "sender": "sender@example.com",
            "recipient": "analysis-failure@test.com",
            "subject": "Pending",
            "body": "This email will remain pending.",
        }, headers=headers)

    email_id, user_id = task.await_args.args
    with patch.object(EmailService, "_compute_analysis", side_effect=RuntimeError("analysis failed")), \
         caplog.at_level(logging.ERROR, logger="app.services.email_service"):
        await analyze_email_in_background(email_id, user_id)

    assert "Background analysis failed" in caplog.text
    detail = await client.get(f"/emails/{email_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["is_analyzed"] is False


@pytest.mark.asyncio
async def test_incoming_email_returns_saved_reply(client):
    headers = await register_user(client, "reply-incoming@test.com")
    mock_nlp, mock_priority = mock_analysis_results()

    with patch("app.services.email_service.get_pipeline") as pipeline, \
         patch("app.services.email_service.compute_priority", return_value=mock_priority), \
         patch("app.genai.reply_generator.generate_reply", return_value="Saved generated reply"):
        pipeline.return_value.process.return_value = mock_nlp
        response = await client.post("/api/emails/incoming", json={
            "sender": "sender@example.com",
            "recipient": "reply-incoming@test.com",
            "subject": "Follow up",
            "body": "Please respond.",
        }, headers=headers)

    assert response.status_code == 201
    assert response.json()["is_analyzed"] is False
    detail = await client.get(f"/emails/{response.json()['id']}", headers=headers)
    assert detail.json()["is_analyzed"] is True
    assert detail.json()["reply"]["current_content"] == "Saved generated reply"


@pytest.mark.asyncio
async def test_incoming_email_requires_authentication(client):
    response = await client.post("/api/emails/incoming", json={
        "sender": "sender@example.com",
        "recipient": "user@test.com",
        "subject": "Unauthenticated",
        "body": "This should be rejected.",
    })
    assert response.status_code == 401