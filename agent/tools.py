"""
tools.py
---------
The three "ground truth" data-access functions available to the agent.

Design principles (see DESIGN_DOC.md for full rationale):
- Each tool is a pure read function against mock JSON data (simulating a DB / API).
- Tools NEVER raise exceptions for "not found" cases — they return None or []
  so the calling agent can produce a graceful, customer-friendly message
  instead of crashing or fabricating data.
- Tools NEVER guess or auto-correct identifiers. If an order/product id
  doesn't exist, that's a clean miss, not an error.
"""

import json
import os
import re
from typing import Optional

_STOPWORDS = {
    "a", "an", "the", "is", "are", "do", "you", "have", "any", "i", "me", "my",
    "for", "of", "to", "in", "on", "want", "looking", "show", "find", "search",
    "there", "got", "need", "please", "can", "with",
}

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

with open(os.path.join(_DATA_DIR, "orders.json"), "r", encoding="utf-8") as f:
    _ORDERS = {o["order_id"].upper(): o for o in json.load(f)}

with open(os.path.join(_DATA_DIR, "products.json"), "r", encoding="utf-8") as f:
    _PRODUCTS = {p["product_id"].upper(): p for p in json.load(f)}

_PRODUCTS_LIST = list(_PRODUCTS.values())


def get_order(order_id: str) -> Optional[dict]:
    """
    Fetch order details by order ID.

    Args:
        order_id: e.g. "ORD-1002" (case-insensitive, whitespace-tolerant)

    Returns:
        dict with order details, or None if the order does not exist.
    """
    if not order_id or not isinstance(order_id, str):
        return None
    key = order_id.strip().upper()
    return _ORDERS.get(key)  # None if missing -> caller must NOT fabricate


def search_products(query: str) -> list:
    """
    Search products using keyword matching against name, category,
    and description.

    Args:
        query: free-text search string, e.g. "shoes", "cheap sneakers"

    Returns:
        List of matching product dicts. Empty list if nothing matches
        (caller must report this honestly, not invent a result).
    """
    if not query or not isinstance(query, str):
        return []

    # Strip punctuation so "electronics?" / "shoes," etc. still match cleanly,
    # and drop common stopwords so full-sentence queries don't produce noisy matches.
    cleaned = re.sub(r"[^\w\s-]", " ", query.strip().lower())
    terms = [t for t in cleaned.split() if t and t not in _STOPWORDS]
    if not terms:
        return []

    results = []
    for product in _PRODUCTS_LIST:
        haystack = " ".join([
            product["name"],
            product["category"],
            product["description"],
        ]).lower()
        if any(term in haystack for term in terms):
            results.append(product)

    return results


def get_product(product_id: str) -> Optional[dict]:
    """
    Fetch product details by product ID.

    Args:
        product_id: e.g. "PRD-001" (case-insensitive, whitespace-tolerant)

    Returns:
        dict with product details, or None if the product does not exist.
    """
    if not product_id or not isinstance(product_id, str):
        return None
    key = product_id.strip().upper()
    return _PRODUCTS.get(key)


# Tool schemas in Claude's native tool-use format.
# Kept alongside the functions so signatures and schemas can never drift apart.
TOOL_SCHEMAS = [
    {
        "name": "get_order",
        "description": (
            "Fetch order details (status, items, tracking number, delivery date, "
            "shipping address) given an order ID. Returns null if the order ID "
            "does not exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order ID, e.g. 'ORD-1002'.",
                }
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "search_products",
        "description": (
            "Search the product catalog using a free-text keyword query "
            "(matches against name, category, and description). Returns an "
            "empty list if nothing matches -- do not assume or invent results "
            "in that case."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords to search for, e.g. 'cheap running shoes'.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_product",
        "description": (
            "Fetch full product details (name, price, category, stock status, "
            "rating, description) given a product ID. Returns null if the "
            "product ID does not exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "The product ID, e.g. 'PRD-001'.",
                }
            },
            "required": ["product_id"],
        },
    },
]

# Dispatch table used by the agent core to actually execute a tool call by name.
TOOL_FUNCTIONS = {
    "get_order": get_order,
    "search_products": search_products,
    "get_product": get_product,
}


# --------------------------------------------------------------------------
# UI-only helpers (NOT used by the agent itself -- only so the Streamlit
# interface can show real orders/products/categories as clickable buttons
# instead of asking the user to type IDs from memory).
# --------------------------------------------------------------------------

def list_orders() -> list:
    """Returns all orders, for populating UI selection buttons."""
    return list(_ORDERS.values())


def list_categories() -> list:
    """Returns all distinct product categories, for UI selection buttons."""
    return sorted({p["category"] for p in _PRODUCTS_LIST})


def list_products(category: str = None) -> list:
    """Returns all products, optionally filtered by category, for UI buttons."""
    if category:
        return [p for p in _PRODUCTS_LIST if p["category"] == category]
    return list(_PRODUCTS_LIST)
