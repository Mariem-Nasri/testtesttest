"""
agents/agent4_definition.py
────────────────────────────
Agent 4 — Definition Extractor

Extracts the formal definition of a key term from the document's
definitions section and nearby paragraphs.

Runs in parallel with Agent 1 (both just read the document).
Output feeds into Agent 3 (Validator) to improve score accuracy.
"""

import re
from utils.display import agent_header, step_output

FEW_SHOT_EXAMPLE = """
EXAMPLE:

Definition snippet:
  DEFINITION | Leverage Ratio | ratio of Consolidated Total Debt to
  Consolidated EBITDAX measured quarterly | format: ratio | page: 9

Key: "Leverage Ratio Covenant (Investment Grade Period)"

Output:
{
  "definition_text": "The ratio of Consolidated Total Debt to Consolidated EBITDAX, measured as of the last day of each fiscal quarter",
  "expected_format": "ratio",
  "value_hint": null,
  "related_table": null,
  "source_page": 9
}

EXAMPLE 2:

Covenant snippet:
  COVENANT | Leverage Ratio | The Borrower will not permit the Leverage Ratio
  to be greater than 4.50 to 1.00 | value: 4.50 to 1.00 | format: ratio | page: 15

Key: "Leverage Ratio Covenant (Investment Grade Period)"

Output:
{
  "definition_text": "The Borrower will not permit the Leverage Ratio to be greater than 4.50 to 1.00 during an Investment Grade Period",
  "expected_format": "ratio",
  "value_hint": "4.50 to 1.00",
  "related_table": null,
  "source_page": 15
}
"""


# ── Format inference from key name (no LLM needed) ───────────────────────────
_FORMAT_PATTERNS = [
    # ratio patterns
    (re.compile(r'\bratio\b|\bleverage\b|\bcoverage\b', re.I),           "ratio"),
    # percentage patterns
    (re.compile(r'\brate\b|\bfee\b|\bmargin\b|\bspread\b|\byield\b|'
                r'\bpercentage\b|\bpercent\b|\b%\b', re.I),              "percentage"),
    # date patterns
    (re.compile(r'\bdate\b|\bdeadline\b|\bclosing\b|\bmaturity\b|'
                r'\bexpir\b|\beffective\b', re.I),                       "date"),
    # currency / amount patterns
    (re.compile(r'\bamount\b|\bprincipal\b|\bcurrency\b|\beur\b|'
                r'\busd\b|\bloan\b|\bfee amount\b|\bthreshold\b', re.I), "currency"),
    # number patterns
    (re.compile(r'\bnumber\b|\bcount\b|\bquantity\b|\bdatasets\b|'
                r'\binstallment share\b', re.I),                         "number"),
]

def _infer_format_from_key_name(key_name: str) -> str:
    """
    Infer the expected value format purely from the key name string.
    Returns one of: ratio, percentage, date, currency, number, text.
    Falls back to 'text' if no pattern matches.
    """
    for pattern, fmt in _FORMAT_PATTERNS:
        if pattern.search(key_name):
            return fmt
    return "text"


def _build_prompt(key_name: str, top_def_snippets: list[dict]) -> str:
    snippet_block = "\n".join(
        f"  [{i+1}] score={s['score']:.3f}  {s['snippet']}"
        for i, s in enumerate(top_def_snippets)
    )
    return f"""{FEW_SHOT_EXAMPLE}
─────────────────────────────────────────────────
NOW extract definition for this key:

TOP MATCHING DEFINITION SNIPPETS:
{snippet_block}

KEY NAME: "{key_name}"

Instructions:
1. Find the snippet that best defines or describes this key.
2. Extract the formal definition in plain language (max 2 sentences).
3. Identify the expected value format:
   - "ratio"      → value looks like "4.50 to 1.00"
   - "percentage" → value looks like "2.25%"
   - "date"       → value looks like "2015-11-02"
   - "currency"   → value looks like "EUR 8,582,000"
   - "number"     → value looks like "145"
   - "text"       → free text value
4. If any snippet contains an explicit numeric threshold (e.g. "4.50 to 1.00"),
   include it as value_hint.
5. If the definition mentions a specific table, include it as related_table.

Return ONLY JSON, no explanation:
{{
  "definition_text": "<plain language definition, max 2 sentences>",
  "expected_format": "ratio/percentage/date/currency/number/text",
  "value_hint": "<numeric threshold if found, else null>",
  "related_table": "<table name if mentioned, else null>",
  "source_page": <page number or null>
}}"""


def _build_generation_prompt(key_name: str) -> str:
    return f"""You are an expert document extractor for financial and legal agreements.
Generate a concise plain-language description of the following term in the context of loan agreements and project financing.

TERM: "{key_name}"

Instructions:
1. Write a one-sentence definition in plain language.
2. Keep it general enough to apply across loan and agreement documents.
3. Do not invent numeric values.
4. Return ONLY JSON, no explanation:
{{
  "definition_text": "<plain language definition>",
  "expected_format": "ratio/percentage/date/currency/number/text",
  "value_hint": null,
  "related_table": null,
  "source_page": null
}}"""

def run(key_name: str, top_definitions: list[dict],
        client, timer=None) -> dict:
    """
    Args:
        key_name:         the term to define
        top_definitions:  top matching definition snippets from embedding search
        client:           LLMClient instance

    Returns:
        {definition_text, expected_format, value_hint, related_table, source_page}
    """
    agent_header("Agent 4 — Definition Extractor", key_name)

    # Always infer format from key name as a baseline — no LLM needed
    fmt = _infer_format_from_key_name(key_name)

    # If no definitions found via embedding, return empty string (never generate).
    if not top_definitions or top_definitions[0]["score"] < 0.35:
        step_output("Status:", "No matching definition found in document — returning empty")
        return {
            "definition_text": "",   # empty, not generated
            "expected_format": fmt,
            "value_hint":      None,
            "related_table":   None,
            "source_page":     None,
        }

    # Use LLM only when there are relevant snippets
    prompt = _build_prompt(key_name, top_definitions[:3])
    step_output("Prompt size:", f"{len(prompt)} chars")

    result = client.chat_json(prompt, max_tokens=512)

    if not isinstance(result, dict):
        result = {
            "definition_text": top_definitions[0].get("definition", ""),
            "expected_format": fmt,
            "value_hint":      top_definitions[0].get("value_hint"),
            "related_table":   None,
            "source_page":     top_definitions[0].get("page"),
        }

    # ── FIX: guard against None values returned by LLM for any field ─────────
    # result.get("key", "") only uses "" when the key is ABSENT.
    # If the LLM explicitly sets a key to null, result.get() returns None.
    # We must coerce None → sensible defaults here, not in display.py alone.
    if result.get("expected_format") is None:
        result["expected_format"] = fmt          # use key-name inference
    if result.get("definition_text") is None:
        result["definition_text"] = ""
    if result.get("source_page") is not None:
        result["source_page"] = str(result["source_page"])

    step_output("Definition:",      result.get("definition_text", "")[:80])
    step_output("Expected format:", result.get("expected_format", ""))
    step_output("Value hint:",      str(result.get("value_hint")))
    step_output("Source page:",     str(result.get("source_page")))

    return result