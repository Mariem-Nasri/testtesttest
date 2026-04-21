"""
agents/agent_document_map.py
─────────────────────────────
PHASE 1 — Document Map

ONE LLM call per document. Reads page summaries and returns a structured
map of WHERE each topic lives + whether it is a table or paragraph section.

This map is shared across ALL keys — every subsequent agent uses it to
know which pages to look at instead of scanning the full document.

Output format:
{
  "sections": [
    {
      "topic":    "Interest Rate Grid",
      "pages":    [5, 6],
      "type":     "table",        # "table" | "paragraph"
      "keywords": ["LIBOR", "margin", "leverage ratio"]
    },
    ...
  ],
  "definitions_pages": [1, 2, 3],   # pages containing definitions/terms section
  "parties_pages":     [1],          # pages listing parties
  "total_pages":       24
}
"""

import re
import json
from pathlib import Path

_AGENTS_DIR = Path(__file__).parent

# ── Prompt ────────────────────────────────────────────────────────────────────

DOC_MAP_PROMPT = """You are a financial document analyst. Your job is to create a structured index of a document.

Below are short summaries of each page in a scanned document. Read all summaries carefully.

PAGE SUMMARIES:
{page_summaries}

Your task: identify every DISTINCT SECTION or TOPIC in this document and classify it.

For each section:
1. Give it a descriptive topic name (e.g. "Interest Rate Grid", "Financial Covenants", "Definitions", "Parties")
2. List which pages it spans
3. Classify it as "table" (if the content is primarily a data table with rows/columns) or "paragraph" (if it is prose/clauses/text)
4. List 3-5 keywords that would appear in that section

Also identify:
- Which pages contain the "Definitions" or "Terms" section (where terms are formally defined)
- Which pages list the parties (Borrower, Lender, etc.)

Return ONLY valid JSON, no explanation:
{{
  "sections": [
    {{
      "topic":    "<descriptive section name>",
      "pages":    [<page numbers>],
      "type":     "table" or "paragraph",
      "keywords": ["<kw1>", "<kw2>", "<kw3>"]
    }}
  ],
  "definitions_pages": [<page numbers with definitions section>],
  "parties_pages":     [<page numbers listing parties>],
  "total_pages":       <total number of pages in document>
}}"""


# ── Page splitting ─────────────────────────────────────────────────────────────

def _split_pages(ocr_text: str) -> dict[int, str]:
    """
    Split OCR text into {page_number: page_content} dict.
    Handles the page delimiter format used by the OCR pipeline:
      ==============================
      PAGE N
      ==============================
    """
    pattern = re.compile(r'={20,}\s*\nPAGE\s+(\d+)\s*\n={20,}', re.IGNORECASE)
    splits  = list(pattern.finditer(ocr_text))

    if not splits:
        # No page markers — treat entire text as page 1
        return {1: ocr_text}

    pages = {}
    for i, match in enumerate(splits):
        page_num = int(match.group(1))
        start    = match.end()
        end      = splits[i + 1].start() if i + 1 < len(splits) else len(ocr_text)
        pages[page_num] = ocr_text[start:end].strip()

    return pages


def _build_page_summaries(pages: dict[int, str], max_chars: int = 350) -> str:
    """
    Build a compact summary of each page for the LLM.
    Detects tables by presence of │ characters.
    """
    lines = []
    for page_num in sorted(pages.keys()):
        content = pages[page_num]
        preview = content[:max_chars].replace("\n", " ").strip()

        # Heuristic: page has a table if it contains │ pipe chars or ─ borders
        has_table = (content.count("│") >= 3
                     or content.count("|") >= 6
                     or content.count("─") >= 10
                     or content.count("+") >= 4)
        tag = " [TABLE DETECTED]" if has_table else ""

        lines.append(f"[Page {page_num}]{tag} {preview}")

    return "\n".join(lines)


# ── Table detection helpers ────────────────────────────────────────────────────

def _detect_table_pages(pages: dict[int, str]) -> set[int]:
    """Return page numbers that contain ASCII table structures."""
    table_pages = set()
    for page_num, content in pages.items():
        if (content.count("│") >= 3
                or content.count("|") >= 6
                or content.count("─") >= 10):
            table_pages.add(page_num)
    return table_pages


# ── Dynamic surrounding paragraph extraction ──────────────────────────────────

