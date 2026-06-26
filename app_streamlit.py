"""
app_streamlit.py
-----------------
Web interface for the agentic store assistant (bonus deliverable).

Run with:
    streamlit run app_streamlit.py

Design: a guided decision-tree help center, like Flipkart/Amazon's support
flow -- NOT a free-text box you have to know what to type into.

Flow:
    1. Pick a category (Track order / Cheaper alternative / Browse products / Product info)
    2. Pick the specific item from a real list (an actual order, an actual
       category, an actual product) -- no typing or memorizing IDs needed.
    3. The agent answers (with a live "reasoning" trace showing tool calls).
    4. You're given options to ask another question or go back to the menu.

A free-text box is still offered as a 5th option, for anything outside the
guided flows, since the underlying agent can handle arbitrary questions too.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from dotenv import load_dotenv
load_dotenv()

# Streamlit Cloud (and other Streamlit-hosted deployments) inject secrets
# via st.secrets rather than a .env file. Copy them into os.environ here so
# agent_core.py's provider selection logic works unchanged in both places.
try:
    for key in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        if key in st.secrets and not os.environ.get(key):
            os.environ[key] = st.secrets[key]
except Exception:
    pass  # st.secrets raises if no secrets.toml exists locally -- that's fine

from agent.agent_core import run_agent
from agent import logger as agent_logger
from agent.tools import list_orders, list_categories, list_products


st.set_page_config(page_title="Store Help Center", page_icon="🛍️", layout="centered")

# --------------------------------------------------------------------------
# Styling
# --------------------------------------------------------------------------

st.markdown(
    """
    <style>
        .block-container { padding-top: 2rem; max-width: 780px; }

        .hero {
            background: linear-gradient(135deg, #0F6E56 0%, #085041 100%);
            color: white;
            padding: 1.75rem 2rem;
            border-radius: 14px;
            margin-bottom: 1.25rem;
        }
        .hero h1 { margin: 0; font-size: 1.6rem; }
        .hero p { margin: 0.4rem 0 0 0; opacity: 0.9; font-size: 0.95rem; }

        .brain-badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
        }
        .brain-llm { background: #E1F5EE; color: #085041; }
        .brain-fallback { background: #FAEEDA; color: #633806; }

        .breadcrumb { color: #666; font-size: 0.85rem; margin-bottom: 0.75rem; }

        .answer-box {
            border: 2px solid #0F6E56;
            border-radius: 12px;
            padding: 1.1rem 1.3rem;
            background: #F5FBF9;
            margin: 0.75rem 0;
            font-size: 1.0rem;
        }

        div[data-testid="column"] button { text-align: left; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _active_provider() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return "llm", "Gemini is reasoning over your question"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "llm", "Claude is reasoning over your question"
    return "fallback", "Rule-based fallback (no API key configured)"


def _describe_call(tool_name: str, tool_input: dict, tool_output) -> tuple:
    if tool_name == "get_order":
        oid = tool_input.get("order_id", "?")
        in_progress = f"Looking up order **{oid}**"
        result = "Order found" if tool_output else f"No order found with ID {oid}"
    elif tool_name == "get_product":
        pid = tool_input.get("product_id", "?")
        in_progress = f"Fetching product **{pid}**"
        result = f"Found: {tool_output['name']}" if tool_output else f"No product found with ID {pid}"
    elif tool_name == "search_products":
        q = tool_input.get("query", "")
        in_progress = f"Searching products for \u201c{q}\u201d"
        n = len(tool_output) if tool_output else 0
        result = f"Found {n} matching product(s)" if n else "No matching products found"
    else:
        in_progress = f"Calling {tool_name}"
        result = "Done"
    return in_progress, result


def _run_with_trace(question: str, status_box):
    calls = []
    original_log = agent_logger.log_tool_call

    def spy(tool_name, tool_input, tool_output):
        in_progress, result = _describe_call(tool_name, tool_input, tool_output)
        status_box.write(f"🔎 {in_progress}")
        status_box.write(f"&nbsp;&nbsp;&nbsp;↳ {result}")
        calls.append({"tool": tool_name, "input": tool_input, "output": tool_output})
        return original_log(tool_name, tool_input, tool_output)

    agent_logger.log_tool_call = spy
    try:
        answer = run_agent(question)
    finally:
        agent_logger.log_tool_call = original_log

    return answer, calls


# --------------------------------------------------------------------------
# Flow definitions: category -> how to list choices -> how to build the
# question once a specific choice is picked.
# --------------------------------------------------------------------------

FLOWS = {
    "track": {
        "menu_label": "📦 Track my order",
        "prompt": "Which order would you like to check?",
        "build_question": lambda value: f"Where is order {value}?",
    },
    "cheaper": {
        "menu_label": "💸 Find a cheaper alternative",
        "prompt": "Which order would you like a cheaper alternative for?",
        "build_question": lambda value: f"Is there a cheaper alternative to what I ordered in {value}?",
    },
    "browse": {
        "menu_label": "🔍 Browse products by category",
        "prompt": "Which category interests you?",
        "build_question": lambda value: f"Do you have any {value}?",
    },
    "product": {
        "menu_label": "ℹ️ Get product details",
        "prompt": "Which product would you like details on?",
        "build_question": lambda value: f"Tell me about {value}",
    },
    "free": {
        "menu_label": "💬 Ask something else",
        "prompt": None,
        "build_question": None,
    },
}


def _choices_for(flow_key: str):
    """Returns a list of (button_label, value_to_use_in_question) for a flow."""
    if flow_key in ("track", "cheaper"):
        return [
            (f"{o['order_id']} \u2014 {o['items'][0]['name']} ({o['status'].replace('_', ' ')})", o["order_id"])
            for o in list_orders()
        ]
    if flow_key == "browse":
        return [(c.title(), c) for c in list_categories()]
    if flow_key == "product":
        return [(f"{p['name']} ({p['product_id']})", p["product_id"]) for p in list_products()]
    return []


def _go(stage, **kwargs):
    st.session_state["stage"] = stage
    for k, v in kwargs.items():
        st.session_state[k] = v


def _reset_to_menu():
    _go("menu")


# --------------------------------------------------------------------------
# Session state defaults
# --------------------------------------------------------------------------

if "stage" not in st.session_state:
    st.session_state["stage"] = "menu"   # menu -> select -> result
if "flow" not in st.session_state:
    st.session_state["flow"] = None
if "answer_data" not in st.session_state:
    st.session_state["answer_data"] = None

# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------

st.markdown(
    """
    <div class="hero">
        <h1>🛍️ Store Help Center</h1>
        <p>Pick what you need below -- our agent will look it up for you.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

mode, mode_text = _active_provider()
badge_class = "brain-llm" if mode == "llm" else "brain-fallback"
st.markdown(f'<span class="brain-badge {badge_class}">{mode_text}</span>', unsafe_allow_html=True)
st.write("")

stage = st.session_state["stage"]
flow_key = st.session_state["flow"]

# --------------------------------------------------------------------------
# STAGE 1: Main menu
# --------------------------------------------------------------------------

if stage == "menu":
    st.subheader("What do you need help with?")
    for key, flow in FLOWS.items():
        if st.button(flow["menu_label"], use_container_width=True, key=f"menu_{key}"):
            if key == "free":
                _go("free_input", flow=key)
            else:
                _go("select", flow=key)
            st.rerun()

# --------------------------------------------------------------------------
# STAGE 2a: Free-text question
# --------------------------------------------------------------------------

elif stage == "free_input":
    st.markdown('<div class="breadcrumb">Help Center › Ask something else</div>', unsafe_allow_html=True)
    st.subheader("What would you like to ask?")
    text = st.text_input("Your question", placeholder="e.g. What's the status of ORD-1003?", label_visibility="collapsed")
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Ask", use_container_width=True, type="primary"):
            if text.strip():
                _go("result", flow="free", pending_question=text.strip())
                st.rerun()
            else:
                st.warning("Type a question first.")
    with c2:
        if st.button("⬅ Back to menu", use_container_width=True):
            _reset_to_menu()
            st.rerun()

# --------------------------------------------------------------------------
# STAGE 2b: Pick a specific item (order / category / product) for a flow
# --------------------------------------------------------------------------

elif stage == "select":
    flow = FLOWS[flow_key]
    st.markdown(f'<div class="breadcrumb">Help Center › {flow["menu_label"]}</div>', unsafe_allow_html=True)
    st.subheader(flow["prompt"])

    choices = _choices_for(flow_key)
    for label, value in choices:
        if st.button(label, use_container_width=True, key=f"choice_{flow_key}_{value}"):
            question = flow["build_question"](value)
            _go("result", flow=flow_key, pending_question=question)
            st.rerun()

    st.write("")
    if st.button("⬅ Back to menu", use_container_width=True):
        _reset_to_menu()
        st.rerun()

# --------------------------------------------------------------------------
# STAGE 3: Run the agent and show the result
# --------------------------------------------------------------------------

elif stage == "result":
    flow = FLOWS[flow_key]
    breadcrumb_label = flow["menu_label"]
    st.markdown(f'<div class="breadcrumb">Help Center › {breadcrumb_label} › Result</div>', unsafe_allow_html=True)

    question = st.session_state.get("pending_question")

    if st.session_state["answer_data"] is None or st.session_state["answer_data"].get("question") != question:
        st.markdown(f"**You asked:** {question}")
        with st.status("Agent is reasoning...", expanded=True) as status_box:
            answer, calls = _run_with_trace(question, status_box)
            status_box.update(label="Reasoning complete", state="complete")
        st.session_state["answer_data"] = {"question": question, "answer": answer, "calls": calls}
    else:
        st.markdown(f"**You asked:** {question}")

    data = st.session_state["answer_data"]
    st.markdown(f'<div class="answer-box">{data["answer"]}</div>', unsafe_allow_html=True)

    if data["calls"]:
        with st.expander(f"🧠 Agent reasoning ({len(data['calls'])} tool call(s))"):
            for c in data["calls"]:
                in_progress, result = _describe_call(c["tool"], c["input"], c["output"])
                st.markdown(f"**{in_progress}** \u2014 {result}")

    st.write("")
    st.markdown("**What would you like to do next?**")
    c1, c2 = st.columns([1, 1])
    with c1:
        if flow_key != "free" and st.button("🔁 Ask about another item", use_container_width=True):
            _go("select", flow=flow_key, answer_data=None)
            st.rerun()
    with c2:
        if st.button("⬅ Back to main menu", use_container_width=True):
            st.session_state["answer_data"] = None
            _reset_to_menu()
            st.rerun()
