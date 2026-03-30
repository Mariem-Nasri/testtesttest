"""
core/format_detector.py
───────────────────────
Rule-based format detector for financial key names.
Works on ANY loan agreement without document-specific knowledge.

Priority order:
  1. Key name pattern rules (fast, no LLM)
  2. Key description hints (fast, no LLM)
  3. Agent 4 definition output (LLM-based, fallback)

This prevents Agent 4 from misidentifying rate keys as ratio keys
just because both mention "Leverage Ratio" in their name.
"""

import re

# ── Format patterns — ordered from most specific to most general ──────────────

# PERCENTAGE: interest rates, fees, margins, spreads
PERCENTAGE_PATTERNS = [
    r'\b(loan|libor|abr|sofr|prime|base)\s+rate\b',
    r'\bapplicable\s+margin\b',
    r'\bcommitment\s+fee\b',
    r'\b(utilization|unused)\s+fee\b',
    r'\bletter\s+of\s+credit\s+fee\b',
    r'\bfacility\s+fee\b',
    r'\bspread\b',
    r'\bmargin\b.*\butilization\b',
    r'\butilization\b.*\bmargin\b',
    r'\brate\b.*\b(utilization|leverage|grid)\b',
    r'\b(utilization|leverage|grid)\b.*\brate\b',
]

# RATIO: financial covenants expressed as X.XX to 1.00
RATIO_PATTERNS = [
    r'\bcovenant\b',
    r'\b(leverage|coverage|interest\s+coverage|interest\s+expense)\s+ratio\s+covenant\b',
    r'\b(maximum|minimum|not\s+to\s+exceed|not\s+less\s+than)\b.*\bratio\b',
    r'\bfirst\s+lien\b.*\bratio\b',
    r'\bsenior\s+secured\b.*\bratio\b',
    r'\bdebt\s+service\s+coverage\b',
    r'\btotal\s+net\s+leverage\b',
    r'\bfixed\s+charge\s+coverage\b',
    r'\basset\s+coverage\b',
]

# DATE
DATE_PATTERNS = [
    r'\b(agreement|effective|closing|execution)\s+date\b',
    r'\b(maturity|termination|expiration|expiry)\s+date\b',
    r'\b(first|initial|final)\s+(payment|due|scheduled)\s+date\b',
    r'\bdate\s+of\s+(agreement|amendment|restatement)\b',
    r'\bcommencement\s+date\b',
]

# AMOUNT (dollar amounts)
AMOUNT_PATTERNS = [
    r'\b(total|aggregate|maximum|commitment)\s+(amount|facility|commitment)\b',
    r'\b(revolving|term|swingline)\s+(loan|facility|commitment)\s+(amount|limit|cap)\b',
    r'\bborrowing\s+base\b(?!.*\bpercentage\b)(?!.*\butilization\b)',
    r'\bcredit\s+(limit|cap|facility)\b',
    r'\b(letter\s+of\s+credit)\s+sublimit\b',
]

# MULTIPLE (e.g. 3.50x — used in grid column headers, not covenants)
MULTIPLE_PATTERNS = [
    r'\bratio\s+[<>≥≤]\s*\d+\.\d+x\b',
    r'\b[<>≥≤]\s*\d+\.\d+x\b.*\bratio\b',
]


def detect_format(key_name: str, key_description: str = "") -> str:
    """
    Detect expected value format from key name and description.

    Returns: "percentage" | "ratio" | "date" | "amount" | "text"
    """
    text = f"{key_name} {key_description}".lower()

    # Check PERCENTAGE first — most specific for rate grid keys
    for pat in PERCENTAGE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return "percentage"

    # Check RATIO — covenant keys
    for pat in RATIO_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return "ratio"

    # Check DATE
    for pat in DATE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return "date"

    # Check AMOUNT
    for pat in AMOUNT_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return "amount"

    # Check MULTIPLE (grid column references)
    for pat in MULTIPLE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return "ratio"

    return "text"


def merge_format(
    rule_based: str,
    agent4_format: str,
    key_name: str,
) -> str:
    """
    Merge rule-based format detection with Agent 4's LLM output.

    Rules:
    - If rule_based is specific (not "text") → trust rule_based
    - If rule_based is "text" and agent4 is specific → use agent4
    - Special case: if key contains "rate" → always percentage
      even if Agent 4 said ratio (prevents the Leverage Ratio confusion)
    """
    kn = key_name.lower()

    # Hard override: if key name contains explicit rate/fee words
    # → always percentage, never ratio
    if re.search(r'\b(loan\s+rate|libor\s+rate|abr\s+rate|sofr\s+rate|'
                 r'commitment\s+fee|facility\s+fee|applicable\s+margin)\b',
                 kn, re.IGNORECASE):
        return "percentage"

    # Hard override: if key contains explicit covenant words
    # → always ratio
    if re.search(r'\b(covenant|not\s+to\s+exceed|not\s+less\s+than)\b',
                 kn, re.IGNORECASE):
        return "ratio"

    # Trust rule-based if it found a specific format
    if rule_based != "text":
        return rule_based

    # Fall back to Agent 4
    if agent4_format and agent4_format != "text":
        return agent4_format

    return "text"


def expected_value_pattern(fmt: str) -> str:
    """Return a human-readable description of what the value should look like."""
    return {
        "percentage": "X.XX% (e.g. 2.25%)",
        "ratio":      "X.XX to 1.00 (e.g. 4.50 to 1.00)",
        "date":       "YYYY-MM-DD (e.g. 2015-11-02)",
        "amount":     "$X,XXX,XXX or $XXXmm (e.g. $500,000,000)",
        "text":       "free text",
    }.get(fmt, "unknown format")