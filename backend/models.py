"""Pydantic / PydanticAI structured types for the Campus Customs chat agent."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

MAX_MESSAGE_LENGTH = 2000
MAX_HISTORY = 20


class ChatTurn(BaseModel):
    """One earlier message in the conversation, sent by the chat widget."""

    role: Literal["user", "assistant"]
    content: str = Field(max_length=MAX_MESSAGE_LENGTH * 4)


class PageInfo(BaseModel):
    """Where the customer is on the site when they send a message."""

    path: str = Field(default="/", max_length=200, description="Current URL path, e.g. /products/pierson-college-crewneck.")
    product_id: str | None = Field(default=None, max_length=200, description="Set when the customer is on a single-item page.")


class ChatRequest(BaseModel):
    """Body of POST /api/chat."""

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    # Only used for guests; logged-in customers' history is loaded from the database.
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY)
    page: PageInfo = Field(default_factory=PageInfo)
    # Logged-in customers: which saved conversation this message belongs to.
    # None starts a new conversation (the "New chat" button).
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")


class ProductCard(BaseModel):
    """One product as the website displays it (Products grid and chat search results)."""

    product_id: str
    name: str
    garment_type: str
    category: str = Field(description="General category, e.g. Hoodies or T-Shirts.")
    description: str
    primary_color: str | None = Field(description="Color of the garment itself (not logo/lettering).")
    colors: list[str]
    search_tags: list[str]
    image_url: str
    price: float
    total_stock: int


class ChatResponse(BaseModel):
    """What the chat route sends back to the website."""

    reply: str
    products: list[ProductCard] = Field(
        default_factory=list,
        description="Cards for the page to show; empty when the reply isn't about specific items.",
    )
    conversation_id: str | None = Field(
        default=None, description="The saved conversation this reply belongs to (logged-in customers only)."
    )


class SavedChatMessage(BaseModel):
    """One stored message returned by GET /api/chat/history."""

    role: Literal["user", "assistant"]
    content: str
    products: list[ProductCard] = Field(default_factory=list)
    created_at: str = Field(description="UTC timestamp, 'YYYY-MM-DD HH:MM:SS'.")


class ChatConversation(BaseModel):
    """A saved conversation, returned by GET /api/chat/history."""

    conversation_id: str | None
    messages: list[SavedChatMessage]


class ConversationSummary(BaseModel):
    """One entry in the customer's list of past chats."""

    conversation_id: str
    started_at: str
    last_message_at: str
    message_count: int
    preview: str = Field(description="The customer's first message, shortened.")


MAX_CARDS = 40


class ShopReply(BaseModel):
    """Structured output the agent must return."""

    reply: str = Field(description="The message shown to the customer, in the Campus Customs voice.")
    product_ids: list[str] = Field(
        default_factory=list,
        max_length=MAX_CARDS,
        description=(
            "product_id values (from search_products or get_product_details results in this turn) "
            "to show as product cards on the website, best match first. Empty if no items should be shown."
        ),
    )


# ---------- Tool return types (database lookups) ----------


class SizeStock(BaseModel):
    """Stock for one size of one product, straight from the inventory table."""

    size: str = Field(description="One of XS, S, M, L, XL, XXL.")
    quantity: int = Field(ge=0, description="Units on hand for this size.")
    in_stock: bool = Field(description="False means this size is OUT OF STOCK.")


class ProductSummary(BaseModel):
    """Short search result: enough to pick the right product and answer simple price questions."""

    product_id: str = Field(description="Use this id with get_product_details or check_stock.")
    name: str
    garment_type: str
    category: str = Field(description="General category: Hoodies, Crewnecks, Quarter-Zips, T-Shirts, Long Sleeve, or Fleece & Jackets.")
    primary_color: str | None = Field(description="Color of the garment itself. Use this for color requests like \"navy hoodie\".")
    price: float = Field(description="Price in US dollars, from the catalogue.")
    colors: list[str]
    total_stock: int = Field(ge=0, description="Units on hand across all sizes.")
    in_stock: bool = Field(description="True if at least one size has stock.")


class ProductSearchResult(BaseModel):
    query: str
    total_matches: int = Field(description="How many products matched before the limit was applied.")
    matches: list[ProductSummary] = Field(description="Best matches first; empty if nothing matched.")


class ProductDetails(BaseModel):
    """Full record for one product, including stock by size."""

    product_id: str
    name: str
    garment_type: str
    description: str
    price: float = Field(description="Price in US dollars, from the catalogue.")
    primary_color: str | None = Field(description="Color of the garment itself (not logo/lettering).")
    colors: list[str] = Field(description="All colors on the product, garment first, then logo/lettering colors.")
    sizes: list[SizeStock] = Field(description="Every size, XS to XXL, with its quantity.")
    total_stock: int = Field(ge=0)
    out_of_stock_sizes: list[str] = Field(description="Sizes with zero units.")
    url: str = Field(description="Site path for this product's page.")


class StockCheck(BaseModel):
    """Stock answer for one product, optionally narrowed to one size."""

    product_id: str
    name: str
    requested_size: str | None = Field(description="The size asked about, or None for all sizes.")
    sizes: list[SizeStock]
    total_stock: int = Field(ge=0)
    summary: str = Field(description="Plain-language stock statement to base the answer on.")


class PopularProduct(BaseModel):
    """One product ranked by how often shoppers asked about it in chat."""

    product_id: str
    name: str
    category: str
    price: float
    times_asked_about: int = Field(description="Number of customer chat messages that asked about this product.")


class PopularProductsResult(BaseModel):
    """Aggregate popularity from all saved customer chats (no customer details)."""

    category: str | None = Field(description="Category filter applied, or None for all products.")
    messages_analyzed: int = Field(description="Customer chat messages that mentioned at least one product.")
    ranking: list[PopularProduct] = Field(description="Most asked-about first; empty if there's no chat data yet.")
    note: str = Field(description="How the ranking was measured, to explain it honestly to the customer.")


class ToolError(BaseModel):
    """Returned instead of a result when a lookup can't be completed."""

    error: str
    hint: str = Field(description="What to try next, e.g. search_products to find the product_id.")


@dataclass
class Customer:
    """The logged-in shopper, loaded from the users table by the session cookie."""

    id: int
    first_name: str
    last_name: str
    email: str


@dataclass
class PageContext:
    """The page the customer is on, checked against the database by the backend."""

    path: str
    product_id: str | None = None
    product_name: str | None = None


@dataclass
class AgentDeps:
    """Per-request context handed to the agent and its tools."""

    db_path: Path
    customer: Customer | None = None
    page: PageContext | None = None
