"""
agents/agent_validator.py
──────────────────────────
Phase 3 — Validator (simplified, LLM-only path)

Validates the extracted value using:
  1. Format rule check (instant, no LLM)
     — percentage: must end with %
     — ratio:      must match "X.XX to 1.00"
     — date:       must be YYYY-MM-DD
     — currency:   must have a currency code + number
  2. LLM validation ONLY when:
     — value is null / empty
     — format check fails
     — confidence is low (< 0.6)

No embedding score shortcuts. Every value goes through format check.
Uses llama-3.1-8b-instant (Groq) or qwen2.5:7b (Ollama) — fast model.
"""

import re

# ── ANSI colors ────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"

# ── Format rules ───────────────────────────────────────────────────────────────

FORMAT_RULES = {
    "percentage": {
        "pattern":   re.compile(r'^\d+\.?\d*\s*%$'),
        "example":   "2.25%",
        "normalize": lambda v: (v.strip() + "%") if not v.strip().endswith("%") else v.strip(),
    },
    "ratio": {
        "pattern":   re.compile(r'^\d+\.?\d*\s+to\s+1[.:\d]*', re.IGNORECASE),
        "example":   "4.50 to 1.00",
        "normalize": lambda v: re.sub(r'\s*to\s*1[.:]\s*0*', ' to 1.00', v),
    },
    "date": {
        "pattern":   re.compile(r'^\d{4}-\d{2}-\d{2}$'),
        "example":   "2015-11-02",
        "normalize": lambda v: v,
    },
    "currency": {
        "pattern":   re.compile(r'[A-Z]{2,3}[\s,]?\d|^\d[\d,\.]+$'),
        "example":   "EUR 1,000,000",
        "normalize": lambda v: v.strip(),
    },
    "number": {
        "pattern":   re.compile(r'^\d[\d,\.]*$'),
        "example":   "145",
        "normalize": lambda v: v.strip(),
    },
    "text": {
        "pattern":   re.compile(r'.+'),
        "example":   "any text",
        "normalize": lambda v: v.strip(),
    },
}

MONTH_MAP = {
    "january": "01", "february": "02", "march": "03",
    "april": "04", "may": "05", "june": "06",
    "july": "07", "august": "08", "september": "09",
    "october": "10", "november": "11", "december": "12",
}

DATE_PATTERNS = [
    re.compile(r'(\w+)\s+(\d{1,2}),?\s+(\d{4})'),   # "January 15, 2020"
    re.compile(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})'), # "15/01/2020"
    re.compile(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})'), # "2020-01-15"
]


def _normalize_date(value: str) -> str:
    """Try to normalize a date string to YYYY-MM-DD."""
    # Already ISO format
    if re.match(r'^\d{4}-\d{2}-\d{2}$', value):
        return value

    # "Month Day, Year"
    m = DATE_PATTERNS[0].search(value)
    if m:
        month_name = m.group(1).lower()
        month = MONTH_MAP.get(month_name)
        if month:
            return f"{m.group(3)}-{month}-{int(m.group(2)):02d}"

    # "DD/MM/YYYY"
    m = DATE_PATTERNS[1].search(value)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"

    # "YYYY/MM/DD"
    m = DATE_PATTERNS[2].search(value)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    return value


def format_check(value: str, expected_format: str) -> dict:
    """
    Fast rule-based format validation. No LLM.

    Returns:
        {valid, normalized, issue}
    """
    if not value or str(value).strip() in ("", "null", "None", "N/A"):
        return {"valid": False, "normalized": None, "issue": "null or empty value"}

    value = str(value).strip()
    rule  = FORMAT_RULES.get(expected_format, FORMAT_RULES["text"])

    # Date: attempt normalization first
    if expected_format == "date":
        value = _normalize_date(value)
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', value):
            return {
                "valid": False, "normalized": value,
                "issue": f"cannot normalize date — expected YYYY-MM-DD, got '{value}'",
            }
        return {"valid": True, "normalized": value, "issue": ""}

    # Percentage: auto-add % if bare number
    if expected_format == "percentage" and re.match(r'^\d+\.?\d*$', value):
        value = value + "%"

    if not rule["pattern"].search(value):
        return {
            "valid": False, "normalized": value,
            "issue": f"format mismatch — expected {expected_format} (e.g. {rule['example']}), got '{value}'",
        }

    try:
        normalized = rule["normalize"](value)
    except Exception:
        normalized = value

    return {"valid": True, "normalized": normalized, "issue": ""}


# ── LLM validation prompt ──────────────────────────────────────────────────────

