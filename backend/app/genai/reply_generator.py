"""
Gemini-powered smart reply generator.

Uses google-generativeai SDK with gemini-1.5-flash model.
Falls back to a template-based reply if the API is unavailable.
"""
import logging
import re
import time
from typing import Optional

from app.config import settings
from app.genai.prompt_builder import build_generation_prompt, build_modification_prompt

logger = logging.getLogger(__name__)

_gemini_model = None


def _get_model():
    global _gemini_model
    if _gemini_model is None:
        if not settings.gemini_api_key:
            logger.warning("GEMINI_API_KEY not set. Using template fallback.")
            return None
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            _gemini_model = genai.GenerativeModel(
                model_name=settings.gemini_model,
                generation_config={
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "max_output_tokens": 600,
                },
            )
            logger.info("Gemini model initialized (%s)", settings.gemini_model)
        except Exception as e:
            logger.error("Failed to initialize Gemini: %s", e)
    return _gemini_model


def generate_reply(
    subject: str,
    body: str,
    sender_name: Optional[str],
    category: str,
    category_slug: str,
    intent: str,
    action_required: bool,
    deadline_text: Optional[str],
    entities: list[dict],
    tone: str = "formal",
    action: Optional[str] = None,
    email_id: Optional[str] = None,
) -> str:
    """
    Generate a contextual email reply using Gemini.
    Falls back to template if API unavailable.
    """
    generation_started = time.perf_counter()
    validation_retry = False
    try:
        model = _get_model()
        detected_action = action or _infer_action(body, action_required)
        prompt = build_generation_prompt(
            subject=subject,
            body=body,
            sender_name=sender_name,
            category=category,
            category_slug=category_slug,
            intent=intent,
            action_required=action_required,
            deadline_text=deadline_text,
            entities=entities,
            tone=tone,
            action=detected_action,
        )

        if model is None:
            return _template_fallback(category_slug, sender_name, intent, deadline_text, detected_action)

        try:
            response = _generate_content_timed(model, prompt, 1, email_id)
            reply = response.text.strip()
            if not reply:
                return _template_fallback(category_slug, sender_name, intent, deadline_text, detected_action)
            if _validate_reply(reply, action_required, detected_action, deadline_text):
                return reply

            retry_prompt = build_generation_prompt(
                subject=subject,
                body=body,
                sender_name=sender_name,
                category=category,
                category_slug=category_slug,
                intent=intent,
                action_required=action_required,
                deadline_text=deadline_text,
                entities=entities,
                tone=tone,
                action=detected_action,
                correction_instruction=_validation_feedback(action_required, detected_action, deadline_text),
            )
            validation_retry = True
            retry_response = _generate_content_timed(model, retry_prompt, 2, email_id)
            retry_reply = retry_response.text.strip()
            if retry_reply and _validate_reply(retry_reply, action_required, detected_action, deadline_text):
                return retry_reply
            return _template_fallback(category_slug, sender_name, intent, deadline_text, detected_action)
        except Exception as e:
            logger.error("Gemini API error: %s. Using fallback.", e)
            return _template_fallback(category_slug, sender_name, intent, deadline_text, detected_action)
    finally:
        logger.info(
            "email_analysis_latency event=reply_generation email_id=%s duration_ms=%.2f validation_retry=%s",
            email_id or "unknown",
            (time.perf_counter() - generation_started) * 1000,
            str(validation_retry).lower(),
        )


def _generate_content_timed(model, prompt: str, attempt: int, email_id: Optional[str]):
    attempt_started = time.perf_counter()
    outcome = "success"
    try:
        return model.generate_content(prompt)
    except Exception:
        outcome = "failed"
        raise
    finally:
        logger.info(
            "email_analysis_latency event=gemini_attempt email_id=%s attempt=%d duration_ms=%.2f outcome=%s",
            email_id or "unknown",
            attempt,
            (time.perf_counter() - attempt_started) * 1000,
            outcome,
        )


