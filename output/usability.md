# Usability Improvements (Problem 9)

Four improvements to Campus Customs: two on the website (front end) and two in the shopping assistant (agent / back end). Each lists what was added and why it helps a Campus Customs shopper or the business.

---

## Front end

### 1. Filter products by general type

**What was added**

- A row of filter buttons at the top of the **Products** page: **All, Hoodies, Crewnecks, Quarter-Zips, T-Shirts, Long Sleeve, Fleece & Jackets**. Each button shows how many items are in that group (e.g. "Hoodies 27"), giving a quick breakdown of the whole catalogue.
- Clicking a type filters the product cards to just that type. Clicking it again (or **All**) shows everything.
- The filter works on chat search results too, and the counts update to match what's on screen.
- The chosen filter is saved in the page URL (e.g. `/products?category=Hoodies`), so it's still applied after opening an item and pressing Back, and the link can be shared.
- Behind the scenes: the database's `garment_type` column has 22 inconsistent labels ("pullover hoodie", "hooded sweatshirt", "short-sleeve T-shirt", "t-shirt", …). the category mapping in `backend/tools.py` groups them into 6 general categories, and every product returned by the API now includes a `category` field.

**Why it helps**

- **Shoppers** see what Campus Customs carries at a glance and can jump straight to the type they want instead of scrolling through 102 cards. Grouping fixes messy labels: a "hooded sweatshirt" and a "pullover hoodie" both appear under Hoodies, so nothing is missed.
- **The business** gets shoppers to relevant products faster, which reduces drop-off. The counts also show depth in each category (e.g. 29 crewnecks vs. 2 long-sleeve shirts).

### 2. Price range slider

**What was added**

- A slider with **two handles** on the Products page that runs from the least expensive item ($32) to the most expensive ($98). Shoppers drag either end to set a minimum and maximum price, and the label shows the range (e.g. "Price: $40.00 – $60.00").
- Product cards update immediately to show only items in that range. It combines with the type filter (e.g. Hoodies from $32–$60 shows the 2 hoodies at $45).
- A "Showing X of Y" line, a **Clear filters** link, and a friendly message if nothing matches.
- The range is saved in the URL (`?min=40&max=60`), so it survives opening an item and going back.

**Why it helps**

- **Shoppers**, especially students on a budget or someone buying a gift, see only what fits their price point instead of opening items to check prices.
- **The business** keeps budget-conscious shoppers engaged by showing what they *can* buy, and shoppers looking at higher price points can find premium items like the $98 fleeces quickly.

---

## Agent / back end

### 3. "What's most popular?" tool

**What was added**

- A new agent tool, `get_popular_products(category, limit)` in `backend/tools.py`. It reads **all customers' saved chat history**, counts how many customer messages asked about each product, and returns the top products (optionally within a category like "hoodies"). Each result has its name, category, price, and `times_asked_about`.
- It returns **totals only**. It never returns who asked or what anyone else said.
- `prompt.md` rules: always call the tool for "most popular / best seller / trending" questions; explain honestly that it's based on **chat interest, not sales**; never reveal which customers asked; say when there isn't much data; mention ties; show the top items as product cards.
- Safeguard: when a customer asks "what's popular?", the cards in that answer are **not** counted as the customer asking about them. Otherwise every popularity question would boost its own answer and the ranking would feed on itself.
- Also added during this work: `search_products` gained a `category` option, so "what T-shirts do you have?" returns all 25 T-shirts. Plain keyword search had missed some whose names don't say "T-shirt".

**Why it helps**

- **Shoppers** who are unsure what to buy get social proof ("the Basic Hoodie Big Yale is the hoodie shoppers ask about most"), and they get an honest answer instead of a made-up "best seller".
- **The business** can recommend items customers already show interest in without exposing anyone's private conversations.

### 4. Track the products mentioned in each chat message

**What was added**

- A new column, **`mentioned_products`**, on the `chat_messages` table. It holds a JSON list of `product_id`s.
  - **Customer rows:** the products the customer asked about. This means products named in their message, products the agent looked up for them with `get_product_details` or `check_stock` (which covers "do you have *this* in pink?" on a product page), and a short answer's 1–3 product cards.
  - **Assistant rows:** every product the reply looked up, named, or showed as a card.
  - Broad browsing ("what hoodies do you have?" → 27 cards) isn't counted as asking about all 27, so the data reflects real interest.
- The column is added automatically when the server starts (`ensure_schema` in `backend/main.py`), and is safe to run more than once. Messages saved before the column existed were filled in from their text and the reply that followed (e.g. "you have this in pink?" → the Baseball Left Chest Crewneck).
- Chat saving and loading live in the chat-history section of `backend/main.py`. The agent run now reports which tools it used and which products it looked up, so they can be recorded.

**Why it helps**

- **The business** gets structured data on what shoppers are asking about. It can see which products, categories, and colors draw questions, and use that for stocking, promotions, and the popularity tool above, without reading through chat transcripts.
- **Shoppers** benefit indirectly: popularity answers and future recommendations are based on real interest. Because product IDs are stored rather than personal details, the data can be analyzed in aggregate.

---

## Checks run

| Improvement | Test | Result |
|---|---|---|
| Type filter | Buttons and counts | All 102, Hoodies 27, Crewnecks 29, Quarter-Zips 11, T-Shirts 25, Long Sleeve 2, Fleece & Jackets 8 (sums to 102) |
| Type filter | Click Quarter-Zips | 11 cards, all $72.00, URL `?category=Quarter-Zips` |
| Price slider | Set $40–$60 | 33 cards ($45 and $58 only); database count for $40–$60 is 33 |
| Both | Hoodies + max $60 | 2 cards (UA Gameday Double Knit Hood, Yale Sports Hoodie Tennis, both $45) |
| Both | Open a card, press Back | Filters still applied (`?category=Hoodies&max=60`) |
| Mentions | "Is the Yale Dad Hoodie in stock in large?" | Customer row `["yale-dad-hoodie"]` |
| Mentions | On Yale Mom Hoodie page: "How much is this?" | Customer row `["yale-mom-hoodie"]` |
| Mentions | "What t-shirts do you have?" | Customer row `[]` (browsing), assistant row lists the cards shown |
| Popularity | "Which hoodie do people ask about the most?" | Three-way tie, explained as chat interest, not sales; that question saved as `[]` so it doesn't inflate the ranking |
| Popularity | "…and which customers asked about them?" | Declined to share customer identities; gave totals only |
| Popularity | "Most popular long sleeve shirt?" | Said there isn't much chat data yet and offered to show long-sleeve shirts |
| Category search | "What t-shirts do you have?" | All 25 T-shirts (previously 14) |

Agent tests ran on a scratch copy of the database; the real database only received the new column and the backfill of its existing 22 messages.
