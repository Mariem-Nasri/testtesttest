"""
agents/agent_description.py
─────────────────────────────
Description Agent — always runs in parallel with extraction agents

Searches the full document for the most authoritative definition of a term,
prioritizing verbatim fidelity. Extracts candidate snippets containing the
key term (or near it) from the full OCR text, then uses an LLM to pick and
extract the best definition.

Rules:
  ✓ Found in document → returns the definition text (verbatim or reconstructed)
  ✗ Not found         → returns "" (empty string)
  ✗ NEVER generates a synthetic definition
"""

import re


# ── Snippet extraction ────────────────────────────────────────────────────────

def _extract_candidate_snippets(ocr_text: str, key_name: str,
                                 definitions_pages: list[int],
                                 max_snippets: int = 8) -> list[dict]:
    """
    Extract candidate text snippets that are likely to contain a definition
    of key_name. Searches definitions pages first, then the full document.
    Each snippet is a sentence or short paragraph with a page tag.
    """
    page_pattern = re.compile(r'={20,}\s*\nPAGE\s+(\d+)\s*\n={20,}', re.IGNORECASE)
    splits = list(page_pattern.finditer(ocr_text))

    pages_dict = {}
    if splits:
        for i, match in enumerate(splits):
            pnum  = int(match.group(1))
            start = match.end()
            end   = splits[i + 1].start() if i + 1 < len(splits) else len(ocr_text)
            pages_dict[pnum] = (ocr_text[start:end].strip(), match.start())
    else:
        pages_dict[1] = (ocr_text, 0)

    # Keywords that signal a definition (formal or operational)
    def_signals = re.compile(
        r'means\b|shall mean|is defined as|refers to|"definitions"|'
        r'herein defined|defined term|as used herein|'
        r'\bis\b|\bequals\b|\bshall be\b|\bwill be\b|\bcalculated as\b|'
        r'\bpayable at\b|\bpayable in\b|\bamounts to\b|\brepresents\b',
        re.IGNORECASE
    )

    # Build search terms from key_name (words ≥ 3 chars)
    key_words = [w for w in re.split(r'\W+', key_name) if len(w) >= 3]
    key_pattern = re.compile('|'.join(re.escape(w) for w in key_words), re.IGNORECASE)

    snippets = []

    def _add_snippets_from_text(text: str, page_num: int, priority: int):
        sentences = re.split(r'(?<=[.!?])\s+|\n{2,}', text)
        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 20 or len(sent) > 600:
                continue
            if not key_pattern.search(sent):
                continue
            score = priority
            if def_signals.search(sent):
                score += 2
            if re.search(re.escape(key_name), sent, re.IGNORECASE):
                score += 1
            snippets.append({"snippet": sent, "page": page_num, "score": score})

    # Priority 1: definitions pages
    for pnum in definitions_pages:
        if pnum in pages_dict:
            _add_snippets_from_text(pages_dict[pnum][0], pnum, priority=3)

    # Priority 2: rest of document
    for pnum, (text, _) in pages_dict.items():
        if pnum not in definitions_pages:
            _add_snippets_from_text(text, pnum, priority=1)

    # Deduplicate and sort by score desc
    seen = set()
    unique = []
    for s in sorted(snippets, key=lambda x: -x["score"]):
        key = s["snippet"][:80]
        if key not in seen:
            seen.add(key)
            unique.append(s)

    return unique[:max_snippets]


# ── Prompt ────────────────────────────────────────────────────────────────────

DESCRIPTION_PROMPT = """You are a Definition Extraction Agent for legal and financial documents.

Your task: find the snippet below that best answers the question "What is {key_name}?" and extract it verbatim.

KEY NAME: "{key_name}"

CANDIDATE SNIPPETS:
{snippet_block}

────────────────────────────────────────────

WHAT COUNTS AS A DEFINITION (be inclusive — no formal signal words required):

Any snippet that tells you what the term IS, how it is calculated, what it equals,
or what it obligates — regardless of phrasing. All of these are valid definitions:

  ✓ "X means Y"                          (explicit)
  ✓ "X shall mean Y"                     (explicit)
  ✓ "The X is Y% of the Loan amount."    (operational — IS = definition)
  ✓ "2.03. The X is one quarter of 1%."  (numbered clause — still a definition)
  ✓ "X equals Y."                        (mathematical definition)
  ✓ "X shall be calculated as Y."        (procedural definition)
  ✓ "X will not exceed Y."               (constraint definition)
  ✓ "X is payable at Y."                 (contractual definition)

RULES:

1. Extract the sentence **verbatim** — do not paraphrase or reword.
2. Remove only leading article numbers like "2.03." if present — keep the rest intact.
3. Prefer the snippet closest to a formal definition, but accept any operational description.
4. If multiple snippets are relevant, use the most complete and direct one.
5. If NO snippet meaningfully answers "What is {key_name}?", return empty string — do NOT hallucinate.

Return ONLY JSON:
{{
  "extraction_mode": "verbatim",
  "definition_text": "<exact sentence from document, or empty string>",
  "source_page": <page number or null>
}}"""


# ── Agent entry point ─────────────────────────────────────────────────────────

def run(key_name: str,
        ocr_text: str,
        definitions_pages: list[int],
        client) -> dict:
    """
    Search the full document for the formal definition of key_name.

    Returns:
        {
            "definition_text": "<text from document or empty string>",
            "extraction_mode": "verbatim" | "reconstructed",
            "source_page": <int or null>,
        }
    """
    print(f"  [Desc] Searching definition for '{key_name}'")

    snippets = _extract_candidate_snippets(ocr_text, key_name, definitions_pages)

    if not snippets:
        print(f"  [Desc] No candidate snippets found")
        return {"definition_text": "", "extraction_mode": "verbatim", "source_page": None}

    snippet_block = "\n".join(
        f"  [{i+1}] (page {s['page']}) {s['snippet']}"
        for i, s in enumerate(snippets)
    )

    prompt = DESCRIPTION_PROMPT.format(
        key_name     = key_name,
        snippet_block = snippet_block,
    )

    try:
        result = client.chat_json(prompt, max_tokens=512)
    except Exception as e:
        print(f"  [Desc] LLM error: {e}")
        return {"definition_text": "", "extraction_mode": "verbatim", "source_page": None}

    if not isinstance(result, dict):
        return {"definition_text": "", "extraction_mode": "verbatim", "source_page": None}

    definition_text  = result.get("definition_text") or ""
    extraction_mode  = result.get("extraction_mode") or "verbatim"
    source_page      = result.get("source_page")

    print(f"  [Desc] {'Found' if definition_text else 'Not found'}: "
          f"{definition_text[:80]!r}  [{extraction_mode}]")

    return {
        "definition_text": definition_text,
        "extraction_mode": extraction_mode,
        "source_page":     source_page,
    }
