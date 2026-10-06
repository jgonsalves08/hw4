"""Campus Customs backend: products, product images, accounts, and the chat agent.

Run from the backend/ folder (with the hw4 .venv activated):
    uvicorn main:app --reload --port 8000
"""

import base64
import fcntl
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

# Load .env first: settings are read when this file and agent.py load
# (SESSION_SECRET and AUDIT_TRAIL_PATH below, PORTKEY_API_KEY in agent.py).
# hw4/.env is used if present, otherwise the course-level .env one folder up.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=False)

from fastapi import Cookie, FastAPI, HTTPException, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, field_validator  # noqa: E402

from pydantic_ai.messages import (  # noqa: E402
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)

from agent import MODEL_NAME, redact, run_chat  # noqa: E402
from tools import category_for, primary_color  # noqa: E402
from models import (  # noqa: E402
    MAX_HISTORY,
    ChatTurn,
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

# ---------- Accounts: password hashing, sessions, login limits ----------
# Password hashing and session cookies for Campus Customs.
#
# Passwords are never stored. Each one is run through PBKDF2-HMAC-SHA256 with a
# random per-user salt, and only the result is saved in users.password_hash.

ALGORITHM = "pbkdf2_sha256"
# OWASP's recommended minimum for PBKDF2-HMAC-SHA256.
ITERATIONS = 600_000
# Seed accounts use a 3-part hash (pbkdf2_sha256$salt$digest) with no iteration
# count stored; they were created with 120,000 iterations.
LEGACY_ITERATIONS = int(os.environ.get("LEGACY_PBKDF2_ITERATIONS", "120000"))

SESSION_COOKIE = "cc_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # one week
# Signs session cookies. Without SESSION_SECRET set, a random key is made at
# startup, so everyone is logged out whenever the server restarts.
_SESSION_KEY = os.environ.get("SESSION_SECRET", "").encode() or secrets.token_bytes(32)


def _pbkdf2(password: str, salt: str, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()


def hash_password(password: str) -> str:
    """Return pbkdf2_sha256$<iterations>$<salt>$<hex digest>."""
    salt = secrets.token_hex(16)
    return f"{ALGORITHM}${ITERATIONS}${salt}${_pbkdf2(password, salt, ITERATIONS)}"


def verify_password(password: str, stored: str) -> bool:
    parts = stored.split("$")
    if len(parts) == 4:
        algorithm, iterations, salt, digest = parts
        iterations = int(iterations)
    elif len(parts) == 3:
        algorithm, salt, digest = parts
        iterations = LEGACY_ITERATIONS
    else:
        return False
    if algorithm != ALGORITHM:
        return False
    # Constant-time comparison so response timing doesn't leak how close a guess was.
    return hmac.compare_digest(_pbkdf2(password, salt, iterations), digest)


# A real hash to check against when the email doesn't exist, so a login attempt
# takes the same time whether or not the account is real.
DUMMY_HASH = hash_password(secrets.token_hex(16))


def make_session_token(user_id: int) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"uid": user_id, "exp": int(time.time()) + SESSION_MAX_AGE}).encode()
    ).decode()
    sig = hmac.new(_SESSION_KEY, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def read_session_token(token: str | None) -> int | None:
    """Return the user id from a valid, unexpired token, otherwise None."""
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    expected = hmac.new(_SESSION_KEY, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload))
    except ValueError:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data.get("uid")


class LoginLimiter:
    """Blocks an email after too many failed logins in a short window."""

    def __init__(self, max_failures: int = 5, window_seconds: int = 15 * 60):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        cutoff = time.time() - self.window
        recent = [t for t in self._failures.get(key, []) if t > cutoff]
        self._failures[key] = recent
        return recent

    def is_blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self.max_failures

    def record_failure(self, key: str) -> None:
        self._recent(key).append(time.time())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


# ---------- Chat history storage ----------
# Saving and loading chat history in the chat_messages table.
#
# Each row also records mentioned_products: a JSON list of the product_ids that
# message was about. On user rows this is what the customer asked about; on
# assistant rows it's what the reply looked up or showed. The popularity tool
# counts the user rows.

# A reply about 1-3 items is about those items specifically; a longer list
# (e.g. "here are 27 hoodies") is browsing and doesn't count as asking about each.
SPECIFIC_MAX = 3
# Old messages saved before conversations existed are split into separate chats
# wherever there's a gap this long between messages.
CONVERSATION_GAP = timedelta(hours=3)