def _extract_table_terms(table_text: str) -> set[str]:
    """
    Pull meaningful terms from the table content itself:
    - Codes like DLR#1.1, DLI#2, DLR#2.t, Section IV
    - Capitalized phrases (acronyms, entity names)
    - Words longer than 5 chars from row/col headers
    These drive the search into surrounding paragraphs.
    """
    terms = set()

    # Structured codes: DLR#1.1, DLI#2, Table 1, Section IV, etc.
    for code in re.findall(r'\b(?:DLR|DLI|Table|Section|Schedule|Annex|Exhibit|Article)\s*[#\.]?\s*[\dIVXA-Z]+[\d\.]*\b',
                           table_text, re.IGNORECASE):
        terms.add(code.strip())

    # Pipe-delimited cell content — extract col/row headers (text between │)
    cells = re.findall(r'│([^│\n]{4,60})│', table_text)
    for cell in cells:
        cell = cell.strip()
        # Skip cells that are purely numeric/currency
        if re.match(r'^[\d,\.\s€$£%]+$', cell):
            continue
        # Take meaningful multi-word phrases (≥ 3 chars each)
        words = [w for w in re.findall(r'\b[A-Za-z][a-zA-Z]{2,}\b', cell)]
        if len(words) >= 2:
            # Add the first meaningful 3-word phrase as a search term
            phrase = ' '.join(words[:3])
            terms.add(phrase)
        # Also add individual capitalized/acronym tokens
        for w in re.findall(r'\b[A-Z]{2,}\b', cell):
            terms.add(w)

    # Short meaningful tokens: EUR, MEF, TGR, etc.
    for acronym in re.findall(r'\b[A-Z]{2,5}\b', table_text):
        if acronym not in {'THE', 'AND', 'FOR', 'NOT', 'ARE', 'ITS'}:
            terms.add(acronym)

    return terms


def get_surrounding_paragraphs(ocr_text: str, pages: list[int],
                                context_pages: int = 1,
                                table_text: str = "") -> str:
    """
    Dynamically extract paragraph context around table pages.

    Two strategies combined:
    1. Term-driven search: extract key terms FROM the table (row/col labels,
       codes like DLR#1.1, acronyms like MEF/EUR/TGR), then search ALL
       non-table pages and score them by term overlap — returns the most
       relevant paragraphs regardless of page distance.
    2. Proximity fallback: if term-driven finds nothing, fall back to ±N pages.

    Args:
        ocr_text    : full OCR document text
        pages       : page numbers of the table
        context_pages: proximity window for fallback (default 1)
        table_text  : raw table text (enables term-driven search when provided)
    """
    all_pages   = _split_pages(ocr_text)
    table_set   = set(pages)
    para_pages  = {p: t for p, t in all_pages.items()
                   if p not in table_set
                   and t.count("│") < 3 and t.count("|") < 6}

    if not para_pages:
        return ""

    # ── Strategy 1: term-driven search ────────────────────────────────────────
    if table_text:
        terms = _extract_table_terms(table_text)

        scored: list[tuple[int, int, str]] = []  # (score, page_num, text)
        for page_num, text in para_pages.items():
            text_lower = text.lower()
            score = sum(
                1 for t in terms
                if t.lower() in text_lower
            )
            if score > 0:
                scored.append((score, page_num, text))

        scored.sort(key=lambda x: (-x[0], x[1]))  # highest score first, then page order

        if scored:
            # Return top 3 most relevant paragraph pages
            result_parts = [
                f"[Page {pnum} — relevance:{sc}]\n{txt}"
                for sc, pnum, txt in scored[:3]
            ]
            print(f"  [DocMap] Dynamic context: {len(scored)} para pages matched "
                  f"({len(terms)} table terms), using top {min(3, len(scored))}")
            return "\n\n".join(result_parts)

    # ── Strategy 2: proximity fallback ────────────────────────────────────────
    print(f"  [DocMap] Proximity fallback: ±{context_pages} pages from table p.{pages}")
    result_parts = []
    for p in pages:
        for neighbor in range(max(1, p - context_pages), p + context_pages + 1):
            if neighbor not in table_set and neighbor in para_pages:
                result_parts.append(f"[Page {neighbor}]\n{para_pages[neighbor]}")
    return "\n\n".join(result_parts)


def get_page_texts(ocr_text: str, pages: list[int]) -> str:
    """Extract and concatenate text from specified page numbers."""
    all_pages = _split_pages(ocr_text)
    parts = []
    for p in pages:
        if p in all_pages:
            parts.append(f"[Page {p}]\n{all_pages[p]}")
    return "\n\n".join(parts)


# ── Main function ──────────────────────────────────────────────────────────────

