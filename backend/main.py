"""Campus Customs backend: products, product images, accounts, and the chat agent.

Run from the backend/ folder (with the hw4 .venv activated):
    uvicorn main:app --reload --port 8000
"""

import json
import logging
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env before the local modules below, which read settings when imported
# (SESSION_SECRET in auth.py, AUDIT_TRAIL_PATH in audit.py, PORTKEY_API_KEY in agent.py).
# hw4/.env is used if present, otherwise the course-level .env one folder up.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=False)

from fastapi import Cookie, FastAPI, HTTPException, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, field_validator  # noqa: E402

import audit  # noqa: E402
import auth
import chat_store
from categories import category_for, primary_color
from agent import MODEL_NAME, run_chat
from safety import redact
from models import (
    AgentDeps,
    ChatConversation,
    ChatRequest,
    ChatResponse,
    Customer,
    PageContext,
    PageInfo,
    ProductCard,
    SavedChatMessage,
    ConversationSummary,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = Path(os.environ.get("CAMPUS_DB", DATA_DIR / "campus_customs.db"))
SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL"]

app = FastAPI(title="Campus Customs API")

# Adds chat_messages.mentioned_products on first run and fills it for old rows.
chat_store.ensure_schema(DB_PATH)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Only the product photo folder is public, so /images/products/<file>.jpg lines
# up with image_file_path in the catalogue without exposing the database file.
app.mount("/images/products", StaticFiles(directory=DATA_DIR / "products"), name="images")


class InventoryRow(BaseModel):
    size: str
    quantity: int


class ProductDetail(ProductCard):
    inventory: list[InventoryRow]


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_product(row: sqlite3.Row) -> dict:
    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "garment_type": row["garment_type"],
        "category": category_for(row["garment_type"]),
        "description": row["description"],
        "primary_color": primary_color(row["product_id"], json.loads(row["colors"])),
        "colors": json.loads(row["colors"]),
        "search_tags": json.loads(row["search_tags"]),
        "image_url": f"/images/{row['image_file_path']}",
        "price": row["price"],
        "total_stock": row["total_stock"] or 0,
    }


PRODUCT_QUERY = """
    SELECT c.*, SUM(i.quantity) AS total_stock
    FROM catalogue c
    LEFT JOIN inventory i ON i.product_id = c.product_id
"""


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/products", response_model=list[ProductCard])
def list_products() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(PRODUCT_QUERY + " GROUP BY c.product_id ORDER BY c.name").fetchall()
    return [row_to_product(r) for r in rows]


def load_product_cards(product_ids: list[str]) -> list[ProductCard]:
    """Look up cards for the given ids, keeping their order and dropping unknown or repeated ids."""
    unique_ids = list(dict.fromkeys(product_ids))
    if not unique_ids:
        return []
    placeholders = ",".join("?" * len(unique_ids))
    with get_db() as conn:
        rows = conn.execute(
            PRODUCT_QUERY + f" WHERE c.product_id IN ({placeholders}) GROUP BY c.product_id",
            unique_ids,
        ).fetchall()
    by_id = {r["product_id"]: ProductCard(**row_to_product(r)) for r in rows}
    return [by_id[pid] for pid in unique_ids if pid in by_id]


