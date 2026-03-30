"""
agents/agent2_table.py
───────────────────────
Agent 2 — Table Specialist

Only called when Agent 1's confidence is below HIGH_CONFIDENCE threshold.
Receives the top 3 matching snippets (tiny prompt) instead of full page text.
Understands both horizontal and vertical table reading.
Uses few-shot prompting with one example.
"""

from utils.display import agent_header, step_output

FEW_SHOT_EXAMPLE = """
EXAMPLE — how to read a table both horizontally and vertically:

Table snippet:
  Leverage Ratio Grid | LIBOR Loans | Leverage Ratio ≥ 3.00x | value: 2.25%
  Leverage Ratio Grid | LIBOR Loans | Leverage Ratio < 3.00x ≥ 2.00x | value: 2.00%
  Leverage Ratio Grid | ABR Loans   | Leverage Ratio ≥ 3.00x | value: 1.25%

Key: "LIBOR Loan Rate - Leverage Ratio ≥ 3.00x"
Description: "The applicable margin for LIBOR loans when Leverage Ratio ≥ 3.00x"

Reading horizontally: find row=LIBOR Loans, then column=≥ 3.00x → 2.25%
Reading vertically:   find column=≥ 3.00x, then row=LIBOR Loans → 2.25%
Both give the same answer: 2.25%

Correct output:
{
  "value": "2.25%",
  "row_label": "LIBOR Loans",
  "column_label": "Leverage Ratio ≥ 3.00x",
  "table_title": "Leverage Ratio Grid",
  "confidence": "high",
  "reasoning": "Row LIBOR Loans × column ≥ 3.00x = 2.25%"
}
"""


def _build_prompt(key_name: str, key_description: str,
                  top_snippets: list[dict]) -> str:
    snippet_block = "\n".join(
        f"  [{i+1}] score={s['score']:.3f}  {s['snippet']}"
        for i, s in enumerate(top_snippets)
    )

    # Build special disambiguation notes based on key type
    extra_instructions = ""
    kn_lower = key_name.lower()

    if "bank authorized representative" in kn_lower or (
        "bank" in kn_lower and "representative" in kn_lower
    ):
        extra_instructions += (
            "\nCRITICAL — PARTY DISAMBIGUATION:\n"
            "  This key is about the BANK's authorized representative (the lending institution).\n"
            "  The document has TWO signatory sections: one for the Borrower and one for the Bank.\n"
            "  You MUST return the name/title from the BANK's signature block ONLY.\n"
            "  Do NOT return the Borrower's (government minister's) name or title.\n"
            "  The Bank's representative is typically a Country Director, Regional VP, or similar Bank officer.\n"
        )
    elif "borrower authorized representative" in kn_lower or (
        "borrower" in kn_lower and "representative" in kn_lower
    ):
        extra_instructions += (
            "\nCRITICAL — PARTY DISAMBIGUATION:\n"
            "  This key is about the BORROWER's authorized representative (the government side).\n"
            "  You MUST return the name/title from the BORROWER's signature block ONLY.\n"
            "  Do NOT return the Bank officer's name or title.\n"
            "  The Borrower's representative is typically a government minister or official.\n"
        )

    if "currency" in kn_lower and "loan" in kn_lower:
        extra_instructions += (
            "\nCRITICAL — CURRENCY EXTRACTION:\n"
            "  Extract the ISO 4217 currency code of the LOAN PRINCIPAL AMOUNT.\n"
            "  Look for the currency that appears directly before the loan amount figure (e.g., 'EUR 386,200,000').\n"
            "  Do NOT extract interest rate benchmark currencies (LIBOR, SOFR, etc.).\n"
            "  Return only the 3-letter currency code (e.g., EUR, USD, XOF).\n"
        )

    return f"""{FEW_SHOT_EXAMPLE}
─────────────────────────────────────────────────
NOW extract for this real key:

TOP MATCHING SNIPPETS (from embedding search):
{snippet_block}

KEY NAME       : "{key_name}"
KEY DESCRIPTION: "{key_description}"
{extra_instructions}
Instructions:
1. Snippets can be in TWO formats:
   a) TABLE format: "TableTitle | RowOrCol | ColOrRow | value: X"
      → Read horizontally AND vertically to find the correct cell.
   b) PLAIN TEXT format: a raw paragraph from the document
      → Read the text directly and extract the value that answers the key.
2. For table snippets: pick the row × column that matches the key.
3. For plain text snippets: extract the exact value mentioned for the key.
4. Pick the snippet with the highest score if multiple match.
5. If no snippet contains the answer, return null for value.
6. NEVER return a date as the value for a non-date key (Borrower, Lender, etc.).

Return ONLY JSON, no explanation:
{{
  "value": "<extracted value or null>",
  "row_label": "<row header or page reference>",
  "column_label": "<column header or field name>",
  "table_title": "<table name or 'Plain text'>",
  "confidence": "high/medium/low",
  "reasoning": "<one sentence max>"
}}"""


def run(key_name: str, key_description: str,
        top_cells: list[dict], client, timer=None) -> dict:
    """
    Args:
        key_name:        the key to extract
        key_description: business rule description
        top_cells:       top 3-5 snippets from embedding search
        client:          LLMClient instance

    Returns:
        {value, row_label, column_label, table_title, confidence, reasoning}
    """
    agent_header("Agent 2 — Table Specialist (LLM)", key_name)

    if not top_cells:
        step_output("Status:", "No candidates from embedding — returning null")
        return {"value": None, "row_label": None, "column_label": None,
                "table_title": None, "confidence": "low", "reasoning": "No candidates"}

    # Only send top 3 snippets — keeps prompt tiny
    prompt = _build_prompt(key_name, key_description, top_cells[:3])
    step_output("Prompt size:", f"{len(prompt)} chars (vs ~24,000 chars before)")

    result = client.chat_json(prompt, max_tokens=512)

    if not isinstance(result, dict):
        result = {"value": None, "row_label": None, "column_label": None,
                  "table_title": None, "confidence": "low",
                  "reasoning": "LLM returned invalid JSON"}

    step_output("Extracted:", f"value={result.get('value')!r}  "
                f"row={result.get('row_label')!r}  "
                f"col={result.get('column_label')!r}")
    step_output("Reasoning:", result.get("reasoning", ""))

    return result