def build_document_map(ocr_text: str, client) -> dict:
    """
    Phase 1: Build a structural map of the document.

    Args:
        ocr_text : full OCR output text
        client   : LLMClient instance (document_map agent)

    Returns:
        {
            sections: [{topic, pages, type, keywords}],
            definitions_pages: [...],
            parties_pages: [...],
            total_pages: N,
            _page_index: {page_num: text}  (added locally, not from LLM)
        }
    """
    pages          = _split_pages(ocr_text)
    total_pages    = max(pages.keys()) if pages else 0
    table_pages    = _detect_table_pages(pages)
    page_summaries = _build_page_summaries(pages)

    print(f"  [DocMap] {total_pages} pages found, {len(table_pages)} contain tables")

    prompt = DOC_MAP_PROMPT.format(page_summaries=page_summaries)

    try:
        result = client.chat_json(prompt, max_tokens=2048)
    except Exception as e:
        print(f"  [DocMap] LLM failed ({e}) — building fallback map")
        result = _build_fallback_map(pages, table_pages, total_pages)

    if not isinstance(result, dict) or "sections" not in result:
        result = _build_fallback_map(pages, table_pages, total_pages)

    # Validate and fix pages lists
    result = _validate_map(result, total_pages)

    # Attach local page index (used by get_page_texts)
    result["_page_index"] = pages
    result["total_pages"] = total_pages

    _print_map_summary(result)
    return result


def _validate_map(doc_map: dict, total_pages: int) -> dict:
    """Ensure page numbers are valid integers within range."""
    valid = range(1, total_pages + 1)

    def clean_pages(pages_raw):
        if not isinstance(pages_raw, list):
            return []
        cleaned = []
        for p in pages_raw:
            try:
                n = int(p)
                if n in valid:
                    cleaned.append(n)
            except (ValueError, TypeError):
                pass
        return cleaned

    for section in doc_map.get("sections", []):
        section["pages"]    = clean_pages(section.get("pages", []))
        section["keywords"] = section.get("keywords", [])
        if section.get("type") not in ("table", "paragraph"):
            section["type"] = "paragraph"

    doc_map["definitions_pages"] = clean_pages(doc_map.get("definitions_pages", []))
    doc_map["parties_pages"]     = clean_pages(doc_map.get("parties_pages", []))
    return doc_map


def _build_fallback_map(pages: dict, table_pages: set, total_pages: int) -> dict:
    """
    Heuristic fallback when LLM call fails.
    Classifies each page as table or paragraph based on ASCII art detection.
    """
    sections = []
    current_type  = None
    current_pages = []

    for page_num in sorted(pages.keys()):
        page_type = "table" if page_num in table_pages else "paragraph"
        if page_type != current_type:
            if current_pages:
                sections.append({
                    "topic":    f"{'Table' if current_type == 'table' else 'Section'} (pages {current_pages[0]}-{current_pages[-1]})",
                    "pages":    current_pages[:],
                    "type":     current_type,
                    "keywords": [],
                })
            current_type  = page_type
            current_pages = [page_num]
        else:
            current_pages.append(page_num)

    if current_pages:
        sections.append({
            "topic":    f"{'Table' if current_type == 'table' else 'Section'} (pages {current_pages[0]}-{current_pages[-1]})",
            "pages":    current_pages[:],
            "type":     current_type,
            "keywords": [],
        })

    return {
        "sections":           sections,
        "definitions_pages":  [],
        "parties_pages":      [1] if 1 in pages else [],
        "total_pages":        total_pages,
    }


def _print_map_summary(doc_map: dict) -> None:
    print(f"  [DocMap] Document structure ({doc_map['total_pages']} pages):")
    for s in doc_map.get("sections", [])[:8]:  # show max 8
        kw = ", ".join(s.get("keywords", [])[:3])
        print(f"    [{s['type']:9s}] p.{s['pages']} — {s['topic'][:50]}  ({kw})")
    if doc_map.get("definitions_pages"):
        print(f"  [DocMap] Definitions: pages {doc_map['definitions_pages']}")


# ── Key routing: find best section for a key ──────────────────────────────────

def find_section_for_key(key_name: str, key_desc: str,
                          doc_map: dict) -> dict:
    """
    Match a key to the most relevant section in the document map.
    Uses keyword overlap + semantic heuristics (no LLM call).

    Returns the best matching section dict, or a fallback covering all pages.
    """
    query_tokens = set(
        re.findall(r'\b\w{3,}\b', f"{key_name} {key_desc}".lower())
    )

    best_score   = 0
    best_section = None

    for section in doc_map.get("sections", []):
        score = 0
        section_text = f"{section['topic']} {' '.join(section.get('keywords', []))}".lower()
        section_tokens = set(re.findall(r'\b\w{3,}\b', section_text))

        overlap = query_tokens & section_tokens
        score   = len(overlap)

        if score > best_score:
            best_score   = score
            best_section = section

    if best_section is None or best_score == 0:
        # Return fallback covering all pages
        all_pages = list(doc_map.get("_page_index", {}).keys())
        return {
            "topic":    "Full Document",
            "pages":    all_pages[:6],   # limit to first 6 pages
            "type":     "paragraph",
            "keywords": [],
        }

    return best_section
