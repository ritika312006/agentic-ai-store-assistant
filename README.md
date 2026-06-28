🛍️ Agentic AI Store Assistant

An AI agent that answers customer questions for an online store by deciding which tools to use, chaining them when needed, and replying in a clear, customer-friendly way — never fabricating data.

🔗 Live demo: https://agentic-ai-store-assistant-rzsxk9sn8jlixcyevsyvdt.streamlit.app/
📦 Repo: https://github.com/ritika312006/agentic-ai-store-assistant
📢 See: "sample_io.md" for a full set of example questions and the agent's actual responses.
📢 See: "DESIGN_DOC.md" for the full write-up of architecture choices and trade-offs.

What it does

Ask things like:


"Where is order ORD-1002?"
"Is there a cheaper alternative to the shoes I ordered in ORD-1001?"
"Do you have any electronics?"


The agent decides on its own which tool(s) to call, chains multiple tool calls when one question needs several lookups, and turns the raw results into a natural answer — instead of dumping JSON at the customer.

Available tools

ToolPurposeget_order(order_id)Fetch order details (status, items, tracking, delivery date)search_products(query)Keyword search across the product catalogget_product(product_id)Fetch full product details (price, stock, rating)

Architecture

agentic-ai-store/
├── agent/
│   ├── tools.py              # The 3 tools + UI-listing helpers
│   ├── agent_core.py         # run_agent() -- LLM tool-calling loop (Gemini / Claude)
│   ├── rule_based_router.py  # Deterministic fallback (works with zero API key)
│   └── logger.py             # Logs every tool call (name, input, output)
├── data/
│   ├── orders.json           # Mock order data
│   └── products.json         # Mock product catalog
├── tests/
│   └── test_agent.py         # 20 pytest unit tests
├── app_streamlit.py          # Guided help-center web UI (bonus)
├── requirements.txt
├── .env.example               # Template for your API key
└── DESIGN_DOC.md              # Design decisions write-up

How run_agent() works


The question + the 3 tool definitions are sent to an LLM (Gemini by default — free tier).
The LLM decides which tool(s) to call and in what order, and the code executes them against the mock data.
Results are fed back to the LLM, which can call more tools (chaining) or produce a final answer.
If no LLM key is configured, or the LLM call fails for any reason, the app falls back to a deterministic rule-based router automatically — so it never crashes and always answers.
Every tool call is logged (logs/tool_calls.log) with its input and output.


This means tool selection and chaining are genuinely decided by the model at runtime, not hardcoded if/else logic.

Error handling


Invalid order ID / product ID → polite "I couldn't find that" message, never invented data.
Empty search results → honestly says nothing was found.
Ambiguous questions → the agent asks a clarifying question instead of guessing.
LLM/network failure → silently falls back to the rule-based router.


Tech stack


Python 3.13
Google Gemini (google-genai) — free tier, primary reasoning engine
Anthropic Claude — optional alternative provider, same code path
Streamlit — web UI (bonus)
pytest — 20 unit tests (bonus)


Running it locally

bashpip install -r requirements.txt
cp .env.example .env          # then add your free Gemini key (see below)
streamlit run app_streamlit.py

Get a free Gemini key at https://aistudio.google.com/apikey — no credit card required. The app still works with no key at all, using the rule-based fallback.

Running tests

bashpython -m pytest tests/test_agent.py -v

20 tests covering tool correctness, error handling, tool chaining, and fallback behavior.