LLM_VALIDATION_PROMPT = """You are a financial data validation assistant.

TASK: Validate and correct the extracted value for this field.

KEY NAME       : "{key_name}"
EXTRACTED VALUE: "{value}"
EXPECTED FORMAT: "{expected_format}" (example: {format_example})
FORMAT ISSUE   : "{format_issue}"

DEFINITION FROM DOCUMENT:
{definition_text}

DOCUMENT TEXT (relevant pages):
{page_text}

INSTRUCTIONS:
1. Check if the value appears in the document text above.
2. If the value is wrong or null: search the document text for the correct value.
3. If found: return the corrected, normalized value.
4. If genuinely not in the document: return null for value.
5. Normalize the value to the expected format.
6. Score 0.0–1.0:
   1.0 = found verbatim, correct format
   0.8 = found with minor normalization
   0.6 = inferred from context, high confidence
   0.4 = best guess, low confidence
   0.0 = not found in document

Return ONLY JSON:
{{
  "value": "<corrected value or null>",
  "score": <0.0–1.0>,
  "reason": "<max 15 words explaining the decision>",
  "format_valid": true/false
}}"""


def _quick_currency_from_text(key_name: str, page_text: str) -> str | None:
    """
    Fast regex scan for currency codes embedded in table headers or paragraphs.
    Called when value is None and key_name suggests a currency lookup.
    """
    if not any(w in key_name.lower() for w in ("currency", "devise", "monnaie")):
        return None
    # Match ISO currency codes in parentheses or standalone: (EUR), expressed in USD, etc.
    for pat in [
        re.compile(r'expressed in\s+([A-Z]{3})', re.IGNORECASE),
        re.compile(r'\(expressed in\s+([A-Z]{3})\)', re.IGNORECASE),
        re.compile(r'amount.*?\(([A-Z]{3})\)', re.IGNORECASE),
        re.compile(r'\b(EUR|USD|GBP|XOF|JPY|CHF|MAD|TND)\b'),
    ]:
        m = pat.search(page_text)
        if m:
            return m.group(1).upper()
    return None


def run(key_name: str,
        value,
        expected_format: str,
        definition_text: str,
        page_text: str,
        client,
        confidence: float = 0.5) -> dict:
    """
    Validate the extracted value.

    Args:
        key_name        : field name
        value           : extracted value (may be None)
        expected_format : "percentage"/"ratio"/"date"/"currency"/"number"/"text"
        definition_text : definition from Description Agent (may be "")
        page_text       : relevant OCR page text for cross-reference
        client          : LLMClient (agent_validator)
        confidence      : raw extraction confidence (0–1)

    Returns:
        {value, score, reason, format_valid}
    """
    print(f"  [Validator] '{key_name}': value={value!r}  format={expected_format}")

    # ── Step 0: Regex rescue for null currency fields ─────────────────────────
    if value is None:
        rescued = _quick_currency_from_text(key_name, page_text)
        if rescued:
            print(f"  [Validator] Regex rescued currency: {rescued!r}")
            return {"value": rescued, "score": 0.75,
                    "reason": "Currency code extracted from table header",
                    "format_valid": True}

    # ── Step 1: Format check (no LLM) ─────────────────────────────────────────
    check = format_check(str(value) if value is not None else "", expected_format)

    if check["valid"] and confidence >= 0.7:
        # Good format + decent confidence → accept without LLM
        score = min(1.0, confidence + 0.05)
        print(f"  {GREEN}[Validator] Accepted:{RESET} format valid, conf={confidence:.2f} → score={score:.2f}")
        return {
            "value":        check["normalized"],
            "score":        round(score, 2),
            "reason":       "Format valid, confidence sufficient",
            "format_valid": True,
        }

    # ── Step 2: LLM validation (value null, bad format, or low confidence) ────
    rule          = FORMAT_RULES.get(expected_format, FORMAT_RULES["text"])
    format_issue  = check.get("issue", "")

    print(f"  {YELLOW}[Validator] Calling LLM:{RESET} "
          f"valid={check['valid']} conf={confidence:.2f} issue='{format_issue[:50]}'")

    prompt = LLM_VALIDATION_PROMPT.format(
        key_name        = key_name,
        value           = value if value is not None else "null",
        expected_format = expected_format,
        format_example  = rule["example"],
        format_issue    = format_issue or "none",
        definition_text = definition_text[:500] if definition_text else "Not available",
        page_text       = page_text[:3000] if page_text else "Not available",
    )

    try:
        result = client.chat_json(prompt, max_tokens=256)
    except Exception as e:
        print(f"  {RED}[Validator] LLM error: {e}{RESET}")
        return {
            "value":        check.get("normalized") or value,
            "score":        round(max(0.0, confidence - 0.2), 2),
            "reason":       f"LLM validation failed: {str(e)[:40]}",
            "format_valid": check["valid"],
        }

    if not isinstance(result, dict):
        return {
            "value":        check.get("normalized") or value,
            "score":        round(max(0.0, confidence - 0.2), 2),
            "reason":       "LLM returned invalid response",
            "format_valid": check["valid"],
        }

    result["format_valid"] = result.get("format_valid", check["valid"])
    print(f"  [Validator] LLM result: value={result.get('value')!r}  "
          f"score={result.get('score')}  reason={result.get('reason','')[:50]}")
    return result
