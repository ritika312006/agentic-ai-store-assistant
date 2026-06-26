"""
rule_based_router.py
---------------------
A deterministic, no-API-key-required fallback agent.

Why this exists (see DESIGN_DOC.md):
- The LLM-driven agent (agent_core.py) is the "real" deliverable, but it
  requires a valid API key and network access. This fallback guarantees
  the project is runnable and demoable in any environment (offline,
  no API key, API outage) -- which matters for evaluators cloning the repo.
- It uses simple regex/keyword extraction to decide which tool(s) to call,
  then chains them exactly like the LLM agent would.

This file deliberately mirrors the LLM agent's *behavior* (same tool
chaining logic, same graceful error handling) so the two are easy to compare.
"""

import re
from agent.tools import get_order, get_product, search_products
from agent.logger import log_tool_call

ORDER_ID_PATTERN = re.compile(r"\bORD-\d+\b", re.IGNORECASE)
PRODUCT_ID_PATTERN = re.compile(r"\bPRD-\d+\b", re.IGNORECASE)

CHEAPER_KEYWORDS = ["cheaper", "cheap", "less expensive", "lower price", "discount", "alternative", "instead"]
STATUS_KEYWORDS = ["where", "track", "status", "shipped", "delivery", "arrive"]


def _format_order(order: dict) -> str:
    status_map = {
        "delivered": f"it was delivered on {order.get('delivery_date')}.",
        "in_transit": f"it's currently in transit, with estimated delivery on {order.get('estimated_delivery')}.",
        "processing": "it's still being processed and hasn't shipped yet.",
        "cancelled": f"it was cancelled. Reason: {order.get('cancellation_reason', 'not specified')}.",
    }
    items = ", ".join(f"{i['name']} (x{i['quantity']})" for i in order["items"])
    detail = status_map.get(order["status"], f"its status is '{order['status']}'.")
    tracking = f" Tracking number: {order['tracking_number']}." if order.get("tracking_number") else ""
    return f"Your order {order['order_id']} ({items}) -- {detail}{tracking}"


def _format_cheaper_alternative(reference_product: dict, alternatives: list) -> str:
    cheaper = [p for p in alternatives if p["price"] < reference_product["price"] and p["product_id"] != reference_product["product_id"]]
    cheaper.sort(key=lambda p: p["price"])
    if not cheaper:
        return (
            f"I checked, but I couldn't find a cheaper alternative to {reference_product['name']} "
            f"(${reference_product['price']:.2f}) in our catalog right now."
        )
    best = cheaper[0]
    return (
        f"Yes! A cheaper alternative to {reference_product['name']} (${reference_product['price']:.2f}) "
        f"is {best['name']} at ${best['price']:.2f} "
        f"({'in stock' if best['in_stock'] else 'currently out of stock'})."
    )


def run_agent_rule_based(question: str) -> str:
    """
    Deterministic fallback agent. Same external contract as run_agent():
    takes a raw customer question, returns a customer-friendly string.
    """
    q = question.strip()
    q_lower = q.lower()

    order_match = ORDER_ID_PATTERN.search(q)
    product_match = PRODUCT_ID_PATTERN.search(q)
    wants_cheaper = any(kw in q_lower for kw in CHEAPER_KEYWORDS)

    # Case 1: question references an order AND asks for a cheaper alternative
    # -> chain get_order -> search_products
    if order_match and wants_cheaper:
        order_id = order_match.group(0)
        order = log_tool_call("get_order", {"order_id": order_id}, get_order(order_id))
        if not order:
            return f"I couldn't find any order with ID {order_id}. Could you double-check the order number?"

        first_item = order["items"][0]
        ref_product = log_tool_call(
            "get_product", {"product_id": first_item["product_id"]}, get_product(first_item["product_id"])
        )
        if not ref_product:
            return (
                f"I found your order {order_id}, but I couldn't retrieve details for the product in it, "
                f"so I can't suggest an alternative right now."
            )

        candidates = log_tool_call(
            "search_products", {"query": ref_product["category"]}, search_products(ref_product["category"])
        )
        return _format_cheaper_alternative(ref_product, candidates)

    # Case 2: question is purely about order status/tracking -> get_order
    if order_match:
        order_id = order_match.group(0)
        order = log_tool_call("get_order", {"order_id": order_id}, get_order(order_id))
        if not order:
            return f"I couldn't find any order with ID {order_id}. Could you double-check the order number?"
        return _format_order(order)

    # Case 3: question references a specific product ID -> get_product
    if product_match:
        product_id = product_match.group(0)
        product = log_tool_call("get_product", {"product_id": product_id}, get_product(product_id))
        if not product:
            return f"I couldn't find any product with ID {product_id}. Could you double-check the product ID?"
        stock = "in stock" if product["in_stock"] else "currently out of stock"
        return f"{product['name']} is priced at ${product['price']:.2f} and is {stock}. {product['description']}"

    # Case 4: generic product search (e.g. "do you have running shoes?")
    if any(kw in q_lower for kw in ["do you have", "looking for", "search", "find me", "show me"]) or wants_cheaper:
        query = q_lower
        results = log_tool_call("search_products", {"query": query}, search_products(query))
        if not results:
            return "I couldn't find any products matching that. Could you try different keywords?"
        top = sorted(results, key=lambda p: p["price"])[:3]
        listing = "; ".join(f"{p['name']} (${p['price']:.2f})" for p in top)
        return f"Here are some options I found: {listing}."

    # Case 5: nothing recognizable -> ask for clarification, never guess
    return (
        "I'm not sure what you're asking about. Could you share an order number (e.g. ORD-1002), "
        "a product ID, or describe what product you're looking for?"
    )
