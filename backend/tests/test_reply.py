from types import SimpleNamespace

from app.genai import reply_generator
from app.genai.prompt_builder import build_generation_prompt


class FakeGemini:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []

    def generate_content(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(text=next(self.responses))


def test_action_request_with_deadline_uses_retry_and_context(monkeypatch):
    model = FakeGemini(["Thank you for your email.", "I will send the project status in two days."])
    monkeypatch.setattr(reply_generator, "_get_model", lambda: model)
    reply = reply_generator.generate_reply(
        "Project status", "Please send the project status in two days.", "Alex",
        "Work / Professional", "work_professional", "General Information", True,
        "in two days", [],
    )
    assert "project status" in reply.lower()
    assert "two days" in reply.lower()
    assert len(model.prompts) == 2
    assert "Detected action:" in model.prompts[0]


def test_meeting_reply_is_accepted_when_it_mentions_meeting(monkeypatch):
    model = FakeGemini(["I acknowledge the project meeting tomorrow and can confirm attendance."])
    monkeypatch.setattr(reply_generator, "_get_model", lambda: model)
    reply = reply_generator.generate_reply(
        "Project meeting", "Can you confirm tomorrow's project meeting?", "Alex",
        "Work / Professional", "work_professional", "Meeting Invitation", True,
        "tomorrow", [],
    )
    assert "meeting" in reply.lower()
    assert len(model.prompts) == 1


def test_informational_reply_does_not_require_action(monkeypatch):
    model = FakeGemini(["Thank you for sharing the report. I have received it."])
    monkeypatch.setattr(reply_generator, "_get_model", lambda: model)
    reply = reply_generator.generate_reply(
        "Report", "Thanks for sharing the report.", "Alex",
        "Work / Professional", "work_professional", "General Information", False,
        None, [],
    )
    assert "received" in reply.lower()
    assert len(model.prompts) == 1


def test_support_reply_acknowledges_issue(monkeypatch):
    model = FakeGemini(["I understand the payment issue and will review the account details."])
    monkeypatch.setattr(reply_generator, "_get_model", lambda: model)
    reply = reply_generator.generate_reply(
        "Payment issue", "I need help resolving a payment issue.", "Alex",
        "Customer Support", "customer_support", "Support Communication", True,
        None, [],
    )
    assert "payment issue" in reply.lower()
    assert len(model.prompts) == 1


def test_prompt_contains_structured_reply_context():
    prompt = build_generation_prompt(
        "Subject", "Body", "Alex", "Work / Professional", "work_professional",
        "Action Request", True, "tomorrow", [{"entity_text": "Project X"}],
        action="Send Project X", tone="formal",
    )
    for value in ("Subject", "Body", "Work / Professional", "Action Request", "Yes", "Send Project X", "tomorrow", "Project X", "formal"):
        assert value in prompt