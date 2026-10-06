"""General product categories.

The catalogue's garment_type has 22 inconsistent values ("pullover hoodie",
"hooded sweatshirt", "short-sleeve T-shirt", ...). This maps each one to a
general category used by the website filter and the agent's tools.
"""

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
