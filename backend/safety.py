"""Code-level safety checks that back up the rules in prompts/prompt.md.

The prompt asks the agent never to reveal sensitive data; these checks make
sure that holds even if the model slips. They run on every reply before it is
shown, saved to chat history, or written to the audit trail.
"""

import re

# Agent loop limits (enforced by PydanticAI UsageLimits and a timeout in agent.py).
MAX_MODEL_REQUESTS = 6  # model calls per customer message
MAX_TOOL_CALLS = 10  # tool calls per customer message
MAX_TOTAL_TOKENS = 120_000  # input + output tokens per customer message
RUN_TIMEOUT_SECONDS = 60

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PASSWORD_HASH_RE = re.compile(r"pbkdf2_sha256\$\S+")
CARD_NUMBER_RE = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
SECRET_KEY_RE = re.compile(r"\b(?:sk|pk|pt)-[A-Za-z0-9_-]{16,}\b")


def _mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"


def redact(text: str, allowed_email: str | None = None) -> str:
    """Remove password hashes, card numbers, API keys, and email addresses.

    allowed_email: the logged-in customer's own address, which may appear in a
    reply to them (e.g. "your account is under ...").
    """
    text = PASSWORD_HASH_RE.sub("[removed]", text)
    text = SECRET_KEY_RE.sub("[removed]", text)
    text = CARD_NUMBER_RE.sub("[removed]", text)
    allowed = (allowed_email or "").lower()
    return EMAIL_RE.sub(lambda m: m.group(0) if m.group(0).lower() == allowed else _mask_email(m.group(0)), text)