def _infer_action(body: str, action_required: bool) -> Optional[str]:
    if not action_required:
        return None
    text = " ".join((body or "").split()).rstrip(".")
    match = re.search(
        r"\b(?:please|kindly)\s+(send|provide|review|confirm|respond|reply|approve|submit)\s+(.+)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    requested = re.split(r"\s+(?:in|within|by|before)\s+", match.group(2), maxsplit=1, flags=re.IGNORECASE)[0]
    return f"{match.group(1).capitalize()} {requested.strip(' ,')}."


def _validate_reply(
    reply: str,
    action_required: bool,
    action: Optional[str],
    deadline_text: Optional[str],
) -> bool:
    lowered_reply = reply.lower()
    if action_required and action:
        action_terms = [term for term in re.findall(r"[a-z0-9]+", action.lower()) if len(term) > 2]
        if not any(term in lowered_reply for term in action_terms):
            return False
    if deadline_text:
        deadline_terms = [term for term in re.findall(r"[a-z0-9]+", deadline_text.lower()) if len(term) > 2]
        if not any(term in lowered_reply for term in deadline_terms) and "deadline" not in lowered_reply:
            return False
    return True


def _validation_feedback(
    action_required: bool,
    action: Optional[str],
    deadline_text: Optional[str],
) -> str:
    requirements = []
    if action_required and action:
        requirements.append(f"explicitly acknowledge the requested action: {action}")
    if deadline_text:
        requirements.append(f"explicitly acknowledge the deadline: {deadline_text}")
    return " and ".join(requirements) + ". Do not claim completion." if requirements else "Address the original email specifically."


def modify_reply(current_reply: str, style: str, category_slug: str) -> str:
    """
    Modify an existing reply's style using Gemini.
    """
    model = _get_model()
    prompt = build_modification_prompt(current_reply, style, category_slug)

    if model is None:
        return _apply_template_modification(current_reply, style)

    try:
        # Use higher temperature for creative variations
        import google.generativeai as genai
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.8 if style in ("friendly", "longer") else 0.5,
                max_output_tokens=600,
            ),
        )
        result = response.text.strip()
        return result if result else current_reply
    except Exception as e:
        logger.error("Gemini modification error: %s", e)
        return _apply_template_modification(current_reply, style)


# ── Fallback templates ────────────────────────────────────────────────────────

FALLBACK_TEMPLATES = {
    "job_career": (
        "Dear {sender},\n\n"
        "Thank you for reaching out regarding this opportunity. "
        "I appreciate you taking the time to contact me.\n\n"
        "I would be happy to discuss this further and confirm my availability.\n\n"
        "Best regards,\n[Your Name]"
    ),
    "education": (
        "Dear {sender},\n\n"
        "Thank you for the update. I acknowledge receipt of this information "
        "and will act accordingly.\n\n"
        "Please let me know if you require any additional information from my end.\n\n"
        "Regards,\n[Your Name]"
    ),
    "ecommerce_shopping": (
        "Dear {sender},\n\n"
        "Thank you for the update regarding my order. "
        "I have noted the information provided.\n\n"
        "Please let me know if any further action is required from my end.\n\n"
        "Regards,\n[Your Name]"
    ),
    "finance_banking": (
        "Dear {sender},\n\n"
        "Thank you for this notification. I have reviewed the information provided.\n\n"
        "If any action is required from my end, please provide the necessary details "
        "and I will respond promptly.\n\n"
        "Regards,\n[Your Name]"
    ),
    "travel": (
        "Dear {sender},\n\n"
        "Thank you for the travel update. I have noted the details of my booking.\n\n"
        "Please confirm if any action is required from my end.\n\n"
        "Regards,\n[Your Name]"
    ),
    "healthcare": (
        "Dear {sender},\n\n"
        "Thank you for the communication. I acknowledge the appointment/information provided.\n\n"
        "Please let me know if there is anything I need to prepare or confirm.\n\n"
        "Regards,\n[Your Name]"
    ),
    "default": (
        "Dear {sender},\n\n"
        "Thank you for your email. I have reviewed the information you have shared.\n\n"
        "I will follow up as needed. Please feel free to reach out if you require "
        "any additional information.\n\n"
        "Best regards,\n[Your Name]"
    ),
}


def _template_fallback(
    category_slug: str,
    sender_name: Optional[str],
    intent: str,
    deadline_text: Optional[str],
    action: Optional[str] = None,
) -> str:
    template = FALLBACK_TEMPLATES.get(category_slug, FALLBACK_TEMPLATES["default"])
    sender = sender_name or "Sir/Madam"
    reply = template.format(sender=sender)

    if action:
        reply = reply.replace(
            "I will follow up as needed.",
            f"I acknowledge your request to {action.lower()} and will review it carefully.",
        )

    if deadline_text:
        # Insert deadline acknowledgement
        reply = reply.replace(
            "I will follow up as needed.",
            f"I note that the deadline is {deadline_text} and will respond accordingly.",
        )
    return reply


def _apply_template_modification(reply: str, style: str) -> str:
    """Simple non-AI modification when Gemini is unavailable."""
    if style == "shorter":
        lines = reply.split("\n")
        # Keep greeting, first content line, and sign-off
        content_lines = [l for l in lines if l.strip()]
        if len(content_lines) > 4:
            return "\n".join([content_lines[0], content_lines[1], content_lines[-2], content_lines[-1]])
    return reply
