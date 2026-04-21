"""
agents/agent_tables.py
───────────────────────
Tables Agent — Raw ASCII table extraction

Reads ASCII tables from OCR text with FULL support for:
  • Horizontal reading (row × column intersection)
  • Vertical reading (column × row intersection)
  • Merged cells (spanning multiple rows or columns)
  • Multi-row headers
  • Cross-page tables (table split across two pages)
  • │ pipe character tables (produced by TATR)
  • +---------+ style tables (produced by some OCR engines)

Uses llama-3.3-70b-versatile (Groq) or qwen2.5:7b (Ollama).
Called when Document Map routes a key to a "table" type section.
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# ── Few-shot example ──────────────────────────────────────────────────────────

FEW_SHOT = """
══════════════════════════════════════════════════════════
EXAMPLE — how to read ASCII tables both ways:
══════════════════════════════════════════════════════════

INPUT TABLE (from OCR):
  ┌────────────────────────────┬───────────┬───────────┐
  │ Leverage Ratio Grid        │ LIBOR     │ ABR       │
  │                            │ Loans     │ Loans     │
  ├────────────────────────────┼───────────┼───────────┤
  │ Leverage Ratio ≥ 3.00x     │   2.25%   │   1.25%   │
  │ Leverage Ratio < 3.00x     │   2.00%   │   1.00%   │
  │  and ≥ 2.00x               │           │           │
  │ Leverage Ratio < 2.00x     │   1.75%   │   0.75%   │
  └────────────────────────────┴───────────┴───────────┘

KEY: "LIBOR Loan Rate when Leverage Ratio ≥ 3.00x"
DESCRIPTION: "Applicable margin for LIBOR loans when leverage ratio ≥ 3.00x"

HORIZONTAL READ: Find row "Leverage Ratio ≥ 3.00x" → column "LIBOR Loans" → 2.25%
VERTICAL READ:   Find column "LIBOR Loans" → row "≥ 3.00x" → 2.25%
Both confirm: 2.25%

OUTPUT:
{
  "value": "2.25%",
  "row_label": "Leverage Ratio ≥ 3.00x",
  "column_label": "LIBOR Loans",
  "table_title": "Leverage Ratio Grid",
  "page": 5,
  "confidence": "high",
  "reasoning": "Row '≥ 3.00x' × column 'LIBOR Loans' = 2.25% confirmed by both H and V reads"
}

══════════════════════════════════════════════════════════
EXAMPLE — merged cells:
══════════════════════════════════════════════════════════

INPUT TABLE:
  │ Commitment Fee            │          0.375%           │
  │ (all tranches)            │ per annum, payable quarterly │

KEY: "Commitment Fee"
READING: Merged row label "Commitment Fee" maps to value "0.375% per annum, payable quarterly"

OUTPUT:
{
  "value": "0.375%",
  "row_label": "Commitment Fee",
  "column_label": "Rate",
  "table_title": "Fee Schedule",
  "page": 12,
  "confidence": "high",
  "reasoning": "Merged cell: commitment fee = 0.375% per annum"
}
══════════════════════════════════════════════════════════
"""


def _build_prompt(key_name: str, key_desc: str, page_texts: str) -> str:
    return f"""{FEW_SHOT}
══════════════════════════════════════════════════════════
NOW extract for this real key:
══════════════════════════════════════════════════════════

DOCUMENT PAGES (OCR output with ASCII tables):
{page_texts[:6000]}

KEY NAME       : "{key_name}"
KEY DESCRIPTION: "{key_desc}"

EXTRACTION INSTRUCTIONS:
1. Locate the table(s) on these pages.
2. Read headers: they may be multi-row (combine them for full meaning).
3. Try HORIZONTAL read first: scan the row that matches the key → find the column.
4. Then try VERTICAL read: scan the column that matches the key → find the row.
5. For merged cells: the value applies to ALL rows in the merged span.
6. For cross-page tables: the header on page N applies to data on page N+1.
7. Report the EXACT cell value as it appears — do NOT calculate or infer.
8. If the table uses │ characters: columns are delimited by │.
9. SPECIAL CASE — metadata keys (Currency, Unit, Scale):
   These are often embedded INSIDE column/row headers, not in data cells.
   Example: column header "Amount of the Loan Allocated (expressed in EUR)"
   → Currency = "EUR" (extracted from the header itself, no matching row needed).
10. If nothing matches: set value to null and explain in reasoning.
11. Include the page number where you found the value.

Return ONLY JSON, no explanation:
{{
  "value": "<extracted value or null>",
  "row_label": "<row header that matched>",
  "column_label": "<column header that matched>",
  "table_title": "<name of the table if visible, else 'Unknown Table'>",
  "page": <page number or null>,
  "confidence": "high/medium/low",
  "reasoning": "<one sentence: how you identified row × column>"
}}"""


def run(key_name: str, key_desc: str, page_texts: str, client) -> dict:
    """
    Extract value from ASCII table on given pages.

    Args:
        key_name   : field to extract (e.g. "LIBOR Rate – Leverage ≥ 3.00x")
        key_desc   : description (e.g. "Applicable margin when leverage ratio ...")
        page_texts : concatenated OCR text of relevant pages
        client     : LLMClient (agent_tables)

    Returns:
        {value, row_label, column_label, table_title, page, confidence, reasoning}
    """
    print(f"  [Tables] Extracting '{key_name}' from {len(page_texts)} chars of table text")

    if not page_texts.strip():
        return {
            "value": None, "row_label": None, "column_label": None,
            "table_title": None, "page": None,
            "confidence": "low", "reasoning": "No table text provided",
        }

    prompt = _build_prompt(key_name, key_desc, page_texts)

    try:
        result = client.chat_json(prompt, max_tokens=512)
    except Exception as e:
        print(f"  [Tables] LLM error: {e}")
        return {
            "value": None, "row_label": None, "column_label": None,
            "table_title": None, "page": None,
            "confidence": "low", "reasoning": f"LLM error: {str(e)[:60]}",
        }

    if not isinstance(result, dict):
        return {
            "value": None, "row_label": None, "column_label": None,
            "table_title": None, "page": None,
            "confidence": "low", "reasoning": "LLM returned non-dict",
        }

    v = result.get("value")
    print(f"  [Tables] value={v!r}  row={result.get('row_label')!r}  "
          f"col={result.get('column_label')!r}  conf={result.get('confidence')}")
    return result
