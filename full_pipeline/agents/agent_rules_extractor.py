"""
agents/agent_rules_extractor.py
─────────────────────────────────
Rules Sub-Agent — sits under the Tables Agent

Takes:
  1. The raw table extraction output from agent_tables.py
  2. Surrounding paragraph text (clauses near the table)

Combines both to extract:
  - Exact rule / condition
  - Threshold values
  - Exceptions / carve-outs
  - Context that makes the table value meaningful

Called when the key type is "table" AND the key description suggests
a rule, condition, or covenant (not just a simple lookup value).

Uses llama-3.3-70b-versatile (Groq) or qwen2.5:7b (Ollama).
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_doc_type_rules(doc_type: str) -> str:
    """Load doc-type-specific rules prompt context if available."""
    rules_file = _PROMPTS_DIR / f"{doc_type}_rules.txt"
    if rules_file.exists():
        return rules_file.read_text(encoding="utf-8")
    return ""


RULES_PROMPT = """You are a financial document rules analyst.

{doc_type_context}

You have:
  1. A TABLE VALUE extracted from a data table in the document
  2. SURROUNDING PARAGRAPH TEXT — clauses and prose around or near the table

Your task: combine both sources to extract the COMPLETE RULE that governs this field.

KEY NAME: "{key_name}"
KEY DESCRIPTION: "{key_desc}"

TABLE EXTRACTION RESULT:
  Value        : {value}
  Row Label    : {row_label}
  Column Label : {col_label}
  Table Title  : {table_title}
  Confidence   : {confidence}

SURROUNDING PARAGRAPH TEXT (clauses near the table):
{surrounding_text}

INSTRUCTIONS:
1. Start with the table value — it is the numeric/factual anchor.
2. Search the paragraph text for clauses that:
   - Define WHEN this value applies (conditions)
   - State what HAPPENS if this threshold is exceeded (consequence)
   - Carve out EXCEPTIONS ("provided that", "unless", "except")
   - Set the MEASUREMENT BASIS (tested quarterly, on last day of fiscal year, etc.)
3. Combine table value + paragraph context into a complete rule statement.
4. If no qualifying paragraph text found, the rule_context should restate the table value cleanly.
5. Do NOT invent conditions or values not present in the text.

Return ONLY JSON, no explanation:
{{
  "value": "<the table value, cleaned and normalized>",
  "rule_context": "<complete rule: condition + value + consequence + exceptions, max 3 sentences>",
  "condition": "<what must be true for this value to apply, or null>",
  "consequence": "<what happens when threshold is reached, or null>",
  "exception": "<any carve-outs or exceptions, or null>",
  "measurement_basis": "<how/when this is measured, or null>",
  "page": <page number or null>,
  "confidence": "high/medium/low"
}}"""


def run(key_name: str, key_desc: str,
        table_result: dict,
        surrounding_text: str,
        client,
        doc_type: str = "loan") -> dict:
    """
    Combine table output + surrounding paragraph context to extract the full rule.

    Args:
        key_name         : field name
        key_desc         : field description
        table_result     : output from agent_tables.run()
        surrounding_text : paragraph text from pages around the table
        client           : LLMClient (agent_rules)
        doc_type         : "loan", "isda", "invoice", "compliance_report"

    Returns:
        {value, rule_context, condition, consequence, exception,
         measurement_basis, page, confidence}
    """
    print(f"  [Rules] Extracting rule for '{key_name}'")

    # If table agent returned null, still try from paragraph text
    value      = table_result.get("value")
    row_label  = table_result.get("row_label") or ""
    col_label  = table_result.get("column_label") or ""
    table_title = table_result.get("table_title") or "Unknown Table"
    confidence = table_result.get("confidence", "low")

    doc_type_context = _load_doc_type_rules(doc_type)

    prompt = RULES_PROMPT.format(
        doc_type_context = doc_type_context,
        key_name         = key_name,
        key_desc         = key_desc,
        value            = value or "null (not found in table)",
        row_label        = row_label or "N/A",
        col_label        = col_label or "N/A",
        table_title      = table_title,
        confidence       = confidence,
        surrounding_text = surrounding_text[:3000] if surrounding_text else "No surrounding paragraph text available.",
    )

    try:
        result = client.chat_json(prompt, max_tokens=768)
    except Exception as e:
        print(f"  [Rules] LLM error: {e}")
        result = None

    if not isinstance(result, dict):
        # Fallback: just pass through the table result
        return {
            "value":             value,
            "rule_context":      f"{key_name}: {value}" if value else None,
            "condition":         None,
            "consequence":       None,
            "exception":         None,
            "measurement_basis": None,
            "page":              table_result.get("page"),
            "confidence":        confidence,
        }

    # Ensure value is not overwritten with None if table had a good value
    if result.get("value") is None and value is not None:
        result["value"] = value
    if result.get("page") is None:
        result["page"] = table_result.get("page")

    print(f"  [Rules] value={result.get('value')!r}  "
          f"rule={str(result.get('rule_context',''))[:80]}")
    return result