def new_conversation_id() -> str:
    return uuid.uuid4().hex


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _product_names(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = conn.execute("SELECT product_id, name FROM catalogue").fetchall()
    # Longest names first so "Yale Sports Hoodie Golf" wins over a shorter overlap.
    return sorted(((r["product_id"], r["name"].lower()) for r in rows), key=lambda t: -len(t[1]))


def find_named_products(text: str, names: list[tuple[str, str]]) -> list[str]:
    """product_ids whose full name (or id) appears in the text."""
    lowered = text.lower()
    found = []
    for product_id, name in names:
        if re.search(rf"\b{re.escape(name)}\b", lowered) or product_id in lowered:
            found.append(product_id)
    return found


def ensure_schema(db_path: Path) -> None:
    """Add the mentioned_products and conversation_id columns if missing, then fill them for old rows."""
    with _connect(db_path) as conn:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(chat_messages)")}
        if "mentioned_products" not in columns:
            conn.execute("ALTER TABLE chat_messages ADD COLUMN mentioned_products TEXT")
        if "conversation_id" not in columns:
            conn.execute("ALTER TABLE chat_messages ADD COLUMN conversation_id TEXT")
        _backfill(conn)
        _backfill_conversations(conn)


def _backfill_conversations(conn: sqlite3.Connection) -> None:
    """Group older messages into conversations by user, starting a new one after a long gap."""
    rows = conn.execute(
        "SELECT id, user_id, created_at FROM chat_messages WHERE conversation_id IS NULL ORDER BY user_id, id"
    ).fetchall()
    last_user, last_time, current = None, None, None
    for r in rows:
        t = datetime.fromisoformat(r["created_at"])
        if r["user_id"] != last_user or last_time is None or t - last_time > CONVERSATION_GAP:
            current = new_conversation_id()
        conn.execute("UPDATE chat_messages SET conversation_id = ? WHERE id = ?", (current, r["id"]))
        last_user, last_time = r["user_id"], t


def _backfill(conn: sqlite3.Connection) -> None:
    """Fill mentioned_products for rows saved before the column existed."""
    rows = conn.execute(
        "SELECT id, user_id, role, content, products_json FROM chat_messages"
        " WHERE mentioned_products IS NULL ORDER BY id"
    ).fetchall()
    if not rows:
        return
    names = _product_names(conn)
    for r in rows:
        if r["role"] == "assistant":
            cards = [p["product_id"] for p in json.loads(r["products_json"] or "[]")]
            mentioned = list(dict.fromkeys(cards + find_named_products(r["content"], names)))
        else:
            mentioned = find_named_products(r["content"], names)
            # Old rows have no tool-call record, so use the reply: if it was about
            # 1-3 specific items, that's what the customer was asking about.
            reply = conn.execute(
                "SELECT content, products_json FROM chat_messages"
                " WHERE user_id = ? AND id > ? AND role = 'assistant' ORDER BY id LIMIT 1",
                (r["user_id"], r["id"]),
            ).fetchone()
            if reply:
                cards = [p["product_id"] for p in json.loads(reply["products_json"] or "[]")]
                specific = cards if cards else find_named_products(reply["content"], names)
                if len(specific) <= SPECIFIC_MAX:
                    mentioned = list(dict.fromkeys(mentioned + specific))
        conn.execute(
            "UPDATE chat_messages SET mentioned_products = ? WHERE id = ?",
            (json.dumps(mentioned), r["id"]),
        )


def latest_conversation_id(db_path: Path, user_id: int) -> str | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT conversation_id FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    return row["conversation_id"] if row else None


def owns_conversation(db_path: Path, user_id: int, conversation_id: str) -> bool:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT user_id FROM chat_messages WHERE conversation_id = ? LIMIT 1", (conversation_id,)
        ).fetchone()
    return row is not None and row["user_id"] == user_id


