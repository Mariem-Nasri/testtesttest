"""
agents/agent_description.py
─────────────────────────────
Description Agent — always runs in parallel with extraction agents

Searches the definitions/terms section of the document for the
formal definition of the key term.

Rules:
  ✓ Found in document → returns the definition text
  ✗ Not found         → returns "" (empty string)
  ✗ NEVER generates a synthetic definition

Uses llama-4-scout (Groq) or qwen2.5:7b (Ollama) — fast model,
simple task.
"""

import re
from pathlib import Path


DESCRIPTION_PROMPT = """You are a legal document analyst searching for a term's definition.

TERM TO FIND: "{key_name}"

DEFINITIONS / TERMS SECTION OF DOCUMENT:
{definitions_text}

INSTRUCTIONS:
1. Search the text above for a formal definition of "{key_name}" or any of its common aliases.
2. A definition typically looks like:
   - "{key_name}" means ...
   - "{key_name}" shall mean ...
   - "{key_name}" is defined as ...
   - Definition of "{key_name}": ...
3. Extract the COMPLETE definition sentence(s) — do not truncate.
4. If the exact term is not found, check for closely related terms or abbreviations.
5. If NO definition exists in this text: return empty string for definition_text.
   DO NOT create, infer, or generate a definition. Only return what is literally in the text.

Return ONLY JSON, no explanation:
{{
  "definition_text": "<exact definition from document, or empty string if not found>",
  "source_page": <page number or null>,
  "alias_used": "<the exact phrasing found, if different from key name, or null>"
}}"""


def _extract_definition_text(ocr_text: str, definitions_pages: list[int]) -> str:
    """
    Extract text from the definitions pages.
    Falls back to heuristic search if pages list is empty.
    """
    # Split into pages
    page_pattern = re.compile(r'={20,}\s*\nPAGE\s+(\d+)\s*\n={20,}', re.IGNORECASE)
    splits = list(page_pattern.finditer(ocr_text))

    if not splits:
        return ocr_text[:4000]

    pages_dict = {}
    for i, match in enumerate(splits):
        pnum  = int(match.group(1))
        start = match.end()
        end   = splits[i + 1].start() if i + 1 < len(splits) else len(ocr_text)
        pages_dict[pnum] = ocr_text[start:end].strip()

    if definitions_pages:
        parts = []
        for p in definitions_pages:
            if p in pages_dict:
                parts.append(f"[Page {p}]\n{pages_dict[p]}")
        if parts:
            return "\n\n".join(parts)

    # Heuristic fallback: search all pages for "means" / "shall mean" density
    best_page  = None
    best_count = 0
    for pnum, text in pages_dict.items():
        count = (text.lower().count(" means ") +
                 text.lower().count("shall mean") +
                 text.lower().count("is defined as") +
                 text.lower().count('"definitions"'))
        if count > best_count:
            best_count = count
            best_page  = pnum

    if best_page and best_count > 0:
        nearby = []
        for p in range(max(1, best_page - 1), best_page + 3):
            if p in pages_dict:
                nearby.append(f"[Page {p}]\n{pages_dict[p]}")
        return "\n\n".join(nearby)

    # Last resort: first 4000 chars
    return ocr_text[:4000]


def run(key_name: str,
        ocr_text: str,
        definitions_pages: list[int],
        client) -> dict:
    """
    Search the definitions section for the formal definition of key_name.

    Args:
        key_name          : term to define (e.g. "Leverage Ratio")
        ocr_text          : full OCR text
        definitions_pages : page numbers of the definitions section (from DocMap)
        client            : LLMClient (agent_description)

    Returns:
        {
            "definition_text": "<text from document or empty string>",
            "source_page": <int or null>,
            "alias_used": <str or null>
        }
    """
    print(f"  [Desc] Searching definition for '{key_name}'")

    definitions_text = _extract_definition_text(ocr_text, definitions_pages)

    if not definitions_text.strip():
        return {
            "definition_text": "",
            "source_page":     None,
            "alias_used":      None,
        }

    prompt = DESCRIPTION_PROMPT.format(
        key_name         = key_name,
        definitions_text = definitions_text[:4500],
    )

    try:
        result = client.chat_json(prompt, max_tokens=512)
    except Exception as e:
        print(f"  [Desc] LLM error: {e}")
        return {"definition_text": "", "source_page": None, "alias_used": None}

    if not isinstance(result, dict):
        return {"definition_text": "", "source_page": None, "alias_used": None}

    # Enforce: never return None, always return "" if not found
    definition_text = result.get("definition_text") or ""
    print(f"  [Desc] {'Found' if definition_text else 'Not found'}: "
          f"{definition_text[:80]!r}")

    return {
        "definition_text": definition_text,
        "source_page":     result.get("source_page"),
        "alias_used":      result.get("alias_used"),
    }
