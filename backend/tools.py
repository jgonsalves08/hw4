"""Tools the Campus Customs agent can call.

Each tool takes a RunContext[AgentDeps] first, so it can read the database path
and the logged-in customer for the current request. All product facts (price,
description, stock) come from campus_customs.db through these tools, so the
agent never has to guess them.
"""

import json
import re
import sqlite3
from pathlib import Path

from pydantic_ai import RunContext

from models import (
    AgentDeps,
    PopularProduct,
    PopularProductsResult,
    ProductDetails,
    ProductSearchResult,
    ProductSummary,
    SizeStock,
    StockCheck,
    ToolError,
)

# ---------- Product categories and garment color ----------
# General product categories.
#
# The catalogue's garment_type has 22 inconsistent values ("pullover hoodie",
# "hooded sweatshirt", "short-sleeve T-shirt", ...). This maps each one to a
# general category used by the website filter and the agent's tools.

CATEGORIES = ["Hoodies", "Crewnecks", "Quarter-Zips", "T-Shirts", "Long Sleeve", "Fleece & Jackets"]

# Checked in order: "short-sleeve crew-neck t-shirt" must hit T-Shirts before
# Crewnecks, and "quarter-zip pullover sweatshirt" must hit Quarter-Zips.
_RULES = [
    ("hood", "Hoodies"),
    ("quarter-zip", "Quarter-Zips"),
    ("t-shirt", "T-Shirts"),
    ("long-sleeve", "Long Sleeve"),
    ("fleece", "Fleece & Jackets"),
    ("jacket", "Fleece & Jackets"),
    ("crew", "Crewnecks"),
    ("mockneck", "Crewnecks"),
]


def category_for(garment_type: str) -> str:
    text = garment_type.lower()
    for keyword, category in _RULES:
        if keyword in text:
            return category
    return "Other"


def normalize_category(value: str) -> str | None:
    """Match loose input like "hoodie", "tees", "quarter zip" to a category name."""
    text = value.lower().replace(" ", "").replace("-", "")
    aliases = {
        "hood": "Hoodies", "sweatshirt": "Crewnecks", "crew": "Crewnecks",
        "quarter": "Quarter-Zips", "zip": "Quarter-Zips", "tshirt": "T-Shirts", "tee": "T-Shirts",
        "longsleeve": "Long Sleeve", "fleece": "Fleece & Jackets", "jacket": "Fleece & Jackets",
    }
    for key, category in aliases.items():
        if key in text:
            return category
    return None


# The first entry in catalogue.colors is the garment's own color (it matches the
# start of the description for 99 of 102 products); the rest are logo/text colors.
# These three products have no color data, so their garment color was read from
# the product photos.
PRIMARY_COLOR_OVERRIDES = {
    "benjamin-franklin-t-shirt": "heather gray",
    "berkeley-sweater-fleece-jacket": "heather gray",
    "timothy-dwight-college-crewneck": "heather gray",
}


def primary_color(product_id: str, colors: list[str]) -> str | None:
    """The color of the garment itself (not its logo or lettering)."""
    if product_id in PRIMARY_COLOR_OVERRIDES:
        return PRIMARY_COLOR_OVERRIDES[product_id]
    return colors[0] if colors else None


# ---------- Database lookups ----------

SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL"]
SIZE_ALIASES = {
    "XSMALL": "XS", "EXTRASMALL": "XS", "SMALL": "S", "MEDIUM": "M", "MED": "M",
    "LARGE": "L", "XLARGE": "XL", "EXTRALARGE": "XL", "XXLARGE": "XXL", "2XL": "XXL",
}
DEFAULT_RESULTS = 12
MAX_RESULTS = 40
STOP_WORDS = {"a", "an", "the", "and", "or", "for", "with", "in", "of", "do", "you", "have", "any", "yale"}


def _connect(db_path: Path) -> sqlite3.Connection:
    # Read-only: the agent can look things up but can never change the database.
    conn = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_size(size: str) -> str | None:
    key = re.sub(r"[\s\-_.]", "", size).upper()
    key = SIZE_ALIASES.get(key, key)
    return key if key in SIZE_ORDER else None


def _sizes_for(conn: sqlite3.Connection, product_id: str) -> list[SizeStock]:
    rows = conn.execute(
        "SELECT size, quantity FROM inventory WHERE product_id = ?", (product_id,)
    ).fetchall()
    sizes = [SizeStock(size=r["size"], quantity=r["quantity"], in_stock=r["quantity"] > 0) for r in rows]
    return sorted(sizes, key=lambda s: SIZE_ORDER.index(s.size) if s.size in SIZE_ORDER else 99)