@app.get("/api/products/{product_id}", response_model=ProductDetail)
def get_product(product_id: str) -> dict:
    with get_db() as conn:
        row = conn.execute(
            PRODUCT_QUERY + " WHERE c.product_id = ? GROUP BY c.product_id", (product_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Product not found")
        stock_rows = conn.execute(
            "SELECT size, quantity FROM inventory WHERE product_id = ?", (product_id,)
        ).fetchall()

    product = row_to_product(row)
    stock = sorted(
        ({"size": s["size"], "quantity": s["quantity"]} for s in stock_rows),
        key=lambda s: SIZE_ORDER.index(s["size"]) if s["size"] in SIZE_ORDER else len(SIZE_ORDER),
    )
    product["inventory"] = stock
    return product


# ---------- Accounts ----------

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8
login_limiter = auth.LoginLimiter()


def _clean_email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address")
    return value


class SignupRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str
    confirm_password: str

    @field_validator("first_name", "last_name")
    @classmethod
    def required_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("This field is required")
        return v

    _email = field_validator("email")(_clean_email)


class LoginRequest(BaseModel):
    email: str
    password: str

    _email = field_validator("email")(lambda v: v.strip().lower())


class User(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str


def _user_from_row(row: sqlite3.Row) -> dict:
    # Seed accounts may only have the combined name filled in.
    first, last = row["first_name"], row["last_name"]
    if not first:
        first, _, last = row["name"].partition(" ")
    return {"id": row["id"], "first_name": first, "last_name": last or "", "email": row["email"]}


def _start_session(response: Response, user_id: int) -> None:
    response.set_cookie(
        auth.SESSION_COOKIE,
        auth.make_session_token(user_id),
        max_age=auth.SESSION_MAX_AGE,
        httponly=True,  # page JavaScript can't read the cookie
        samesite="lax",
        # Set secure=True when the site is served over HTTPS.
    )


def current_user(token: str | None) -> dict | None:
    user_id = auth.read_session_token(token)
    if user_id is None:
        return None
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user_from_row(row) if row else None


@app.post("/api/auth/signup", response_model=User, status_code=201)
def signup(req: SignupRequest, response: Response) -> dict:
    if len(req.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if req.password != req.confirm_password:
        raise HTTPException(400, "Passwords do not match")

    with get_db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash, first_name, last_name)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    f"{req.first_name} {req.last_name}",
                    req.email,
                    auth.hash_password(req.password),
                    req.first_name,
                    req.last_name,
                ),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "An account with that email already exists")
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()

    _start_session(response, row["id"])
    return _user_from_row(row)


@app.post("/api/auth/login", response_model=User)
def login(req: LoginRequest, response: Response) -> dict:
    if login_limiter.is_blocked(req.email):
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")

    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (req.email,)).fetchone()

    stored = row["password_hash"] if row else auth.DUMMY_HASH
    if not auth.verify_password(req.password, stored) or row is None:
        login_limiter.record_failure(req.email)
        # Same message either way, so it doesn't reveal which emails have accounts.
        raise HTTPException(401, "Incorrect email or password")

    login_limiter.reset(req.email)
    _start_session(response, row["id"])
    return _user_from_row(row)


