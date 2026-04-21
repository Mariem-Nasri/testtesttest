"""
template_registry.py
──────────────────────────────────────────────────────────────────────────────
Maps roles → allowed document subtypes → template files.

To add a new document type:
  1. Create backend/templates/{role}_{subtype}.json
  2. Add an entry to ROLE_TEMPLATES below
  3. Add a prompt file full_pipeline/agents/prompts/{subtype}_terms.txt
     and optionally {subtype}_rules.txt
"""

import json
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "templates"

# ── Role → doc subtypes mapping ───────────────────────────────────────────────
ROLE_TEMPLATES: dict[str, list[dict]] = {
    "banking": [
        {
            "subtype":       "loan",
            "display_name":  "Loan / Credit Agreement",
            "template_file": "banking_loan.json",
            "prompt_terms":  "loan_terms",
            "prompt_rules":  "loan_rules",
        },
        {
            "subtype":       "isda",
            "display_name":  "ISDA Master Agreement",
            "template_file": "banking_isda.json",
            "prompt_terms":  "isda_terms",
            "prompt_rules":  "isda_rules",
        },
    ],
    "insurance": [
        {
            "subtype":       "invoice",
            "display_name":  "Insurance Policy / Premium Invoice",
            "template_file": "insurance_policy.json",
            "prompt_terms":  "invoice_terms",
            "prompt_rules":  "invoice_terms",  # reuse terms for rules
        },
    ],
    "compliance": [
        {
            "subtype":       "compliance_report",
            "display_name":  "Compliance / Risk Assessment Report",
            "template_file": "compliance_report.json",
            "prompt_terms":  "compliance_terms",
            "prompt_rules":  "compliance_terms",
        },
    ],
    # Admin can access all
    "admin": [
        {
            "subtype":       "loan",
            "display_name":  "Loan / Credit Agreement",
            "template_file": "banking_loan.json",
            "prompt_terms":  "loan_terms",
            "prompt_rules":  "loan_rules",
        },
        {
            "subtype":       "isda",
            "display_name":  "ISDA Master Agreement",
            "template_file": "banking_isda.json",
            "prompt_terms":  "isda_terms",
            "prompt_rules":  "isda_rules",
        },
        {
            "subtype":       "invoice",
            "display_name":  "Insurance Policy / Invoice",
            "template_file": "insurance_policy.json",
            "prompt_terms":  "invoice_terms",
            "prompt_rules":  "invoice_terms",
        },
        {
            "subtype":       "compliance_report",
            "display_name":  "Compliance Report",
            "template_file": "compliance_report.json",
            "prompt_terms":  "compliance_terms",
            "prompt_rules":  "compliance_terms",
        },
    ],
}


def get_subtypes_for_role(role: str) -> list[dict]:
    """Return list of allowed doc subtypes for a role."""
    return ROLE_TEMPLATES.get(role, [])


def load_template(role: str, subtype: str) -> dict:
    """
    Load the template JSON for a role+subtype combination.

    Returns:
        {doc_subtype, display_name, role, keys: [...]}

    Raises:
        ValueError if role or subtype is not allowed
    """
    subtypes = get_subtypes_for_role(role)
    entry    = next((s for s in subtypes if s["subtype"] == subtype), None)

    if entry is None:
        allowed = [s["subtype"] for s in subtypes]
        raise ValueError(
            f"Role '{role}' cannot access doc type '{subtype}'. "
            f"Allowed: {allowed}"
        )

    template_path = TEMPLATES_DIR / entry["template_file"]
    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")

    return json.loads(template_path.read_text(encoding="utf-8"))


def merge_with_extra_keys(template_keys: list, extra_keys: list) -> list:
    """
    Merge template keys with user-supplied extra keys.
    Extra keys are appended; duplicates (by keyName) are deduplicated.

    extra_keys format:
      [{"keyName": "X", "keyNameDescription": "..."}, ...]
    """
    existing_names = {k["keyName"].lower().strip() for k in template_keys}
    merged         = list(template_keys)

    for extra in extra_keys:
        name = extra.get("keyName", "").strip()
        if not name:
            continue
        if name.lower() not in existing_names:
            merged.append({
                "keyName":            name,
                "keyNameDescription": extra.get("keyNameDescription", ""),
                "expectedFormat":     extra.get("expectedFormat", "text"),
                "searchType":         extra.get("searchType", ""),
            })
            existing_names.add(name.lower())

    return merged
