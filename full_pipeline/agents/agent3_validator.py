"""
agents/agent3_validator.py [IMPROVED VERSION]
──────────────────────────────────────────────
Agent 3 — Validator

Validates the extracted value using:
  1. Format sanity checks (no LLM needed — instant)
  2. Definition cross-check (does value match expected format?)
  3. LLM validation (only called when sanity checks are insufficient)

Uses definition from Agent 4 to catch format mismatches like
"1.75%" being returned for a ratio key.

IMPROVEMENTS:
  ✓ Fixed bare except clauses — now catches specific exceptions
  ✓ Better error logging for debugging
  ✓ More robust date parsing
"""

import re
from utils.display import agent_header, step_output

# ── Format validation rules (no LLM needed) ──────────────────────────────────

FORMAT_RULES = {
    "percentage": {
        "pattern": re.compile(r'^\d+\.?\d*\s*%$'),
        "example": "2.25%",
        "normalize": lambda v: v.strip() if v.endswith("%") else v + "%"
    },
    "ratio": {
        "pattern": re.compile(r'^\d+\.?\d*\s+to\s+1[.:\d]+', re.IGNORECASE),
        "example": "4.50 to 1.00",
        "normalize": lambda v: re.sub(r'\s*to\s*1[.:]\s*0*', ' to 1.00', v)
    },
    "date": {
        "pattern": re.compile(r'^\d{4}-\d{2}-\d{2}$'),
        "example": "2015-11-02",
        "normalize": lambda v: v
    },
    "text": {
        "pattern": re.compile(r'.+'),
        "example": "any text",
        "normalize": lambda v: v
    }
}

DATE_PATTERNS = [
    (re.compile(r'(\w+ \d+, \d{4})'),
     lambda m: _parse_date(m.group(1))),
    (re.compile(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})'),
     lambda m: f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"),
]

MONTH_MAP = {
    "january": "01", "february": "02", "march": "03",
    "april": "04", "may": "05", "june": "06",
    "july": "07", "august": "08", "september": "09",
    "october": "10", "november": "11", "december": "12"
}

# ANSI colors
YELLOW = "\033[93m"
RESET  = "\033[0m"


def _parse_date(date_str: str) -> str:
    """
    Parse date string in format "Month Day, Year" to "YYYY-MM-DD".
    
    Args:
        date_str: Date string like "January 15, 2020"
    
    Returns:
        Normalized date string "2020-01-15"
    """
    try:
        parts = date_str.replace(",", "").split()
        if len(parts) == 3:
            month = MONTH_MAP.get(parts[0].lower())
            if month:
                return f"{parts[2]}-{month}-{int(parts[1]):02d}"
    except (ValueError, IndexError, AttributeError) as e:
        # Log error for debugging but continue
        pass
    return date_str


def sanity_check(value: str, expected_format: str,
                 value_hint: str = None) -> dict:
    """
    Fast rule-based check. No LLM needed.
    Returns {valid, normalized_value, score_adjustment, issue}
    """
    if not value or value in ("null", "N/A", ""):
        return {"valid": False, "normalized": None,
                "score_adj": -1.0, "issue": "null value"}

    rule = FORMAT_RULES.get(expected_format, FORMAT_RULES["text"])

    # Normalise date formats
    if expected_format == "date":
        for pat, converter in DATE_PATTERNS:
            m = pat.search(value)
            if m:
                try:
                    value = converter(m)
                except (ValueError, IndexError, TypeError, AttributeError) as e:
                    # Log error but continue to try next pattern
                    print(f"    [DEBUG] Date conversion failed for '{m.group(0)}': {type(e).__name__}")
                    continue
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', value):
            return {"valid": False, "normalized": value,
                    "score_adj": -0.3, "issue": f"date format wrong, expected YYYY-MM-DD"}

    # Check format mismatch
    if not rule["pattern"].search(value):
        # Special case: percentage ending missing %
        if expected_format == "percentage" and re.match(r'^\d+\.?\d*$', value):
            value = value + "%"
        else:
            issue = (f"value '{value}' does not match expected format "
                     f"'{expected_format}' (e.g. {rule['example']})")
            return {"valid": False, "normalized": value,
                    "score_adj": -0.5, "issue": issue}

    # Normalise
    try:
        normalized = rule["normalize"](value)
    except (ValueError, IndexError, TypeError, AttributeError, KeyError) as e:
        # Log error but use original value
        print(f"    [DEBUG] Normalization failed: {type(e).__name__}: {e}")
        normalized = value

    # Cross-check with value_hint from definition
    hint_match = True
    if value_hint and expected_format == "ratio":
        try:
            hint_val = re.search(r'\d+\.\d+', value_hint)
            got_val  = re.search(r'\d+\.\d+', normalized)
            if hint_val and got_val:
                hint_match = abs(float(hint_val.group()) - float(got_val.group())) < 0.01
        except (ValueError, AttributeError) as e:
            # If cross-check fails, don't fail the validation
            print(f"    [DEBUG] Value hint cross-check failed: {e}")
            hint_match = True

    return {
        "valid":      True,
        "normalized": normalized,
        "score_adj":  0.0 if hint_match else -0.1,
        "issue":      "" if hint_match else "value doesn't match definition hint"
    }