@app.post("/api/auth/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(auth.SESSION_COOKIE)


@app.get("/api/auth/me", response_model=User | None)
def me(cc_session: str | None = Cookie(default=None)) -> dict | None:
    return current_user(cc_session)


# ---------- Chat ----------

logger = logging.getLogger("campus_customs.chat")
BLOCKED_REPLY = (
    "Sorry, I can't help with that. I'm here to help you find Campus Customs gear — "
    "ask me about hoodies, tees, sizes, or colors!"
)
LIMIT_REPLY = (
    "Sorry, that request was too much for me to look up in one go. Could you ask about "
    "one item or category at a time?"
)
UNAVAILABLE = "The shopping assistant is unavailable right now. Please try again."


SAFE_PATH = re.compile(r"^/[A-Za-z0-9/_\-]*$")
HISTORY_PAGE_SIZE = 50


def build_page_context(page: PageInfo) -> PageContext:
    """Turn the browser's page info into trusted context for the agent.

    The product id is looked up in the database, so the agent only ever sees a
    real product name, and odd-looking paths are replaced rather than passed on.
    """
    path = page.path if SAFE_PATH.match(page.path) else "/"
    if page.product_id:
        with get_db() as conn:
            row = conn.execute(
                "SELECT product_id, name FROM catalogue WHERE product_id = ?", (page.product_id,)
            ).fetchone()
        if row:
            return PageContext(path=path, product_id=row["product_id"], product_name=row["name"])
    return PageContext(path=path)


@app.get("/api/chat/conversations", response_model=list[ConversationSummary])
def chat_conversations(cc_session: str | None = Cookie(default=None)) -> list[dict]:
    """The logged-in customer's past chats (newest first); empty for guests."""
    user = current_user(cc_session)
    return chat_store.list_conversations(DB_PATH, user["id"]) if user else []


@app.get("/api/chat/history", response_model=ChatConversation)
def chat_history(
    conversation_id: str | None = None, cc_session: str | None = Cookie(default=None)
) -> ChatConversation:
    """One saved conversation (default: the most recent), oldest message first."""
    user = current_user(cc_session)
    if user is None:
        return ChatConversation(conversation_id=None, messages=[])
    if conversation_id is None:
        conversation_id = chat_store.latest_conversation_id(DB_PATH, user["id"])
    elif not chat_store.owns_conversation(DB_PATH, user["id"], conversation_id):
        raise HTTPException(404, "Conversation not found")
    if conversation_id is None:
        return ChatConversation(conversation_id=None, messages=[])

    messages = []
    for r in chat_store.load_conversation_rows(DB_PATH, user["id"], conversation_id, HISTORY_PAGE_SIZE):
        # Rebuild cards from the catalogue by id, so restored chats show current
        # prices/stock and cards saved before newer fields existed still load.
        try:
            ids = [p["product_id"] for p in json.loads(r["products_json"] or "[]")]
        except (ValueError, TypeError, KeyError):
            ids = []
        messages.append(
            SavedChatMessage(
                role=r["role"], content=r["content"], products=load_product_cards(ids), created_at=r["created_at"]
            )
        )
    return ChatConversation(conversation_id=conversation_id, messages=messages)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, cc_session: str | None = Cookie(default=None)) -> ChatResponse:
    user = current_user(cc_session)
    customer = (
        Customer(id=user["id"], first_name=user["first_name"], last_name=user["last_name"], email=user["email"])
        if user
        else None
    )
    deps = AgentDeps(db_path=DB_PATH, customer=customer, page=build_page_context(req.page))
    # Logged-in customers: memory comes from the database (it can't be edited by
    # the browser) and covers only the current conversation, so "New chat" really
    # starts fresh. Guests: only the turns the widget sent for this visit.
    conversation_id = None
    if customer:
        conversation_id = req.conversation_id
        if conversation_id is None or not chat_store.owns_conversation(DB_PATH, customer.id, conversation_id):
            conversation_id = chat_store.new_conversation_id()
        history = chat_store.load_history_turns(DB_PATH, customer.id, conversation_id)
    else:
        history = req.history

    started = datetime.now(UTC)
    run = await run_chat(req.message, history, deps)

    cards: list[ProductCard] = []
    redacted = False
    if run.stop_reason == "completed":
        # The agent only chooses ids; every card is rebuilt from the database, so
        # made-up ids are dropped and prices/stock on the cards are always real.
        cards = load_product_cards(run.reply.product_ids)
        if len(cards) < len(set(run.reply.product_ids)):
            logger.warning("Agent returned unknown product ids; they were dropped")
        # Last line of defense: strip hashes, card numbers, keys, and other people's emails.
        reply = redact(run.reply.reply, allowed_email=customer.email if customer else None)
        redacted = reply != run.reply.reply
    elif run.stop_reason == "content_filter":
        # The provider blocked the message (often a prompt-injection attempt).
        reply = BLOCKED_REPLY
    elif run.stop_reason in ("usage_limit_exceeded", "timeout"):
        reply = LIMIT_REPLY
    else:
        reply = None
        logger.error("Agent run failed: %s (%s)", run.stop_reason, run.detail)

    events = audit.loop_events(run.messages)
    audit.append_entry(
        {
            "time": started.isoformat(timespec="milliseconds"),
            "duration_ms": int((datetime.now(UTC) - started).total_seconds() * 1000),
            "model": MODEL_NAME,
            "customer": f"user #{customer.id}" if customer else "guest",
            "conversation_id": conversation_id,
            "page": deps.page.product_id or deps.page.path,
            "message": audit.short(req.message),
            "events": events,
            "tool_calls": sum(1 for e in events if e["type"] == "tool_call"),
            "model_requests": run.requests,
            "tokens": {"input": run.input_tokens, "output": run.output_tokens},
            "stop_reason": run.stop_reason,
            "model_finish_reason": audit.model_finish_reason(run.messages),
            "stop_detail": run.detail,
            "reply": audit.short(reply) if reply else None,
            "cards_shown": len(cards),
            "reply_redacted": redacted,
        }
    )

    if reply is None:
        # Never send stack traces or keys to the browser.
        raise HTTPException(502, UNAVAILABLE)
    if customer:
        chat_store.save_exchange(
            DB_PATH,
            customer.id,
            conversation_id,
            req.message,
            reply,
            cards,
            run.looked_up,
            # Cards from a "what's popular?" answer aren't the customer asking about
            # those items; counting them would make the ranking feed on itself.
            count_cards="get_popular_products" not in run.tools_used,
        )
    return ChatResponse(reply=reply, products=cards, conversation_id=conversation_id)
