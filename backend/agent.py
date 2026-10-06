"""Agent entry and wiring: builds the PydanticAI agent and runs one chat turn."""

import asyncio
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext, capture_run_messages
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from models import AgentDeps, ChatTurn, ShopReply
from tools import TOOLS

BACKEND_DIR = Path(__file__).resolve().parent
PROMPT_PATH = BACKEND_DIR / "prompts" / "prompt.md"
MODEL_NAME = "gpt-5.6-luna"

# ---------- Safety limits and reply redaction ----------
# Code-level safety checks that back up the rules in prompts/prompt.md.
#
# The prompt asks the agent never to reveal sensitive data; these checks make
# sure that holds even if the model slips. They run on every reply before it is
# shown, saved to chat history, or written to the audit trail.

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


# PORTKEY_API_KEY lives in a .env file: hw4/.env if present, otherwise the
# course-level AI Foundations/.env. Values already in the environment win.
load_dotenv(BACKEND_DIR.parent / ".env", override=False)
load_dotenv(BACKEND_DIR.parent.parent / ".env", override=False)


def build_model() -> OpenAIChatModel:
    """OpenAI-compatible client pointed at the Portkey gateway."""
    key = os.getenv("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is missing from the .env file.")
    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY", "portkey"),
        base_url=os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1"),
        default_headers={"x-portkey-api-key": key, "x-portkey-provider": "openai"},
    )
    return OpenAIChatModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def load_prompt() -> str:
    # Read on every run so edits to prompt.md apply without restarting the server.
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_agent() -> Agent[AgentDeps, ShopReply]:
    return Agent(
        build_model(),
        deps_type=AgentDeps,
        output_type=ShopReply,
        instructions=load_prompt,
        tools=TOOLS,
        retries=2,
    )


# Built once when the server starts.
shop_agent = build_agent()


# Dynamic instructions: these functions run on every request and add code-built
# context (who is chatting, which page they're on) after prompt.md.
@shop_agent.instructions
def customer_context(ctx: RunContext[AgentDeps]) -> str:
    c = ctx.deps.customer
    if c is None:
        return "## Current customer\nA guest (not logged in). You don't know their name or email."
    return (
        "## Current customer\n"
        f"Logged in as {c.first_name} {c.last_name} ({c.email}). "
        "The message history is this chat only (they can start a new chat or reopen past ones)."
    )


@shop_agent.instructions
def page_context(ctx: RunContext[AgentDeps]) -> str:
    page = ctx.deps.page
    if page is None:
        return "## Current page\nUnknown."
    if page.product_id:
        return (
            "## Current page\n"
            f"The customer is viewing the product page for **{page.product_name}** "
            f"(product_id `{page.product_id}`). Words like \"this\", \"it\", or \"this one\" "
            "refer to this product unless the conversation clearly says otherwise."
        )
    return f"## Current page\nThe customer is on `{page.path}` (not a single product page)."


def to_message_history(history: list[ChatTurn]) -> list[ModelMessage]:
    """Convert the widget's earlier turns into PydanticAI message objects."""
    messages: list[ModelMessage] = []
    for turn in history:
        if turn.role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=turn.content)]))
        else:
            messages.append(ModelResponse(parts=[TextPart(content=turn.content)]))
    return messages


# Tools that look at one specific product; their product_id args are recorded
# as products the customer asked about.
PRODUCT_LOOKUP_TOOLS = {"get_product_details", "check_stock"}


# Hard limits on one agent loop, so a confused model can't call tools forever.
USAGE_LIMITS = UsageLimits(
    request_limit=MAX_MODEL_REQUESTS,
    tool_calls_limit=MAX_TOOL_CALLS,
    total_tokens_limit=MAX_TOTAL_TOKENS,
)


@dataclass
class ChatRun:
    """Outcome of one agent loop, used for the reply, chat history, and the audit trail."""

    reply: ShopReply | None  # None when the loop didn't finish
    stop_reason: str  # completed | content_filter | usage_limit_exceeded | timeout | output_invalid | error
    detail: str | None = None  # short reason for non-completed stops (no secrets)
    messages: list[ModelMessage] = field(default_factory=list)  # this run's messages, for the audit
    looked_up: list[str] = field(default_factory=list)  # product_ids passed to get_product_details / check_stock
    tools_used: set[str] = field(default_factory=set)
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def summarize_tool_calls(messages: list[ModelMessage]) -> tuple[list[str], set[str]]:
    ids: list[str] = []
    tools: set[str] = set()
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    tools.add(part.tool_name)
                    if part.tool_name in PRODUCT_LOOKUP_TOOLS:
                        pid = part.args_as_dict().get("product_id")
                        if isinstance(pid, str):
                            ids.append(pid)
    return list(dict.fromkeys(ids)), tools


async def run_chat(message: str, history: list[ChatTurn], deps: AgentDeps) -> ChatRun:
    """Run one turn within the loop limits; never raises for model problems."""
    prior = to_message_history(history)
    with capture_run_messages() as captured:
        try:
            result = await asyncio.wait_for(
                shop_agent.run(message, deps=deps, message_history=prior, usage_limits=USAGE_LIMITS),
                timeout=RUN_TIMEOUT_SECONDS,
            )
            run = ChatRun(reply=result.output, stop_reason="completed", messages=result.new_messages())
        except UsageLimitExceeded as e:
            run = ChatRun(reply=None, stop_reason="usage_limit_exceeded", detail=str(e)[:200])
        except TimeoutError:
            run = ChatRun(reply=None, stop_reason="timeout", detail=f"over {RUN_TIMEOUT_SECONDS}s")
        except ModelHTTPError as e:
            filtered = "content_filter" in str(e.body)
            run = ChatRun(
                reply=None,
                stop_reason="content_filter" if filtered else "error",
                detail=f"model HTTP {e.status_code}",
            )
        except UnexpectedModelBehavior as e:
            run = ChatRun(reply=None, stop_reason="output_invalid", detail=str(e)[:200])
        except Exception as e:  # network errors etc.; details go to the server log only
            run = ChatRun(reply=None, stop_reason="error", detail=f"{type(e).__name__}: {str(e)[:150]}")
        if not run.messages:
            # Failed runs: keep whatever steps happened (skip the prior history).
            run.messages = list(captured[len(prior):])
    run.looked_up, run.tools_used = summarize_tool_calls(run.messages)
    # Count model calls and tokens from this run's responses (works for failed runs too).
    responses = [m for m in run.messages if isinstance(m, ModelResponse)]
    run.requests = len(responses)
    run.input_tokens = sum(m.usage.input_tokens or 0 for m in responses)
    run.output_tokens = sum(m.usage.output_tokens or 0 for m in responses)
    return run
