"""Saving and loading chat history in the chat_messages table.

Each row also records mentioned_products: a JSON list of the product_ids that
message was about. On user rows this is what the customer asked about; on
assistant rows it's what the reply looked up or showed. The popularity tool
counts the user rows.
"""

import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from models import MAX_HISTORY, ChatTurn, ProductCard

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
