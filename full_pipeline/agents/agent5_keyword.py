"""
agents/agent5_keyword.py
────────────────────────
Agent 5 — Keyword Search

Searches the full OCR text for all occurrences of a given keyword/phrase.
Returns all matches with page numbers, surrounding context, and exact text.
"""

import re
from utils.display import agent_header, step_output


def run(key_name: str, key_description: str, ocr_text: str, client=None) -> dict:
    """
    Args:
        key_name:        the keyword to search for (e.g. "category")
        key_description: optional context (ignored for now)
        ocr_text:        full OCR text
        client:          LLMClient (not used for keyword search)

    Returns:
        {
            "value": list of matches,
            "count": number of matches,
            "matches": [
                {
                    "page": int,
                    "text": "exact match text",
                    "context": "surrounding 100 chars",
                    "position": int  # start position in OCR
                },
                ...
            ]
        }
    """
    agent_header("Agent 5 — Keyword Search", key_name)

    # Build page-position lookup
    page_pattern = re.compile(r'={20,}\s*\nPAGE\s+(\d+)\s*\n={20,}', re.IGNORECASE)
    page_splits = list(page_pattern.finditer(ocr_text))

    def get_page(pos):
        for i, match in enumerate(page_splits):
            if pos < match.start():
                return int(page_splits[i-1].group(1)) if i > 0 else 1
        return int(page_splits[-1].group(1)) if page_splits else 1

    # Search for the keyword (case-insensitive, word boundaries)
    keyword = re.escape(key_name.strip())
    pattern = re.compile(rf'\b{re.escape(key_name)}\b', re.IGNORECASE)
    matches = []

    for match in pattern.finditer(ocr_text):
        start = match.start()
        end = match.end()
        page = get_page(start)

        # Extract surrounding context (100 chars before and after)
        ctx_start = max(0, start - 100)
        ctx_end = min(len(ocr_text), end + 100)
        context = ocr_text[ctx_start:ctx_end].replace('\n', ' ').strip()

        matches.append({
            "page": page,
            "text": match.group(0),
            "context": context,
            "position": start
        })

    step_output("Search results:", f"Found {len(matches)} occurrences of '{key_name}'")

    if matches:
        for i, m in enumerate(matches[:5]):  # Show first 5
            step_output(f"Match {i+1}:", f"Page {m['page']} — {m['context'][:80]}...")
        if len(matches) > 5:
            step_output("...", f"and {len(matches) - 5} more")

    return {
        "value": [m["text"] for m in matches],  # List of exact matches
        "count": len(matches),
        "matches": matches
    }