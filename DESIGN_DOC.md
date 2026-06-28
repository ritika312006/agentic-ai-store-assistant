# Design Document — Agentic AI Store Assistant

## 1. Problem & approach

The assignment asks for an agent that answers customer questions about an online store by deciding, on its own, which of three tools to call (`get_order`, `search_products`, `get_product`), chaining them when one question needs more than one lookup, and replying in plain English without inventing data.

The core design decision was: **let an LLM actually do the deciding**, rather than writing if/else logic that pattern-matches keywords and pretends to be "agentic." A keyword router can satisfy the letter of the spec but not its intent — the whole point is autonomous tool selection and reasoning.

## 2. Architecture

```
agent/tools.py             3 required tools, reading from mock JSON data
agent/agent_core.py        run_agent() -- the LLM tool-calling loop
agent/rule_based_router.py deterministic fallback (no API key needed)
agent/logger.py            logs every tool call
data/orders.json           6 mock orders
data/products.json         12 mock products
app_streamlit.py           guided web UI (bonus)
tests/test_agent.py         20 pytest tests (bonus)
```

`run_agent(question)` is the single entry point required by the spec. Internally it:
1. Sends the question + tool schemas to an LLM.
2. Executes whatever tool call(s) the LLM requests, against the real (mock) data.
3. Feeds results back; the LLM can call more tools (chaining) or finish with an answer.
4. Returns the final natural-language answer.

## 3. LLM provider choice: Gemini over a paid API

I initially built this against the Anthropic API, but switched the primary provider to **Google Gemini** (`gemini-2.5-flash`) because it has a genuinely free tier with no credit card required. This matters for a student assignment that has to actually run on a grader's or mentor's machine without them needing to pay for anything. The code is written provider-agnostically — `agent_core.py` has separate `_run_gemini()` and `_run_anthropic()` functions sharing the same tool schemas and system prompt, so switching providers is a one-line change. This also satisfies the assignment's bonus point ("use any LLM provider") without locking the grader into a paid service.

## 4. The fallback router: a deliberate reliability feature

`rule_based_router.py` re-implements the same question types (order status, cheaper alternative, product lookup, search, ambiguous input) using regex and keyword matching, with zero external dependencies. `run_agent()` uses this in two situations:
- No API key is configured at all.
- The LLM call throws an exception for any reason (network failure, rate limit, invalid key).

This was a conscious trade-off: a "pure" agentic implementation would just fail or show an error in these cases. Instead, the agent degrades gracefully and still answers correctly, just without genuine LLM reasoning. I think this is good engineering practice (the "Error handling" criterion is worth 20% of the grade) and it also means the project is demoable instantly, with zero setup, even before a grader configures any API key.

## 5. Tool design: returning `None`/`[]` instead of raising

All three tools never throw exceptions for "not found" cases — `get_order` and `get_product` return `None`, `search_products` returns `[]`. This was deliberate: it keeps the "is this a real miss or a bug" distinction clean, and it forces every caller (the LLM, the rule-based router) to explicitly handle the empty case rather than letting a stack trace leak Python internals to a customer-facing message. This directly supports the "do not fabricate data" requirement — there's no path where the code has to guess what a missing record might contain.

## 6. Why I added a UI beyond the spec's minimum

The assignment only requires `run_agent(question) -> str`; a UI is an optional bonus. I built a Streamlit web app on top because:
- It makes the tool-chaining process visible in real time (a live "agent reasoning" panel shows each tool call as it happens), which is otherwise invisible if you only see a final printed string.
- It restructures the interaction as a guided menu (pick "Track my order" → pick a real order from a list → see the answer) rather than a free-text box, so anyone unfamiliar with the project — like an evaluator — immediately understands what it can do, without needing to know order/product ID syntax in advance.

## 7. Known limitations

- `run_agent()` is stateless between calls, matching the assignment's exact function signature — it does not maintain conversation memory, so a follow-up like "yes" to a previous answer is treated as a brand-new, unrelated question. This is a deliberate consequence of building strictly to spec rather than scope creep into a full chatbot.
- The mock data (6 orders, 12 products) is intentionally small — large enough to demonstrate every required behavior (status lookup, chaining, invalid IDs, empty search) without needing a real database.