def _hit(word: str, text: str) -> int:
    """1 if the word (or its singular, e.g. hoodies -> hoodie) appears in text."""
    return int(word in text or (word.endswith("s") and word[:-1] in text))


def _not_found(product_id: str) -> ToolError:
    return ToolError(
        error=f"No product with id '{product_id}'.",
        hint="Call search_products to find the correct product_id.",
    )


def get_customer_profile(ctx: RunContext[AgentDeps]) -> str:
    """Return the logged-in customer's name and email, or say they are a guest."""
    c = ctx.deps.customer
    if c is None:
        return "The customer is browsing as a guest (not logged in)."
    return f"Name: {c.first_name} {c.last_name}. Email: {c.email}."


def get_current_page(ctx: RunContext[AgentDeps]) -> str:
    """Return the page the customer is looking at, including the product if they're on a product page."""
    page = ctx.deps.page
    if page is None:
        return "Unknown page."
    if page.product_id:
        return f"Product page for {page.product_name} (product_id: {page.product_id})."
    return f"Page {page.path} (not a single product page)."


def search_products(
    ctx: RunContext[AgentDeps],
    query: str = "",
    category: str | None = None,
    max_price: float | None = None,
    in_stock_only: bool = False,
    limit: int = DEFAULT_RESULTS,
) -> ProductSearchResult:
    """Search the Campus Customs catalogue by keywords.

    Matches against product name, garment type, description, colors, and tags.
    Use this first to find a product_id when the customer names or describes an item.

    Args:
        query: Words describing the product, e.g. "navy hoodie", "Pierson crewneck", "Harvard game tee".
            Can be empty when filtering by category only.
        category: Optional general category: Hoodies, Crewnecks, Quarter-Zips, T-Shirts,
            Long Sleeve, or Fleece & Jackets. Use it for "what <type> do you have?" questions
            so every item of that type is found, even ones whose names don't contain the word.
        max_price: Only return products at or below this price in US dollars.
        in_stock_only: Only return products with at least one size in stock.
        limit: Maximum matches to return (default 12, up to 40). Use a higher limit for broad
            browsing questions like "what hoodies do you have?".
    """
    wanted = normalize_category(category) if category else None
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1 and w not in STOP_WORDS]
    if wanted:
        # The category filter already covers type words like "hoodies" or "tees".
        words = [w for w in words if normalize_category(w) != wanted]
    with _connect(ctx.deps.db_path) as conn:
        rows = conn.execute(
            """SELECT c.*, COALESCE(SUM(i.quantity), 0) AS total_stock
               FROM catalogue c LEFT JOIN inventory i ON i.product_id = c.product_id
               GROUP BY c.product_id"""
        ).fetchall()

    scored: list[tuple[int, ProductSummary]] = []
    for r in rows:
        if max_price is not None and r["price"] > max_price:
            continue
        if in_stock_only and r["total_stock"] == 0:
            continue
        if wanted and category_for(r["garment_type"]) != wanted:
            continue
        name_text = f"{r['name']} {r['garment_type']}".lower()
        other_text = f"{r['description']} {r['colors']} {r['search_tags']}".lower()
        # Name/type hits count double so "hoodie" ranks hoodies above items that only mention hoods.
        score = sum(_hit(w, name_text) * 2 or _hit(w, other_text) for w in words)
        if words and score == 0:
            continue
        scored.append((score, ProductSummary(
            product_id=r["product_id"],
            name=r["name"],
            garment_type=r["garment_type"],
            category=category_for(r["garment_type"]),
            primary_color=primary_color(r["product_id"], json.loads(r["colors"])),
            price=r["price"],
            colors=json.loads(r["colors"]),
            total_stock=r["total_stock"],
            in_stock=r["total_stock"] > 0,
        )))

    scored.sort(key=lambda t: (-t[0], t[1].name))
    shown = [p for _, p in scored[: max(1, min(limit, MAX_RESULTS))]]
    return ProductSearchResult(query=query, total_matches=len(scored), matches=shown)


def get_product_details(ctx: RunContext[AgentDeps], product_id: str) -> ProductDetails | ToolError:
    """Get the full description, price, colors, and stock for every size of one product.

    Args:
        product_id: The id from search_products, e.g. "basic-hoodie-big-yale".
    """
    with _connect(ctx.deps.db_path) as conn:
        r = conn.execute("SELECT * FROM catalogue WHERE product_id = ?", (product_id,)).fetchone()
        if r is None:
            return _not_found(product_id)
        sizes = _sizes_for(conn, product_id)

    return ProductDetails(
        product_id=r["product_id"],
        name=r["name"],
        garment_type=r["garment_type"],
        description=r["description"],
        price=r["price"],
        primary_color=primary_color(r["product_id"], json.loads(r["colors"])),
        colors=json.loads(r["colors"]),
        sizes=sizes,
        total_stock=sum(s.quantity for s in sizes),
        out_of_stock_sizes=[s.size for s in sizes if not s.in_stock],
        url=f"/products/{r['product_id']}",
    )


