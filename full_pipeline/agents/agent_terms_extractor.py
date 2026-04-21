"""
agents/agent_terms_extractor.py
──────────────────────────────────
Terms Agent — sub-agent under Doc-Type Sub-Agent

Called when the key demands rule/term extraction from prose paragraphs
(not from a table). Handles:
  - Obligation clauses ("The Borrower shall...")
  - Fixed terms ("The Commitment Period shall be...")
  - Conditions and carve-outs
  - Cross-references between clauses

Uses doc-type specific prompt context loaded from prompts/ directory.
Uses llama-3.3-70b-versatile (Groq) or qwen2.5:7b (Ollama).
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_doc_type_terms(doc_type: str) -> str:
    """Load doc-type-specific terms prompt context."""
    terms_file = _PROMPTS_DIR / f"{doc_type}_terms.txt"
    if terms_file.exists():
        return terms_file.read_text(encoding="utf-8")
    # Generic fallback
    return (
        "You are a financial document analyst extracting specific field values "
        "from legal agreements and financial documents."
    )


TERMS_PROMPT = """
{doc_type_context}

══════════════════════════════════════════════════════════
TASK: Extract the value for the specified field from the document text below.
══════════════════════════════════════════════════════════

KEY NAME       : "{key_name}"
KEY DESCRIPTION: "{key_desc}"

DOCUMENT TEXT (relevant pages):
{page_text}

EXTRACTION INSTRUCTIONS:
1. Search for the value associated with "{key_name}" — also check synonyms and
   related phrasings. Examples of synonyms to check:
   - "Program Reporting Period" → "Program Report", "reporting frequency",
     "calendar semester", "forty-five days", "45 days"
   - "Loan Currency" → "expressed in", "EUR", "USD", currency code in headers
   - "Agreement Date" → "dated as of", "effective date", "signing date"
2. The value may appear as:
   a) A direct statement: "The [Key] is X" or "The [Key] shall be X"
   b) A definition: "[Key] means X"
   c) A numeric figure in a clause: "not to exceed X", "greater than X"
   d) A party name, date, or reference code embedded in a sentence
3. Extract EXACTLY what the document states — do NOT paraphrase or calculate.
4. If you find multiple occurrences, prefer the one in the most relevant clause.
5. Note the page number where the value was found.
6. If the key refers to a condition or obligation: extract the full condition, not just the number.
7. If NOT found: set value to null. Do NOT invent or guess.

Return ONLY JSON, no explanation:
{{
  "value": "<exact extracted value, or null if not found>",
  "value_raw": "<verbatim sentence from document containing the value>",
  "page": <page number or null>,
  "found_in": "paragraph/clause/definition/not_found",
  "confidence": "high/medium/low",
  "reasoning": "<one sentence: how and where you found the value>"
}}"""


def _needs_terms_extraction(key_desc: str) -> bool:
    """
    Determine if this key needs the Terms Agent (paragraph-based extraction)
    vs a simple lookup. Returns True if the description suggests obligations,
    conditions, or complex terms.
    """
    if not key_desc:
        return False
    lower = key_desc.lower()
    term_indicators = [
        "shall", "must", "obligation", "covenant", "condition",
        "requirement", "clause", "agreement", "provision",
        "permitted", "restricted", "prohibited", "allowed",
        "period", "term", "duration", "trigger", "threshold",
    ]
    return any(ind in lower for ind in term_indicators)


def run(key_name: str, key_desc: str,
        page_text: str,
        client,
        doc_type: str = "loan") -> dict:
    """
    Extract terms/obligations from prose paragraphs.

    Args:
        key_name  : field name to extract
        key_desc  : field description
        page_text : concatenated text of relevant pages (paragraph content)
        client    : LLMClient (agent_terms)
        doc_type  : "loan", "isda", "invoice", "compliance_report"

    Returns:
        {value, value_raw, page, found_in, confidence, reasoning}
    """
    print(f"  [Terms] Extracting '{key_name}' from {len(page_text)} chars of paragraph text")

    if not page_text.strip():
        return {
            "value": None, "value_raw": None, "page": None,
            "found_in": "not_found", "confidence": "low",
            "reasoning": "No paragraph text provided",
        }

    doc_type_context = _load_doc_type_terms(doc_type)

    prompt = TERMS_PROMPT.format(
        doc_type_context = doc_type_context,
        key_name         = key_name,
        key_desc         = key_desc or "(no description provided)",
        page_text        = page_text[:5000],
    )

    try:
        result = client.chat_json(prompt, max_tokens=512)
    except Exception as e:
        print(f"  [Terms] LLM error: {e}")
        return {
            "value": None, "value_raw": None, "page": None,
            "found_in": "not_found", "confidence": "low",
            "reasoning": f"LLM error: {str(e)[:60]}",
        }

    if not isinstance(result, dict):
        return {
            "value": None, "value_raw": None, "page": None,
            "found_in": "not_found", "confidence": "low",
            "reasoning": "LLM returned non-dict response",
        }

    print(f"  [Terms] value={result.get('value')!r}  "
          f"found_in={result.get('found_in')}  "
          f"conf={result.get('confidence')}")
    return result