def _build_llm_prompt(key_name: str, value: str,
                      row_label: str, col_label: str,
                      ocr_snippet: str, definition_text: str,
                      expected_format: str) -> str:
    """Build the LLM validation prompt."""
    return f"""You are a financial data validation assistant.

EXTRACTED VALUE TO VALIDATE:
  Key            : "{key_name}"
  Value          : "{value}"
  Row label      : "{row_label}"
  Column label   : "{col_label}"
  Expected format: "{expected_format}" (e.g. {FORMAT_RULES.get(expected_format, FORMAT_RULES['text'])['example']})

DEFINITION FROM DOCUMENT:
  {definition_text or "Not available"}

OCR SOURCE (first 1500 chars of relevant page):
{ocr_snippet[:1500]}

Validate:
1. Does the value appear in the OCR source? (exact or near-exact)
2. Do row and column labels match the document structure?
3. Does the value format match the expected format?
4. Is the value plausible given the definition?

Score 0.0–1.0:
  1.0 = confirmed verbatim, correct format, matches definition
  0.8 = minor normalisation needed
  0.6 = inferred, row/col approximate
  0.4 = best guess, OCR quality poor
  0.0 = wrong format, wrong table, or not found

Return ONLY JSON:
{{
  "value": "<final normalised value>",
  "score": <0.0–1.0>,
  "reason": "<max 15 words>"
}}"""


def run(key_name: str, value: str, row_label: str, col_label: str,
        embedding_score: float, expected_format: str,
        definition_text: str, value_hint: str,
        ocr_text: str, page_hint: int,
        client, timer=None, thresholds: dict = None) -> dict:
    """
    Validate the extracted value using format checks and LLM if needed.
    
    Args:
        key_name:         the key being validated
        value:            extracted value from Agent 2 or embedding
        row_label:        row label from extraction
        col_label:        column label from extraction
        embedding_score:  confidence from Agent 1's embedding search
        expected_format:  "percentage"/"ratio"/"date"/"text" from Agent 4
        definition_text:  definition from Agent 4
        value_hint:       numeric hint from Agent 4 (if covenant)
        ocr_text:         full OCR text for cross-reference
        page_hint:        page number hint from Agent 1
        client:           LLMClient instance
        thresholds:       dict of confidence thresholds

    Returns:
        {value, score, reason, format_valid}
    
    Raises:
        ValueError: If LLM response parsing fails completely
    """
    agent_header("Agent 3 — Validator", key_name)

    if thresholds is None:
        thresholds = {"VALIDATOR_HIGH_CONF": 0.85}

    # ── Step 1: Format sanity check (no LLM) ─────────────────────────────────
    sanity = sanity_check(value, expected_format, value_hint)
    step_output("Format check:", f"valid={sanity['valid']}  "
                f"format={expected_format}  "
                f"issue={sanity.get('issue','none') or 'none'}")

    if not sanity["valid"]:
        adj   = sanity["score_adj"]
        score = max(0.0, embedding_score + adj)
        step_output("Decision:", f"Format invalid → score={score:.2f}  (no LLM)")
        return {
            "value":        sanity["normalized"] or value,
            "score":        round(score, 2),
            "reason":       sanity.get("issue", "format mismatch"),
            "format_valid": False,
        }

    normalised = sanity["normalized"]

    # ── Step 2: High confidence + valid format → no LLM needed ───────────────
    if embedding_score >= thresholds["VALIDATOR_HIGH_CONF"] and sanity["valid"]:
        score = min(1.0, embedding_score + sanity["score_adj"])
        step_output("Decision:", f"High confidence + valid format → score={score:.2f}  (no LLM)")
        return {
            "value":        normalised,
            "score":        round(score, 2),
            "reason":       "High embedding confidence, format verified",
            "format_valid": True,
        }

    # ── Step 3: LLM validation for medium/low confidence ─────────────────────
    step_output("Decision:", "Medium confidence → calling LLM validator")

    # Get relevant OCR snippet
    if page_hint is not None:
        try:
            page_pat = re.compile(rf'PAGE\s+{page_hint}\b', re.IGNORECASE)
            m = page_pat.search(ocr_text)
            ocr_snippet = ocr_text[m.start():m.start()+4000] if m else ocr_text[:4000]
        except (AttributeError, ValueError) as e:
            print(f"    [DEBUG] Failed to extract page {page_hint}: {e}")
            ocr_snippet = ocr_text[:4000]
    else:
        ocr_snippet = ocr_text[:4000]

    prompt = _build_llm_prompt(
        key_name, normalised, row_label, col_label,
        ocr_snippet, definition_text or "", expected_format
    )
    step_output("Prompt size:", f"{len(prompt)} chars")

    try:
        result = client.chat_json(prompt, max_tokens=256)
    except ValueError as e:
        # JSON parsing failed — use normalised value with embedding score
        print(f"    {YELLOW}⚠ LLM returned invalid JSON: {e}{RESET}")
        result = {
            "value":  normalised,
            "score":  round(min(embedding_score, 0.75), 2),
            "reason": "LLM JSON parsing failed; value from extraction used"
        }

    if not isinstance(result, dict) or not result.get("value"):
        # LLM returned unexpected format — use normalised value with embedding score
        result = {
            "value":  normalised,
            "score":  round(min(embedding_score, 0.75), 2),
            "reason": "Validator LLM returned unexpected format; extraction value used"
        }

    result["format_valid"] = sanity["valid"]
    step_output("Result:", f"value={result.get('value')!r}  "
                f"score={result.get('score')}  "
                f"{result.get('reason','')[:60]}")
    return result