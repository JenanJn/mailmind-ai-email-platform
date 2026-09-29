"""
Email service — orchestrates the full email processing pipeline.

Flow:
  1. Create email record
  2. Run NLP pipeline (category, entities, sentiment, intent) — synchronous
  3. Run priority engine (score + explanations) — synchronous
  4. Generate AI reply via Gemini — synchronous (fast fallback if API unavailable)
  5. Persist analysis, entities, and reply using explicit SQL (no lazy loads)
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import anyio
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session as db_session
from app.models.analysis import EmailAnalysis
from app.models.email import Email
from app.models.entity import EmailEntity
from app.models.reply import GeneratedReply, ReplyVersion
from app.nlp.pipeline import NLPResult, get_pipeline
from app.priority.engine import PriorityResult, compute_priority
from app.schemas.email import EmailCreate

logger = logging.getLogger(__name__)


@dataclass
class AnalysisSnapshot:
    """Plain values captured before any ORM session operations."""
    category_name: str
    priority_score: int
    priority_level: str


class EmailService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_pending_email(self, payload: EmailCreate, user_id: str) -> Email:
        email = Email(
            user_id=user_id,
            sender_name=payload.sender_name,
            sender_email=payload.sender_email,
            subject=payload.subject,
            body=payload.body,
            received_at=payload.received_at or datetime.now(timezone.utc),
            is_analyzed=False,
        )
        self.db.add(email)
        await self.db.flush()
        return email

    async def create_and_analyze(self, payload: EmailCreate, user_id: str) -> "EmailWithSnapshot":
        """Create an email, run full analysis, and return email + plain snapshot."""
        email = await self.create_pending_email(payload, user_id)
        snapshot = await self.analyze_email(email)
        return email, snapshot

    async def analyze_email(self, email: Email) -> AnalysisSnapshot:
        """
        Run full AI analysis and persist results.
        Returns an AnalysisSnapshot with plain values (no ORM lazy-load needed).
        Synchronous NLP/ML/AI work runs in a worker thread. Database operations
        remain on this async session and on the event loop.
        """
        nlp_result, priority_result, reply_text = await anyio.to_thread.run_sync(
            self._compute_analysis,
            email.subject or "",
            email.body or "",
            email.sender_name,
            email.sender_email,
        )

        # ── Step 1: Persist (bulk deletes avoid lazy-load triggers) ───────
        await self.db.execute(
            sql_delete(EmailAnalysis).where(EmailAnalysis.email_id == email.id)
        )
        await self.db.execute(
            sql_delete(EmailEntity).where(EmailEntity.email_id == email.id)
        )
        await self.db.execute(
            sql_delete(GeneratedReply).where(GeneratedReply.email_id == email.id)
        )
        await self.db.flush()

        key_points_str = self._build_key_points(nlp_result, priority_result)
        ai_explanation_str = "|||".join(priority_result.explanations)

        self.db.add(EmailAnalysis(
            email_id=email.id,
            category_name=nlp_result.category,
            category_confidence=nlp_result.category_confidence,
            intent=nlp_result.intent,
            priority_level=priority_result.level,
            priority_score=priority_result.score,
            urgency_level=priority_result.urgency_level,
            sentiment=nlp_result.sentiment,
            sentiment_score=nlp_result.sentiment_score,
            action_required=priority_result.action_required,
            deadline_text=nlp_result.deadline_text,
            key_points=key_points_str,
            ai_explanation=ai_explanation_str,
            priority_factors=priority_result.factors_json,
        ))

        for extracted in nlp_result.entities:
            self.db.add(EmailEntity(
                email_id=email.id,
                entity_type=extracted.entity_type,
                entity_text=extracted.entity_text,
                confidence=extracted.confidence,
                char_position=extracted.char_position,
            ))

        reply = GeneratedReply(
            email_id=email.id,
            current_content=reply_text,
            tone="formal",
            status="draft",
        )
        self.db.add(reply)
        await self.db.flush()

        self.db.add(ReplyVersion(
            reply_id=reply.id,
            content=reply_text,
            version_num=1,
            change_type="generated",
        ))

        email.is_analyzed = True
        await self.db.flush()

        logger.info(
            "Email %s analyzed: %s | priority=%d/%s",
            email.id, nlp_result.category,
            priority_result.score, priority_result.level,
        )

        return AnalysisSnapshot(
            category_name=nlp_result.category,
            priority_score=priority_result.score,
            priority_level=priority_result.level,
        )

    @staticmethod
    def _compute_analysis(
        subject: str,
        body: str,
        sender_name: Optional[str],
        sender_email: Optional[str],
    ) -> tuple[NLPResult, PriorityResult, str]:
        pipeline = get_pipeline()
        nlp_result: NLPResult = pipeline.process(subject, body)

        priority_result: PriorityResult = compute_priority(
            subject,
            body,
            nlp_result.category_slug,
            sender_email,
            action_required=nlp_result.action_required,
            deadline_text=nlp_result.deadline_text,
            deadline_datetime=nlp_result.deadline_datetime,
        )

        from app.genai.reply_generator import generate_reply
        entities_for_prompt = [
            {"entity_type": e.entity_type, "entity_text": e.entity_text}
            for e in nlp_result.entities
        ]
        reply_text: str = generate_reply(
            subject,
            body,
            sender_name,
            nlp_result.category,
            nlp_result.category_slug,
            nlp_result.intent,
            priority_result.action_required,
            nlp_result.deadline_text,
            entities_for_prompt,
        )
        return nlp_result, priority_result, reply_text

    @staticmethod
    def _build_key_points(nlp: NLPResult, priority: PriorityResult) -> str:
        points = []
        if nlp.intent and nlp.intent != "General Information":
            points.append(f"Email intent: {nlp.intent}")
        if nlp.deadline_text:
            points.append(f"Key deadline/time: {nlp.deadline_text}")
        if priority.action_required:
            points.append("Action is required from the recipient")
        if nlp.sentiment == "negative":
            points.append("Email carries a negative or urgent tone")
        if nlp.sentiment == "positive":
            points.append("Email has a positive tone")
        if nlp.entities:
            orgs = [e.entity_text for e in nlp.entities if e.entity_type == "ORG"][:2]
            if orgs:
                points.append(f"Organization mentioned: {', '.join(orgs)}")
            persons = [e.entity_text for e in nlp.entities if e.entity_type == "PERSON"][:2]
            if persons:
                points.append(f"Person mentioned: {', '.join(persons)}")
        return "|||".join(points)


async def analyze_email_in_background(email_id: str, user_id: str) -> None:
    """Analyze a persisted email in a fresh session; safe to invoke again."""
    try:
        async with db_session.AsyncSessionLocal() as db:
            result = await db.execute(
                select(Email).where(Email.id == email_id, Email.user_id == user_id)
            )
            email = result.scalar_one_or_none()
            if email is None or email.is_analyzed:
                return

            await EmailService(db).analyze_email(email)
            await db.commit()
    except Exception:
        logger.exception("Background analysis failed for email %s", email_id)


# Type alias for the tuple returned by create_and_analyze
EmailWithSnapshot = tuple
