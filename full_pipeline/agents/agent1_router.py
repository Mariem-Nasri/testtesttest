"""
agents/agent1_router.py
───────────────────────
Agent 1 — Embedding Router

PRIMARY:  cosine similarity search (no LLM, ~2ms)
FALLBACK: llama-4-scout LLM call when embedding confidence < 0.45

The LLM fallback handles keys whose descriptions don't match
any indexed snippet well — typically very abstract keys or
keys for content not yet in the index (new document sections).
"""

import re
from utils.display import (agent_header, search_result, step_output,
                            confidence_badge, needs_llm_badge)


ROUTER_FALLBACK_PROMPT = """You are a financial document routing assistant.

DOCUMENT PAGE SUMMARIES:
{page_summaries}

KEY TO LOCATE:
  Name       : "{key_name}"
  Description: "{key_desc}"

Identify where in the document this key's value is most likely found.
Return ONLY JSON, no explanation:
{{
  "page": <integer page number or null>,
  "section": "<table or section title>",
  "alias": "<term the document uses for this concept>",
  "reasoning": "<one sentence>"
}}"""


# ── Format inference from key name (shared with agent4) ──────────────────────
_FORMAT_PATTERNS = [
    (re.compile(r'\bratio\b|\bleverage\b|\bcoverage\b', re.I),           "ratio"),
    (re.compile(r'\brate\b|\bfee\b|\bmargin\b|\bspread\b|\byield\b|'
                r'\bpercentage\b|\bpercent\b|\b%\b', re.I),              "percentage"),
    (re.compile(r'\bdate\b|\bdeadline\b|\bclosing\b|\bmaturity\b|'
                r'\bexpir\b|\beffective\b', re.I),                       "date"),
    (re.compile(r'\bamount\b|\bprincipal\b|\bcurrency\b|\beur\b|'
                r'\busd\b|\bloan\b|\bfee amount\b|\bthreshold\b', re.I), "currency"),
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


def _get_page_summaries(ocr_text: str, max_chars_per_page: int = 300) -> str:
    """Build a short summary of each page for the LLM fallback."""
    pattern = re.compile(r'={20,}\s*\nPAGE\s+(\d+)\s*\n={20,}', re.IGNORECASE)
    splits  = list(pattern.finditer(ocr_text))
    if not splits:
        return ocr_text[:500]

    lines = []
    for i, match in enumerate(splits[:15]):   # max 15 pages to keep prompt small
        page_num = match.group(1)
        start    = match.start()
        end      = splits[i+1].start() if i+1 < len(splits) else len(ocr_text)
        preview  = ocr_text[start:end].strip()[:max_chars_per_page].replace("\n", " ")
        lines.append(f"[Page {page_num}] {preview}")
    return "\n".join(lines)


def run(key_name: str, key_description: str,
        index, client=None, ocr_text: str = "", thresholds: dict = None) -> dict:
    """
    Args:
        key_name:        e.g. "LIBOR Loan Rate - Leverage Ratio >= 3.00x"
        key_description: e.g. "The applicable margin for LIBOR loans when..."
        index:           DocumentIndex object
        client:          LLMClient for agent1 (used only as fallback)
        ocr_text:        full OCR text (used only for LLM fallback)
        thresholds:      dict of confidence thresholds

    Returns:
        {
            top_cells, top_definitions, best_value,
            expected_format, definition_text, value_hint,
            confidence, needs_llm, page_hint,
            router_used_llm: bool
        }
    """
    agent_header("Agent 1 — Embedding Router", key_name)

    # Use default thresholds if none are provided
    if thresholds is None:
        thresholds = {
            "HIGH_CONFIDENCE": 0.82,
            "VERY_LOW_CONF":   0.35,
        }

    query = f"{key_name}. {key_description}"

    # ── Search table cells ────────────────────────────────────────────────────
    top_cells = index.search_tables(query, top_k=5)
    print(f"    Table cell matches:")
    for i, cell in enumerate(top_cells[:3]):
        search_result(i+1, cell["snippet"], cell["score"])

    # ── Search definitions ────────────────────────────────────────────────────
    top_defs = index.search_definitions(query, top_k=2)
    print(f"    Definition matches:")
    for i, d in enumerate(top_defs[:2]):
        search_result(i+1, d["snippet"], d["score"])

    # ── Determine expected format ─────────────────────────────────────────────
    # Priority 1: infer from key name (fast, deterministic, no LLM)
    # Priority 2: override with definition index only if score is strong
    #             AND the definition provides a non-text format
    expected_format = _infer_format_from_key_name(key_name)

    value_hint      = None
    definition_text = None

    if top_defs and top_defs[0]["score"] > 0.40:
        best_def    = top_defs[0]
        def_format  = best_def.get("expected_format") or "text"
        # Only override key-name inference if definition gives a richer signal
        if def_format != "text" and expected_format == "text":
            expected_format = def_format
        value_hint      = best_def.get("value_hint")
        definition_text = best_def.get("definition")

    confidence      = top_cells[0]["score"] if top_cells else 0.0
    needs_llm       = confidence < thresholds["HIGH_CONFIDENCE"]
    best_value      = top_cells[0]["value"] if (top_cells and not needs_llm) else None
    page_hint       = top_cells[0].get("page") if top_cells else None
    router_used_llm = False

    # ── LLM fallback for very low confidence ─────────────────────────────────
    if confidence < thresholds["VERY_LOW_CONF"] and client is not None and ocr_text:
        print(f"    ⚠  Confidence {confidence:.3f} very low — calling LLM router fallback")
        router_used_llm = True

        summaries  = _get_page_summaries(ocr_text)
        prompt     = ROUTER_FALLBACK_PROMPT.format(
            page_summaries = summaries,
            key_name       = key_name,
            key_desc       = key_description,
        )
        llm_result = client.chat_json(prompt, max_tokens=256)

        if isinstance(llm_result, dict):
            page_hint = llm_result.get("page") or page_hint
            alias     = llm_result.get("alias", "") or ""
            reasoning = llm_result.get("reasoning", "") or ""
            step_output("LLM router:",  f"page={page_hint}  alias={alias!r}")
            step_output("Reasoning:",   reasoning[:80])

            # Re-search with alias if provided
            if alias:
                alias_query = f"{alias}. {key_description}"
                alias_cells = index.search_tables(alias_query, top_k=3)
                if alias_cells and alias_cells[0]["score"] > confidence:
                    top_cells   = alias_cells
                    confidence  = alias_cells[0]["score"]
                    needs_llm   = confidence < thresholds["HIGH_CONFIDENCE"]
                    best_value  = (alias_cells[0]["value"]
                                   if not needs_llm else None)
                    print(f"    Re-search with alias improved confidence: {confidence:.3f}")

    step_output("Expected format:", expected_format)
    step_output("Confidence:",      f"{confidence:.3f} → {confidence_badge(confidence)}")
    step_output("Decision:",        needs_llm_badge(needs_llm))
    if best_value:
        step_output("Direct value:", f"{best_value} (skipping Agent 2)")
    if router_used_llm:
        step_output("LLM used:",    "yes (very low embedding confidence)")

    return {
        "top_cells":        top_cells,
        "top_definitions":  top_defs,
        "best_value":       best_value,
        "expected_format":  expected_format,
        "definition_text":  definition_text,
        "value_hint":       value_hint,
        "confidence":       confidence,
        "needs_llm":        needs_llm,
        "page_hint":        page_hint,
        "router_used_llm":  router_used_llm,
    }