def list_conversations(db_path: Path, user_id: int, limit: int = 30) -> list[dict]:
    """The customer's past chats, newest first, with dates and a preview."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT conversation_id, MIN(created_at) AS started_at, MAX(created_at) AS last_message_at,
                      COUNT(*) AS message_count, MAX(id) AS last_id,
                      (SELECT content FROM chat_messages f WHERE f.conversation_id = m.conversation_id
                         AND f.role = 'user' ORDER BY f.id LIMIT 1) AS first_message
               FROM chat_messages m WHERE user_id = ? GROUP BY conversation_id
               ORDER BY last_id DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return [
        {
            "conversation_id": r["conversation_id"],
            "started_at": r["started_at"],
            "last_message_at": r["last_message_at"],
            "message_count": r["message_count"],
            "preview": (r["first_message"] or "")[:80],
        }
        for r in rows
    ]


def load_conversation_rows(db_path: Path, user_id: int, conversation_id: str, limit: int) -> list[sqlite3.Row]:
    """Most recent messages of one conversation, oldest first."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT role, content, products_json, created_at FROM chat_messages"
            " WHERE user_id = ? AND conversation_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, conversation_id, limit),
        ).fetchall()
    return list(reversed(rows))


def load_history_turns(db_path: Path, user_id: int, conversation_id: str) -> list[ChatTurn]:
    """The agent's memory: recent messages from this conversation only."""
    rows = load_conversation_rows(db_path, user_id, conversation_id, MAX_HISTORY)
    return [ChatTurn(role=r["role"], content=r["content"]) for r in rows]


def save_exchange(
    db_path: Path,
    user_id: int,
    conversation_id: str,
    message: str,
    reply: str,
    cards: list[ProductCard],
    looked_up: list[str],
    count_cards: bool = True,
) -> None:
    """Store the customer's message and the reply, with the products each was about.

    looked_up: product_ids the agent fetched with get_product_details/check_stock
    this turn (including the product on the page when the customer said "this").
    count_cards: whether 1-3 cards shown count as the customer asking about them.
    """
    card_ids = [c.product_id for c in cards]
    with _connect(db_path) as conn:
        names = _product_names(conn)
        asked = find_named_products(message, names) + looked_up
        if count_cards and len(card_ids) <= SPECIFIC_MAX:
            asked += card_ids
        shown = card_ids + looked_up + find_named_products(reply, names)
        conn.execute(
            "INSERT INTO chat_messages (user_id, conversation_id, role, content, products_json, mentioned_products)"
            " VALUES (?, ?, 'user', ?, NULL, ?)",
            (user_id, conversation_id, message, json.dumps(list(dict.fromkeys(asked)))),
        )
        conn.execute(
            "INSERT INTO chat_messages (user_id, conversation_id, role, content, products_json, mentioned_products)"
            " VALUES (?, ?, 'assistant', ?, ?, ?)",
            (
                user_id,
                conversation_id,
                reply,
                json.dumps([c.model_dump() for c in cards]),
                json.dumps(list(dict.fromkeys(shown))),
            ),
        )


# ---------- Audit trail ----------
# Append-only audit trail of agent-loop activity: output/audit_trail.json.
#
# Every chat message the agent handles adds one entry: when it ran, who it was
# for (customer id or guest, never an email), every tool call with short
# args/results, and why the loop stopped. Entries are only ever appended; the
# file is never cleared between runs or server restarts.

AUDIT_PATH = Path(
    os.environ.get("AUDIT_TRAIL_PATH", Path(__file__).resolve().parent.parent / "output" / "audit_trail.json")
)
SHORT_LIMIT = 200  # characters kept from each arg/result
# The tool PydanticAI uses to return the structured ShopReply.
OUTPUT_TOOL = "final_result"

_lock = threading.Lock()


def short(value: object, limit: int = SHORT_LIMIT) -> str:
    """Compact, redacted, length-capped text for the log."""
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    text = redact(" ".join(text.split()))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds") if dt else None


def loop_events(messages: list[ModelMessage]) -> list[dict]:
    """Turn one run's messages into a timeline of tool calls, results, and retries."""
    events: list[dict] = []
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    events.append(
                        {
                            "time": _iso(msg.timestamp),
                            "type": "final_output" if part.tool_name == OUTPUT_TOOL else "tool_call",
                            "tool": part.tool_name,
                            "args": short(part.args_as_dict()),
                        }
                    )
        elif isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart) and part.tool_name != OUTPUT_TOOL:
                    events.append(
                        {
                            "time": _iso(part.timestamp),
                            "type": "tool_result",
                            "tool": part.tool_name,
                            "result": short(part.model_response_str()),
                        }
                    )
                elif isinstance(part, RetryPromptPart):
                    events.append(
                        {
                            "time": _iso(part.timestamp),
                            "type": "retry",
                            "tool": part.tool_name,
                            "result": short(part.model_response()),
                        }
                    )
    return events