def check_stock(
    ctx: RunContext[AgentDeps], product_id: str, size: str | None = None
) -> StockCheck | ToolError:
    """Check how many units of a product are in stock, for one size or all sizes.

    Always use this for stock or availability questions; never guess quantities.

    Args:
        product_id: The id from search_products.
        size: Optional size to check: XS, S, M, L, XL, or XXL (words like "medium" also work).
    """
    requested = None
    if size:
        requested = _normalize_size(size)
        if requested is None:
            return ToolError(
                error=f"'{size}' is not a size we carry.",
                hint=f"Sizes are {', '.join(SIZE_ORDER)}.",
            )

    with _connect(ctx.deps.db_path) as conn:
        r = conn.execute("SELECT name FROM catalogue WHERE product_id = ?", (product_id,)).fetchone()
        if r is None:
            return _not_found(product_id)
        all_sizes = _sizes_for(conn, product_id)

    total = sum(s.quantity for s in all_sizes)
    if requested:
        sizes = [s for s in all_sizes if s.size == requested]
        qty = sizes[0].quantity if sizes else 0
        if qty > 0:
            summary = f"{r['name']} in size {requested}: {qty} in stock."
        else:
            others = [f"{s.size} ({s.quantity})" for s in all_sizes if s.in_stock]
            summary = f"{r['name']} in size {requested} is OUT OF STOCK." + (
                f" Sizes in stock: {', '.join(others)}." if others else " No other sizes are in stock."
            )
    else:
        sizes = all_sizes
        out = [s.size for s in all_sizes if not s.in_stock]
        summary = f"{r['name']}: {total} in stock across all sizes." + (
            f" Out of stock in: {', '.join(out)}." if out else " Every size is in stock."
        )
        if total == 0:
            summary = f"{r['name']} is OUT OF STOCK in every size."

    return StockCheck(
        product_id=product_id,
        name=r["name"],
        requested_size=requested,
        sizes=sizes,
        total_stock=total,
        summary=summary,
    )


def get_popular_products(
    ctx: RunContext[AgentDeps], category: str | None = None, limit: int = 5
) -> PopularProductsResult | ToolError:
    """Rank products by how often shoppers have asked about them in chat.

    Counts customer messages across all saved chats (logged-in customers) whose
    mentioned_products include each product. Returns totals only, never who asked.
    Use for questions like "what's your most popular hoodie?" or "what are people buying?".

    Args:
        category: Optional general category, e.g. "hoodies", "t-shirts", "quarter-zips".
        limit: How many top products to return (default 5, max 10).
    """
    wanted = None
    if category:
        wanted = normalize_category(category)
        if wanted is None:
            return ToolError(
                error=f"'{category}' isn't a product category.",
                hint=f"Categories are: {', '.join(CATEGORIES)}.",
            )

    with _connect(ctx.deps.db_path) as conn:
        rows = conn.execute(
            "SELECT mentioned_products FROM chat_messages"
            " WHERE role = 'user' AND mentioned_products IS NOT NULL AND mentioned_products != '[]'"
        ).fetchall()
        catalogue = {
            r["product_id"]: r
            for r in conn.execute("SELECT product_id, name, garment_type, price FROM catalogue")
        }

    counts: dict[str, int] = {}
    for r in rows:
        for pid in set(json.loads(r["mentioned_products"])):
            if pid in catalogue:
                counts[pid] = counts.get(pid, 0) + 1

    ranking = [
        PopularProduct(
            product_id=pid,
            name=catalogue[pid]["name"],
            category=category_for(catalogue[pid]["garment_type"]),
            price=catalogue[pid]["price"],
            times_asked_about=n,
        )
        for pid, n in counts.items()
        if wanted is None or category_for(catalogue[pid]["garment_type"]) == wanted
    ]
    ranking.sort(key=lambda p: (-p.times_asked_about, p.name))
    return PopularProductsResult(
        category=wanted,
        messages_analyzed=len(rows),
        ranking=ranking[: max(1, min(limit, 10))],
        note=(
            "Based on how many times logged-in shoppers asked about each product in chat "
            "(not sales data). Guest chats aren't saved, so they aren't counted."
        ),
    )


TOOLS = [
    get_customer_profile,
    get_current_page,
    search_products,
    get_product_details,
    check_stock,
    get_popular_products,
]
