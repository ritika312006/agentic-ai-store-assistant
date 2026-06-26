"""
agent_core.py
-------------
The "real" agent: uses an LLM with native tool-use/function-calling to
decide which tool(s) to call, chain them as needed, and produce a
customer-friendly final answer.

Entry point required by the assignment spec:

    run_agent(question: str) -> str

Supported providers (configurable, free option included):
- Google Gemini  (FREE tier, no credit card required) -- default/primary.
  Get a key at https://aistudio.google.com/apikey and set GEMINI_API_KEY.
- Anthropic Claude (paid) -- optional alternative, set ANTHROPIC_API_KEY.

Provider selection logic (see DESIGN_DOC.md for full rationale):
- If GEMINI_API_KEY is set -> use Gemini.
- Else if ANTHROPIC_API_KEY is set -> use Claude.
- Else -> deterministic rule-based router (always free, always works).
- Any runtime error from the LLM provider (network, auth, rate limit)
  transparently falls back to the rule-based router rather than crashing.

Design notes:
- The system prompt explicitly forbids fabrication and instructs the model
  to rely only on tool outputs, and to ask a clarifying question if the
  request is genuinely ambiguous (e.g., no order/product reference at all).
- Both providers share the same TOOL_SCHEMAS / TOOL_FUNCTIONS defined in
  tools.py, converted to each provider's native format here, so the tool
  *behavior* is guaranteed identical regardless of which LLM is reasoning.
"""

import os
import json

from dotenv import load_dotenv
load_dotenv()  # loads variables from a local .env file, if present

from agent.tools import TOOL_SCHEMAS, TOOL_FUNCTIONS
from agent.logger import log_tool_call
from agent.rule_based_router import run_agent_rule_based

SYSTEM_PROMPT = """You are a customer support agent for an online store.

You have access to tools that fetch REAL data: get_order, search_products, get_product.

Rules you must always follow:
1. Only use information returned by tool calls. NEVER invent or guess order
   details, product details, prices, stock status, or search results.
2. If a tool returns null/empty for something the customer asked about,
   tell them honestly that it wasn't found -- do not make up a plausible-sounding
   answer.
3. Chain multiple tool calls when needed. For example, if a customer asks for
   a cheaper alternative to something in an order, first call get_order to find
   out what they bought, then call get_product or search_products to find
   alternatives, and only then compare prices.
4. If the question is too vague to know which order or product is being asked
   about (e.g. no order ID, no product name/category, no useful keywords),
   ask a short clarifying question instead of guessing.
5. Always write your final answer in a friendly, concise, customer-facing tone.
   Never dump raw JSON or internal tool output at the customer.
"""

_GEMINI_MODEL = "gemini-2.5-flash"
_ANTHROPIC_MODEL = "claude-sonnet-4-6"
_MAX_TOOL_ITERATIONS = 5


def _execute_tool(name: str, tool_input: dict):
    """Executes a single tool call by name and logs it."""
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        result = {"error": f"Unknown tool '{name}'"}
    else:
        result = func(**tool_input)
    return log_tool_call(name, tool_input, result)


# --------------------------------------------------------------------------
# Gemini provider (free tier)
# --------------------------------------------------------------------------

def _run_gemini(question: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    function_declarations = [
        types.FunctionDeclaration(
            name=schema["name"],
            description=schema["description"],
            parameters=schema["input_schema"],
        )
        for schema in TOOL_SCHEMAS
    ]
    tools = types.Tool(function_declarations=function_declarations)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[tools],
    )

    contents = [types.Content(role="user", parts=[types.Part.from_text(text=question)])]

    for _ in range(_MAX_TOOL_ITERATIONS):
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=contents,
            config=config,
        )

        candidate = response.candidates[0]
        parts = candidate.content.parts or []
        function_calls = [p.function_call for p in parts if getattr(p, "function_call", None)]

        if not function_calls:
            text = "".join(p.text for p in parts if getattr(p, "text", None))
            return text.strip() or "Sorry, I wasn't able to come up with an answer for that."

        # Echo the model's turn (including its function call requests) back
        # into the conversation, then append our function results.
        contents.append(candidate.content)

        response_parts = []
        for fc in function_calls:
            output = _execute_tool(fc.name, dict(fc.args))
            response_parts.append(
                types.Part.from_function_response(name=fc.name, response={"result": output})
            )
        contents.append(types.Content(role="user", parts=response_parts))

    return "Sorry, I had trouble working through this request. Could you rephrase it or provide an order/product ID?"


# --------------------------------------------------------------------------
# Anthropic provider (optional, paid)
# --------------------------------------------------------------------------

def _run_anthropic(question: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    messages = [{"role": "user", "content": question}]

    for _ in range(_MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=_ANTHROPIC_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks:
            text_parts = [b.text for b in response.content if b.type == "text"]
            final_answer = "\n".join(text_parts).strip()
            return final_answer or "Sorry, I wasn't able to come up with an answer for that."

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in tool_use_blocks:
            output = _execute_tool(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(output, ensure_ascii=False),
            })
        messages.append({"role": "user", "content": tool_results})

    return "Sorry, I had trouble working through this request. Could you rephrase it or provide an order/product ID?"


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def run_agent(question: str) -> str:
    """
    Main entry point required by the assignment.

    Args:
        question: raw customer question, e.g. "Where is order ORD-1002?"

    Returns:
        A customer-friendly final answer string.
    """
    if not question or not question.strip():
        return "Could you tell me what you'd like help with? For example, an order number or a product you're interested in."

    if os.environ.get("GEMINI_API_KEY"):
        try:
            return _run_gemini(question)
        except Exception:
            return run_agent_rule_based(question)

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _run_anthropic(question)
        except Exception:
            return run_agent_rule_based(question)

    # No LLM provider configured -> deterministic fallback, fully functional.
    return run_agent_rule_based(question)