def model_finish_reason(messages: list[ModelMessage]) -> str | None:
    for msg in reversed(messages):
        if isinstance(msg, ModelResponse):
            return msg.finish_reason
    return None


def append_entry(entry: dict) -> None:
    """Append one entry, keeping the file a valid JSON list. Never truncates history."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock, open(AUDIT_PATH.with_name(".audit_trail.lock"), "w") as lock_file:
        # File lock as well, in case two server processes write at once.
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        entries: list = []
        if AUDIT_PATH.exists() and AUDIT_PATH.stat().st_size > 0:
            try:
                entries = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
                if not isinstance(entries, list):
                    raise ValueError("audit trail is not a list")
            except ValueError:
                # Never overwrite a damaged log: keep it under a new name and start fresh.
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
                AUDIT_PATH.rename(AUDIT_PATH.with_name(f"audit_trail.corrupt-{stamp}.json"))
                entries = []
        entries.append(entry)
        tmp = AUDIT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, AUDIT_PATH)  # atomic: readers never see a half-written file


# ---------- App, products, and images ----------

app = FastAPI(title="Campus Customs API")

# Adds chat_messages.mentioned_products on first run and fills it for old rows.
ensure_schema(DB_PATH)

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


# ---------- Account routes ----------

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8
login_limiter = LoginLimiter()


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
        SESSION_COOKIE,
        make_session_token(user_id),
        max_age=SESSION_MAX_AGE,
        httponly=True,  # page JavaScript can't read the cookie
        samesite="lax",
        # Set secure=True when the site is served over HTTPS.
    )


def current_user(token: str | None) -> dict | None:
    user_id = read_session_token(token)
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
                    hash_password(req.password),
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

    stored = row["password_hash"] if row else DUMMY_HASH
    if not verify_password(req.password, stored) or row is None:
        login_limiter.record_failure(req.email)
        # Same message either way, so it doesn't reveal which emails have accounts.
        raise HTTPException(401, "Incorrect email or password")

    login_limiter.reset(req.email)
    _start_session(response, row["id"])
    return _user_from_row(row)


@app.post("/api/auth/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


@app.get("/api/auth/me", response_model=User | None)
def me(cc_session: str | None = Cookie(default=None)) -> dict | None:
    return current_user(cc_session)


# ---------- Chat routes ----------

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
    return list_conversations(DB_PATH, user["id"]) if user else []


@app.get("/api/chat/history", response_model=ChatConversation)
def chat_history(
    conversation_id: str | None = None, cc_session: str | None = Cookie(default=None)
) -> ChatConversation:
    """One saved conversation (default: the most recent), oldest message first."""
    user = current_user(cc_session)
    if user is None:
        return ChatConversation(conversation_id=None, messages=[])
    if conversation_id is None:
        conversation_id = latest_conversation_id(DB_PATH, user["id"])
    elif not owns_conversation(DB_PATH, user["id"], conversation_id):
        raise HTTPException(404, "Conversation not found")
    if conversation_id is None:
        return ChatConversation(conversation_id=None, messages=[])

    messages = []
    for r in load_conversation_rows(DB_PATH, user["id"], conversation_id, HISTORY_PAGE_SIZE):
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
        if conversation_id is None or not owns_conversation(DB_PATH, customer.id, conversation_id):
            conversation_id = new_conversation_id()
        history = load_history_turns(DB_PATH, customer.id, conversation_id)
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

    events = loop_events(run.messages)
    append_entry(
        {
            "time": started.isoformat(timespec="milliseconds"),
            "duration_ms": int((datetime.now(UTC) - started).total_seconds() * 1000),
            "model": MODEL_NAME,
            "customer": f"user #{customer.id}" if customer else "guest",
            "conversation_id": conversation_id,
            "page": deps.page.product_id or deps.page.path,
            "message": short(req.message),
            "events": events,
            "tool_calls": sum(1 for e in events if e["type"] == "tool_call"),
            "model_requests": run.requests,
            "tokens": {"input": run.input_tokens, "output": run.output_tokens},
            "stop_reason": run.stop_reason,
            "model_finish_reason": model_finish_reason(run.messages),
            "stop_detail": run.detail,
            "reply": short(reply) if reply else None,
            "cards_shown": len(cards),
            "reply_redacted": redacted,
        }
    )

    if reply is None:
        # Never send stack traces or keys to the browser.
        raise HTTPException(502, UNAVAILABLE)
    if customer:
        save_exchange(
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
