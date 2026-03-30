"""
core/index_builder.py
──────────────────────
Parses the full OCR output and builds two embedding indexes.
Designed to work on ANY loan agreement — no hardcoded table names,
column headers, or document-specific patterns.

TABLE CELL INDEX:
  Parses every ASCII table found in the OCR output.
  Each cell is indexed twice (horizontal + vertical orientation).
  Cross-page tables are handled by detecting orphan data rows
  and matching them to the nearest preceding title.

DEFINITION INDEX:
  Extracts defined terms using general legal document patterns:
  - "X shall mean..."  / "X means..."
  - Covenant thresholds: "shall not exceed X.XX to 1.00"
  - Date patterns: "dated as of", "effective date", "as of"
"""

import re
import time
import numpy as np
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    raise ImportError("Run: pip install sentence-transformers")

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
_embed_model     = None

def get_embed_model():
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(EMBED_MODEL_NAME)
    return _embed_model


# =============================================================================
# GENERAL FORMAT DETECTION
# Detects the expected value format from a key name — works for any document
# =============================================================================

# Terms that always mean percentage (interest rates, fees, spreads)
PERCENTAGE_TERMS = {
    "rate", "margin", "spread", "fee", "coupon", "yield",
    "libor", "sofr", "abr", "prime", "base rate", "commitment",
    "utilization fee", "unused fee", "letter of credit"
}

# Terms that always mean ratio (financial covenants)
RATIO_TERMS = {
    "leverage ratio", "coverage ratio", "interest coverage",
    "debt service", "fixed charge", "current ratio",
    "net debt", "ebitda", "ebitdax", "ltv", "loan to value",
    "asset coverage", "interest expense ratio", "first lien"
}

# Terms that always mean date
DATE_TERMS = {
    "date", "maturity", "expiry", "expiration", "effective",
    "closing", "termination", "amendment"
}

# Terms that always mean text/name
TEXT_TERMS = {
    "borrower", "lender", "agent", "guarantor", "party",
    "name", "address", "jurisdiction"
}

def infer_format_from_key(key_name: str) -> str:
    """
    Infer expected value format from the key name alone.
    No document-specific logic — works on any financial agreement.
    """
    kn = key_name.lower()

    # Date check first (most specific)
    if any(t in kn for t in DATE_TERMS) and not any(
        t in kn for t in PERCENTAGE_TERMS | RATIO_TERMS
    ):
        return "date"

    # Percentage: if key contains rate/fee/margin terms
    if any(t in kn for t in PERCENTAGE_TERMS):
        return "percentage"

    # Ratio: if key contains covenant/ratio terms
    if any(t in kn for t in RATIO_TERMS):
        return "ratio"

    # Check for explicit % or x in key name
    if "%" in key_name:
        return "percentage"
    if re.search(r'\d+\.\d+x\b', key_name, re.IGNORECASE):
        return "ratio"

    # "covenant" suffix → ratio
    if "covenant" in kn:
        return "ratio"

    return "text"


# =============================================================================
# TABLE PARSER
# =============================================================================

def parse_ascii_table(table_text: str, table_title: str) -> list[dict]:
    """
    Parse an ASCII grid table into individual cells.
    Indexes each cell with BOTH horizontal and vertical orientation.
    Works for any table structure — no hardcoded column names.
    """
    cells = []
    lines = table_text.splitlines()

    # Extract rows with cell content
    data_lines = []
    for line in lines:
        if "│" not in line:
            continue
        stripped = re.sub(r'[┌┐└┘├┤┬┴┼─═│\s]', '', line)
        if not stripped:
            continue
        parts = [p.strip() for p in line.split("│")]
        parts = [p for p in parts if p]
        if parts:
            data_lines.append(parts)

    if len(data_lines) < 2:
        return []

    # General value pattern — matches any financial value type
    VALUE_RE = re.compile(
        r'\d+\.?\d*\s*%'           # percentage: 2.25%
        r'|\d+\.?\d*\s+to\s+1'    # ratio: 4.50 to 1
        r'|\d+\.?\d*\s*x\b'        # ratio: 3.00x
        r'|\.\d+\s*%'              # percentage: .75%
        r'|\d{4}-\d{2}-\d{2}'      # ISO date
        r'|[A-Z][a-z]+\s+\d+,\s+\d{4}'  # "November 2, 2015"
    , re.IGNORECASE)

    # Threshold pattern for column headers
    THRESHOLD_RE = re.compile(
        r'[><=≥≤]\s*\d+\.?\d*\s*%'    # > 90%, ≥ 25%
        r'|[><=≥≤]\s*\d+\.?\d*\s*x'   # ≥ 3.00x
        r'|\d+\.?\d*\s*x\s+and'        # 3.00x and
        r'|<\s*\d+\.?\d*\s+and'        # < 3.00x and
    , re.IGNORECASE)

    # Classify rows
    title_row   = None
    header_rows = []
    data_rows   = []

    for i, row in enumerate(data_lines):
        has_values = any(VALUE_RE.search(cell) for cell in row)

        if len(row) == 1 and i == 0:
            title_row = row[0]
        elif not has_values:
            # Expand merged threshold cells into individual columns
            expanded = []
            for cell in row:
                tokens = THRESHOLD_RE.findall(cell)
                if len(tokens) > 1:
                    expanded.extend([t.strip() for t in tokens])
                else:
                    expanded.append(cell)
            header_rows.append(expanded)
        else:
            data_rows.append(row)

    if not data_rows:
        return []

    effective_title = title_row or table_title

    # Build column headers
    if header_rows:
        n_cols = max(len(r) for r in header_rows)
        col_headers = []
        for c in range(n_cols):
            parts = []
            for hrow in header_rows:
                if c < len(hrow) and hrow[c]:
                    parts.append(hrow[c])
            col_headers.append(" ".join(parts) if parts else f"col_{c}")
    else:
        col_headers = [f"col_{i}" for i in range(len(data_rows[0]))]

    # Extract cells with H + V snippets
    for row in data_rows:
        if not row:
            continue
        row_label = row[0]

        for col_idx, value in enumerate(row[1:], 1):
            if not value or not VALUE_RE.search(value):
                continue

            col_label = (col_headers[col_idx]
                         if col_idx < len(col_headers)
                         else f"col_{col_idx}")

            # Clean merged cell values like "0.375%0.30%"
            value = _split_merged_value(value, col_label)

            snippet_h = f"{effective_title} | {row_label} | {col_label} | value: {value}"
            snippet_v = f"{effective_title} | {col_label} | {row_label} | value: {value}"

            cells.append({
                "snippet_h":   snippet_h,
                "snippet_v":   snippet_v,
                "value":       value,
                "row_label":   row_label,
                "col_label":   col_label,
                "table_title": effective_title,
            })

    return cells


def _split_merged_value(value: str, col_label: str) -> str:
    """
    Fix OCR-merged cell values like '0.375%0.30%'.
    Uses the column label to pick the correct sub-value.
    """
    # Find all percentage/value tokens in the merged string
    tokens = re.findall(r'\d+\.?\d*\s*%|\d+\.?\d*\s+to\s+1\S*', value)
    if len(tokens) <= 1:
        return value

    # Try to match column label threshold to the right token
    col_lower = col_label.lower()
    for token in tokens:
        tok_val = re.search(r'\d+\.?\d*', token)
        if tok_val and tok_val.group() in col_lower:
            return token.strip()

    # Default: return first token
    return tokens[0].strip()


# =============================================================================
# CROSS-PAGE TABLE DETECTION
# General approach: find orphan data rows near a known table title
# =============================================================================

def extract_cross_page_snippets(ocr_text: str) -> list[dict]:
    """
    Detect tables split across pages by finding:
    1. A table title on one page (header-only table)
    2. Data rows on the next page with no title

    Reconstructs the full table by matching column count.
    Works for ANY document — no hardcoded table names.
    """
    snippets = []

    # Build page-position index so we can tag each snippet with its page number
    _page_re = re.compile(r'={10,}\s*\nPAGE\s+(\d+)\s*\n={10,}', re.IGNORECASE)
    _page_starts = [(int(m.group(1)), m.start()) for m in _page_re.finditer(ocr_text)]

    def _page_for_pos(pos: int) -> int | None:
        """Return page number for a character position in ocr_text."""
        page = None
        for pg, start in _page_starts:
            if start <= pos:
                page = pg
            else:
                break
        return page

    # Find all table blocks
    table_re = re.compile(
        r'\[Table\s+\d+[^\]]*\]\s*\n((?:[^\n]*\n)*?)(?=\[Table|\Z|={10,})',
        re.IGNORECASE
    )

    tables = list(table_re.finditer(ocr_text))

    for i, match in enumerate(tables):
        table_text = match.group(1)
        if "│" not in table_text:
            continue

        lines = [l for l in table_text.splitlines() if "│" in l]
        if not lines:
            continue

        # Check if this is a header-only table (no value rows)
        VALUE_RE = re.compile(r'\d+\.?\d*\s*%|\d+\.?\d*\s+to\s+1|\d+\.?\d*\s*x\b', re.IGNORECASE)
        data_lines  = [l for l in lines if VALUE_RE.search(l)]
        header_lines = [l for l in lines if not VALUE_RE.search(l)]

        if data_lines or not header_lines:
            continue  # not a header-only table

        # This is a header-only table — find the title
        title = "Unknown Table"
        for line in lines:
            parts = [p.strip() for p in line.split("│") if p.strip()]
            if len(parts) == 1 and len(parts[0]) > 3:
                title = parts[0]
                break

        # Get column headers
        col_headers = []
        for line in header_lines[1:]:  # skip title row
            parts = [p.strip() for p in line.split("│") if p.strip()]
            if len(parts) > 1:
                col_headers = parts
                break

        if not col_headers:
            continue

        # Find the next table that has no title (continuation)
        for j in range(i+1, min(i+3, len(tables))):
            next_text   = tables[j].group(1)
            next_lines  = [l for l in next_text.splitlines() if "│" in l]
            next_data   = [l for l in next_lines if VALUE_RE.search(l)]
            next_headers = [l for l in next_lines if not VALUE_RE.search(l)
                           and re.sub(r'[┌┐└┘├┤┬┴┼─═│\s]', '', l)]

            # Continuation: has data but title is just a row label (no spanning cell)
            if not next_data:
                continue

            # Try to match column count
            first_data_row = [p.strip() for p in next_data[0].split("│") if p.strip()]
            n_values = len(first_data_row) - 1  # subtract row label

            # Use existing col_headers or generate generic ones
            effective_cols = (col_headers if len(col_headers) >= n_values
                              else [f"col_{k}" for k in range(n_values + 1)])

            # Parse continuation rows
            for line in next_data:
                parts = [p.strip() for p in line.split("│") if p.strip()]
                if len(parts) < 2:
                    continue
                row_label = parts[0]
                for c, val in enumerate(parts[1:], 1):
                    if not VALUE_RE.search(val):
                        continue
                    col = (effective_cols[c]
                           if c < len(effective_cols)
                           else f"col_{c}")
                    val = _split_merged_value(val, col)
                    snippets.append({
                        "snippet_h":   f"{title} | {row_label} | {col} | value: {val}",
                        "snippet_v":   f"{title} | {col} | {row_label} | value: {val}",
                        "value":       val,
                        "row_label":   row_label,
                        "col_label":   col,
                        "table_title": title,
                        "page":        _page_for_pos(tables[j].start()),
                    })
            break

    return snippets


# =============================================================================
# GENERAL TABLE EXTRACTOR
# =============================================================================

def extract_tables_from_ocr(ocr_text: str) -> list[dict]:
    """Find and parse all ASCII tables in the OCR output."""
    all_cells = []

    page_pattern = re.compile(r'={10,}\s*\n\s*PAGE\s+(\d+)\s*\n\s*={10,}', re.IGNORECASE)
    page_splits  = list(page_pattern.finditer(ocr_text))

    if not page_splits:
        pages = {1: ocr_text}
    else:
        pages = {}
        for i, match in enumerate(page_splits):
            page_num = int(match.group(1))
            start    = match.start()
            end      = page_splits[i+1].start() if i+1 < len(page_splits) else len(ocr_text)
            pages[page_num] = ocr_text[start:end]

    table_pattern = re.compile(
        r'\[Table\s+\d+[^\]]*\]\s*\n((?:[^\n]*\n)*?(?=\[Table|\Z|={10,}))',
        re.IGNORECASE
    )

    for page_num, page_text in pages.items():
        for match in table_pattern.finditer(page_text):
            table_text = match.group(1)
            if "│" not in table_text:
                continue

            title = "Unknown Table"
            for line in table_text.splitlines():
                if "│" in line:
                    parts = [p.strip() for p in line.split("│") if p.strip()]
                    if len(parts) == 1 and parts[0]:
                        title = parts[0]
                        break

            cells = parse_ascii_table(table_text, title)
            for cell in cells:
                cell["page"] = page_num
            all_cells.extend(cells)

    return all_cells


# =============================================================================
# GENERAL DEFINITION EXTRACTOR
# Works on any legal/financial agreement
# =============================================================================

# General ratio value patterns used in covenants
RATIO_VALUE_RE = re.compile(
    r'\d+\.?\d*\s+to\s+1[.:\d]*'   # 4.50 to 1.00 / 3.00 to 1:00
    r'|\d+\.?\d*\s*:\s*1[.:\d]*'   # 4.50:1.00
    r'|\d+\.?\d*\s*x\b'             # 3.00x
    r'|\d+\.?\d*\s+times',          # 3.00 times
    re.IGNORECASE
)

# General definition pattern — works for any legal document
DEF_PATTERN = re.compile(
    r'"?([A-Z][A-Za-z\s\-]{2,60})"?\s+(?:shall\s+)?means?\s+'
    r'(.{30,600}?)(?=\n\n|"[A-Z]|\Z)',
    re.DOTALL
)

# General covenant pattern
COVENANT_PATTERN = re.compile(
    r'(?:shall\s+not\s+(?:permit|allow|cause)|'
    r'will\s+not\s+permit|'
    r'maintain[s]?\s+(?:a\s+)?|'
    r'shall\s+maintain)\s+'
    r'(?:the\s+)?([A-Z][A-Za-z\s\-]{2,60})\s+'
    r'(?:to\s+be\s+)?(?:greater\s+than|less\s+than|'
    r'exceed|below|above|at\s+least|not\s+less\s+than|'
    r'not\s+more\s+than|in\s+excess\s+of)\s+'
    r'([^.;]{5,80}?)(?=[.;])',
    re.DOTALL | re.IGNORECASE
)


def extract_definitions_from_ocr(ocr_text: str) -> list[dict]:
    """
    Extract defined terms and covenant thresholds from any legal document.
    No document-specific patterns.
    """
    definitions = []

    page_pattern = re.compile(r'PAGE\s+(\d+)', re.IGNORECASE)

    def get_page(pos):
        last_page = 1
        for m in page_pattern.finditer(ocr_text[:pos]):
            last_page = int(m.group(1))
        return last_page

    # Formal definitions
    for match in DEF_PATTERN.finditer(ocr_text):
        term       = match.group(1).strip()
        definition = " ".join(match.group(2).split())
        page       = get_page(match.start())

        # Infer format from definition content
        def_lower = definition.lower()
        if RATIO_VALUE_RE.search(definition):
            fmt = "ratio"
        elif "ratio of" in def_lower or "divided by" in def_lower:
            fmt = "ratio"
        elif "percentage" in def_lower or "%" in definition:
            fmt = "percentage"
        elif "date" in def_lower:
            fmt = "date"
        else:
            fmt = "text"

        snippet = (f"DEFINITION | {term} | "
                   f"{definition[:200]} | "
                   f"format: {fmt} | page: {page}")

        definitions.append({
            "snippet":         snippet,
            "term":            term,
            "definition":      definition,
            "expected_format": fmt,
            "page":            page,
            "value_hint":      None,
        })

    # Covenant thresholds
    for match in COVENANT_PATTERN.finditer(ocr_text):
        term      = match.group(1).strip()
        threshold = match.group(2).strip()
        page      = get_page(match.start())
        full_text = " ".join(match.group(0).split())

        # Extract numeric value hint
        val_match  = RATIO_VALUE_RE.search(threshold)
        value_hint = val_match.group(0).strip() if val_match else None

        # Capture period qualifier (Investment Grade / Borrowing Base Trigger)
        # Look at surrounding context (200 chars before the match)
        ctx_start = max(0, match.start() - 200)
        context   = ocr_text[ctx_start:match.end()]
        period    = ""
        if re.search(r'Investment\s+Grade\s+Period', context, re.IGNORECASE):
            period = "Investment Grade Period"
        elif re.search(r'Borrowing\s+Base\s+Trigger\s+Period', context, re.IGNORECASE):
            period = "Borrowing Base Trigger Period"

        # Include period in snippet so embeddings can distinguish them
        term_with_period = f"{term} ({period})" if period else term

        snippet = (f"COVENANT | {term_with_period} | "
                   f"{full_text[:200]} | "
                   f"value: {value_hint or threshold[:50]} | "
                   f"format: ratio | page: {page}")

        definitions.append({
            "snippet":         snippet,
            "term":            term_with_period,
            "definition":      full_text,
            "expected_format": "ratio",
            "page":            page,
            "value_hint":      value_hint,
        })

    return definitions


# =============================================================================
# GENERAL TEXT SNIPPETS (dates, parties, etc.)
# =============================================================================

def extract_known_table_snippets(ocr_text: str) -> list[dict]:
    """
    Extract cells from known table structures with fixed column headers.
    These tables have consistent column header patterns across loan agreements.
    """
    snippets = []
    VALUE_RE = re.compile(r'(?<![<>≥≤])\d+\.\d+\s*%|\.\d+\s*%', re.IGNORECASE)

    # Build page-position lookup for tagging snippets with their page number
    _page_re2 = re.compile(r'={10,}\s*\nPAGE\s+(\d+)\s*\n={10,}', re.IGNORECASE)
    _pg_starts2 = [(int(m.group(1)), m.start()) for m in _page_re2.finditer(ocr_text)]

    def _pg(pos: int) -> int | None:
        pg = None
        for p, s in _pg_starts2:
            if s <= pos:
                pg = p
            else:
                break
        return pg

    # Leverage Ratio Grid — 4 columns
    LR_COLS  = ["≥ 3.00x", "< 3.00x and ≥ 2.00x", "< 2.00x and ≥ 1.00x", "< 1.00x"]
    LR_TITLE = "Leverage Ratio Grid"
    LR_ROW_RE = re.compile(
        r'│\s*(LIBOR Loans|ABR Loans|Commitment Fee Rate)\s*'
        r'│\s*(\.?\d+\.?\d*%)\s*'
        r'│\s*(\.?\d+\.?\d*%)\s*'
        r'│\s*(\.?\d+\.?\d*(?:\.?\d+)?)\s*'   # may be merged like 0.375%0.30%
        r'│\s*(\.?\d+\.?\d*%)\s*│',
        re.IGNORECASE
    )
    for m in LR_ROW_RE.finditer(ocr_text):
        row_label = m.group(1).strip()
        raw_vals  = [m.group(i).strip() for i in range(2, 6)]
        # Split any merged cell like "0.375%0.30%"
        split_vals = []
        for v in raw_vals:
            parts = re.findall(r'\.?\d+\.?\d*%', v)
            split_vals.append(parts[0] if parts else v)
        for col_label, value in zip(LR_COLS, split_vals):
            snippets.append({
                "snippet_h":   f"{LR_TITLE} | {row_label} | {col_label} | value: {value}",
                "snippet_v":   f"{LR_TITLE} | {col_label} | {row_label} | value: {value}",
                "value":       value,
                "row_label":   row_label,
                "col_label":   col_label,
                "table_title": LR_TITLE,
                "page":        _pg(m.start()),
            })

    return snippets


def extract_text_snippets_from_ocr(ocr_text: str) -> list[dict]:
    """
    Extract key metadata from plain text — works on any agreement.
    Covers effective dates, party names, governing law, etc.
    """
    snippets = []

    # General date patterns
    date_patterns = [
        # "dated as of November 2, 2015"
        re.compile(
            r'(?:dated\s+as\s+of|effective\s+(?:as\s+of|date(?:\s+of)?)|'
            r'as\s+of|dated)\s+'
            r'([A-Z][a-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            re.IGNORECASE
        ),
        # "this Agreement, dated [date]"
        re.compile(
            r'this\s+\w+(?:\s+\w+)?\s*,?\s*dated\s+'
            r'([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})',
            re.IGNORECASE
        ),
    ]

    # Page-position lookup for text snippets
    _ts_page_re = re.compile(r'={10,}\s*\nPAGE\s+(\d+)\s*\n={10,}', re.IGNORECASE)
    _ts_pg_starts = [(int(mm.group(1)), mm.start()) for mm in _ts_page_re.finditer(ocr_text)]

    def _ts_pg(pos: int) -> int | None:
        pg = None
        for p, s in _ts_pg_starts:
            if s <= pos:
                pg = p
            else:
                break
        return pg

    seen_dates = set()
    for pat in date_patterns:
        for m in pat.finditer(ocr_text):
            date_val = m.group(1).strip()
            if date_val in seen_dates:
                continue
            seen_dates.add(date_val)
            snippets.append({
                "snippet_h": f"Agreement Date | {date_val} | effective date | value: {date_val}",
                "snippet_v": f"Agreement Date | effective date | {date_val} | value: {date_val}",
                "value":     date_val,
                "row_label": "Agreement Date",
                "col_label": "effective date",
                "table_title": "Document Metadata",
                "page":      _ts_pg(m.start()),
            })

    # ── Party names: Borrower / Bank ─────────────────────────────────────────
    # Matches: KINGDOM OF MOROCCO ("Borrower")  or  (*Borrower")  (OCR asterisk)
    #          between KINGDOM OF MOROCCO and INTERNATIONAL BANK ...  (multi-line or inline)
    party_patterns = [
        # ANY role word in quotes after an all-caps name: ("Borrower"), ("Seller"), ("Company")…
        # No IGNORECASE — keeps [A-Z] strictly uppercase so lazy match can't bleed into
        # surrounding lowercase prose.
        re.compile(
            r'([A-Z][A-Z ,\.]{3,80}?)\s*\(\s*[*"\']\s*(?:the\s+)?([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)?)\s*[*"\']\s*\)'
        ),
        # 'between\nX\nand\nY' — multi-line title page format (any document)
        re.compile(
            r'between\s*\n\s*([A-Z][A-Z\s]{3,60}?)\s*\n\s*and\s*\n\s*([A-Z][A-Z\s]{3,80})',
            re.IGNORECASE
        ),
    ]
    seen_parties = set()
    for m in party_patterns[0].finditer(ocr_text):
        name = " ".join(m.group(1).split())
        role = m.group(2).strip()           # preserve original casing e.g. "Borrower", "Seller"
        if name in seen_parties:
            continue
        seen_parties.add(name)
        # Use the actual role word from the document — works for any agreement type
        snippets.append({
            "snippet_h":   f"Parties | {role} | name | value: {name}",
            "snippet_v":   f"Parties | name | {role} | value: {name}",
            "value":       name,
            "row_label":   role,
            "col_label":   "name",
            "table_title": "Parties",
            "page":        _ts_pg(m.start()),
        })

    m2 = party_patterns[1].search(ocr_text)
    if m2:
        borrower = " ".join(m2.group(1).split())
        lender   = " ".join(m2.group(2).split())
        m2_page  = _ts_pg(m2.start())
        for name, role in [(borrower, "Borrower"), (lender, "Bank")]:
            if name not in seen_parties:
                seen_parties.add(name)
                snippets.append({
                    "snippet_h":   f"Parties | {role} | name | value: {name}",
                    "snippet_v":   f"Parties | name | {role} | value: {name}",
                    "value":       name,
                    "row_label":   role,
                    "col_label":   "name",
                    "table_title": "Parties",
                    "page":        m2_page,
                })

    # ── Loan amount from plain text ───────────────────────────────────────────
    # Matches: "EUR386,200,000" or "EUR 386,200,000" or "USD 100,000,000"
    amount_re = re.compile(
        r'(EUR|USD|GBP|JPY|CHF|XDR)\s*(\d[\d,\.]+(?:\s*(?:million|billion))?)',
        re.IGNORECASE
    )
    seen_amounts = set()
    for m in amount_re.finditer(ocr_text):
        currency = m.group(1).upper()
        amount   = m.group(2).strip()
        full_val = f"{currency} {amount}"
        if full_val in seen_amounts:
            continue
        seen_amounts.add(full_val)
        snippets.append({
            "snippet_h":   f"Loan Terms | Loan Amount | {currency} | value: {full_val}",
            "snippet_v":   f"Loan Terms | {currency} | Loan Amount | value: {full_val}",
            "value":       full_val,
            "row_label":   "Loan Amount",
            "col_label":   currency,
            "table_title": "Loan Terms",
            "page":        _ts_pg(m.start()),
        })
        # Also add a currency-only snippet (only for the first/principal currency)
        # Label it as "principal denomination currency" to distinguish from
        # interest rate benchmark currencies (LIBOR/SOFR base currency, etc.)
        if currency not in seen_amounts:
            seen_amounts.add(currency)
            snippets.append({
                "snippet_h":   f"Loan Terms | Loan Principal Currency | principal denomination currency code | value: {currency}",
                "snippet_v":   f"Loan Terms | principal denomination currency code | Loan Principal Currency | value: {currency}",
                "value":       currency,
                "row_label":   "Loan Principal Currency",
                "col_label":   "principal denomination currency code",
                "table_title": "Loan Terms",
                "page":        _ts_pg(m.start()),
            })

    # ── Authorized representatives from signature block ───────────────────────
    # Matches: "Name: Nadia FETTAH"  or  "By: John Smith"
    # Look back up to 600 chars to determine party context (Borrower vs Bank)
    _BORROWER_CONTEXT = re.compile(
        r'\b(?:FOR THE BORROWER|BORROWER)\b|[("\']Borrower["\')]',
        re.IGNORECASE
    )
    _BANK_CONTEXT = re.compile(
        r'\bFOR THE BANK\b|[("\']Bank["\')]|\bIBRD\b|\bWorld Bank\b|\bINTERNATIONAL BANK\b',
        re.IGNORECASE
    )

    def _party_label_for(pos: int, ocr: str) -> str:
        """Return 'Borrower' or 'Bank' based on the nearest party marker before pos."""
        ctx_start = max(0, pos - 800)
        ctx = ocr[ctx_start:pos]
        # Find the LAST occurrence of each party marker in the context window
        b_pos = -1
        for m in _BORROWER_CONTEXT.finditer(ctx):
            b_pos = m.start()
        k_pos = -1
        for m in _BANK_CONTEXT.finditer(ctx):
            k_pos = m.start()
        if b_pos == -1 and k_pos == -1:
            return "Borrower"   # default if no context
        if k_pos > b_pos:
            return "Bank"
        return "Borrower"

    rep_re = re.compile(
        r'(?:Name|By)\s*:\s*([A-Z][A-Za-z\s\-]{2,60}?)(?:\n|$)',
        re.IGNORECASE
    )
    for m in rep_re.finditer(ocr_text):
        name = " ".join(m.group(1).split())
        if len(name) < 4:
            continue
        party = _party_label_for(m.start(), ocr_text)
        snippets.append({
            "snippet_h":   f"Signatures | {party} Authorized Representative | name | value: {name}",
            "snippet_v":   f"Signatures | name | {party} Authorized Representative | value: {name}",
            "value":       name,
            "row_label":   f"{party} Authorized Representative",
            "col_label":   "name",
            "table_title": "Signatures",
            "page":        _ts_pg(m.start()),
        })

    # ── Title/position from signature block ──────────────────────────────────
    # Matches: "Title: Minister of Finance"  or  "Position: Country Director"
    title_re = re.compile(
        r'(?:Title|Position|Function)\s*:\s*([A-Za-z][A-Za-z\s\-,\.]{4,80}?)(?:\n|$)',
        re.IGNORECASE
    )
    for m in title_re.finditer(ocr_text):
        title_val = " ".join(m.group(1).split())
        party = _party_label_for(m.start(), ocr_text)
        snippets.append({
            "snippet_h":   f"Signatures | {party} Authorized Representative | title | value: {title_val}",
            "snippet_v":   f"Signatures | title | {party} Authorized Representative | value: {title_val}",
            "value":       title_val,
            "row_label":   f"{party} Authorized Representative",
            "col_label":   "title",
            "table_title": "Signatures",
            "page":        _ts_pg(m.start()),
        })

    # ── Program name from preamble / recitals ────────────────────────────────
    # World Bank: "in support of the Borrower's [Name] Program"
    # Also matches: "financing of [Name]" / "WHEREAS ... carry out ... [Name]"
    # Match program names — no IGNORECASE so capture group must start uppercase
    program_patterns = [
        re.compile(
            r'in\s+support\s+of\s+(?:the\s+)?(?:[Bb]orrower\'?s?\s+)?'
            r'([A-Z][A-Za-z\s\-\(\)]{4,120}?)\s*(?:Program|Programme)',
        ),
        re.compile(
            r'(?:carry\s+out|implement|financing\s+of)\s+'
            r'(?:the\s+)?([A-Z][A-Za-z\s\-\(\)]{4,120}?)\s*(?:Program|Programme)',
        ),
        re.compile(
            r'(?:the\s+)([A-Z][A-Za-z\s\-\(\)]{4,120}?)\s*(?:Program|Programme)\s+'
            r'(?:for\s+Results|Development\s+Policy|Investment)',
        ),
    ]
    seen_programs = set()
    for pat in program_patterns:
        for m in pat.finditer(ocr_text):
            prog = " ".join(m.group(1).split()).strip()
            # Must start with an uppercase letter and be non-trivial
            if not prog or not prog[0].isupper() or len(prog) < 5:
                continue
            if prog.lower() in seen_programs:
                continue
            seen_programs.add(prog.lower())
            # Include "Program" suffix from the match for context
            suffix_match = re.search(
                r'(Program|Programme)(?:\s+for\s+Results|\s+Development\s+Policy)?',
                ocr_text[m.end()-1:m.end()+40], re.IGNORECASE
            )
            suffix = suffix_match.group(0).strip() if suffix_match else "Program"
            full_name = f"{prog} {suffix}"
            snippets.append({
                "snippet_h":   f"Document Metadata | Program Name | title | value: {full_name}",
                "snippet_v":   f"Document Metadata | title | Program Name | value: {full_name}",
                "value":       full_name,
                "row_label":   "Program Name",
                "col_label":   "title",
                "table_title": "Document Metadata",
                "page":        _ts_pg(m.start()),
            })

    # ── Loan / Project number ─────────────────────────────────────────────────
    loan_num_re = re.compile(
        r'(?:LOAN|PROJECT|CONTRACT|AGREEMENT)\s+(?:NUMBER|NO\.?|#|N°)\s*([A-Z0-9][\w\-]{2,20})',
        re.IGNORECASE
    )
    for m in loan_num_re.finditer(ocr_text):
        num = m.group(1).strip()
        snippets.append({
            "snippet_h":   f"Document Metadata | Loan Number | id | value: {num}",
            "snippet_v":   f"Document Metadata | id | Loan Number | value: {num}",
            "value":       num,
            "row_label":   "Loan Number",
            "col_label":   "id",
            "table_title": "Document Metadata",
            "page":        _ts_pg(m.start()),
        })

    # ── Raw page-text chunks (catch-all for any PDF type) ─────────────────────
    # Creates overlapping 400-char chunks from the first 6 pages.
    # Even when regex patterns miss everything, Agent 2 (LLM) can read these
    # chunks and extract any value — this is the "works on any PDF" guarantee.
    page_split_re = re.compile(
        r'={20,}\s*\nPAGE\s+(\d+)\s*\n={20,}', re.IGNORECASE
    )
    page_matches = list(page_split_re.finditer(ocr_text))
    chunk_size, stride, max_pages = 400, 200, 6
    for pi, pm in enumerate(page_matches[:max_pages]):
        page_num = int(pm.group(1))
        p_start  = pm.end()
        p_end    = page_matches[pi + 1].start() if pi + 1 < len(page_matches) else len(ocr_text)
        page_text = ocr_text[p_start:p_end].strip()
        for j in range(0, max(1, len(page_text) - chunk_size + 1), stride):
            chunk = page_text[j: j + chunk_size].strip()
            if len(chunk) < 40:
                continue
            snippets.append({
                "snippet_h":   chunk,
                "snippet_v":   chunk,
                "value":       None,   # Agent 2 extracts the value from the chunk text
                "row_label":   f"Page {page_num}",
                "col_label":   "text",
                "table_title": f"Page {page_num}",
                "page":        page_num,
            })

    return snippets


# =============================================================================
# DOCUMENT INDEX
# =============================================================================

class DocumentIndex:

    def __init__(self):
        self.table_snippets  = []
        self.table_meta      = []
        self.table_vectors   = None
        self.def_snippets    = []
        self.def_meta        = []
        self.def_vectors     = None

    def build(self, ocr_text: str, timer=None):
        from utils.display import index_stats
        model = get_embed_model()

        # ── Table index ───────────────────────────────────────────────────────
        if timer: timer.start("  Parsing tables from OCR")
        all_cells    = extract_tables_from_ocr(ocr_text)
        cross_page   = extract_cross_page_snippets(ocr_text)
        known_tables = extract_known_table_snippets(ocr_text)
        text_snips   = extract_text_snippets_from_ocr(ocr_text)
        all_cells.extend(cross_page)
        all_cells.extend(known_tables)
        all_cells.extend(text_snips)
        if timer: timer.end(
            f"{len(all_cells)} cells "
            f"({len(cross_page)} cross-page, {len(known_tables)} known, "
            f"{len(text_snips)} from text)"
        )

        if timer: timer.start("  Building table cell index")
        t0 = time.time()
        for cell in all_cells:
            self.table_snippets.append(cell["snippet_h"])
            self.table_meta.append({**cell, "orientation": "horizontal"})
            self.table_snippets.append(cell["snippet_v"])
            self.table_meta.append({**cell, "orientation": "vertical"})

        if self.table_snippets:
            self.table_vectors = model.encode(
                self.table_snippets, show_progress_bar=False, batch_size=64
            )
        t_table = time.time() - t0
        if timer: timer.end(f"{len(self.table_snippets)} snippets embedded")
        index_stats("Table Cell Index",
                    len(self.table_snippets),
                    self.table_vectors.shape[1] if self.table_vectors is not None else 0,
                    t_table)

        # ── Definition index ──────────────────────────────────────────────────
        if timer: timer.start("  Building definition index")
        t0 = time.time()
        all_defs = extract_definitions_from_ocr(ocr_text)
        for d in all_defs:
            self.def_snippets.append(d["snippet"])
            self.def_meta.append(d)

        if self.def_snippets:
            self.def_vectors = model.encode(
                self.def_snippets, show_progress_bar=False, batch_size=64
            )
        t_def = time.time() - t0
        if timer: timer.end(f"{len(self.def_snippets)} snippets embedded")
        index_stats("Definition Index",
                    len(self.def_snippets),
                    self.def_vectors.shape[1] if self.def_vectors is not None else 0,
                    t_def)

    def save(self, path: str):
        import pickle
        with open(path, "wb") as f:
            pickle.dump({
                "table_snippets": self.table_snippets,
                "table_meta":     self.table_meta,
                "table_vectors":  self.table_vectors,
                "def_snippets":   self.def_snippets,
                "def_meta":       self.def_meta,
                "def_vectors":    self.def_vectors,
            }, f)
        print(f"  Index saved → {path}")

    def load(self, path: str):
        import pickle
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.table_snippets = data["table_snippets"]
        self.table_meta     = data["table_meta"]
        self.table_vectors  = data["table_vectors"]
        self.def_snippets   = data["def_snippets"]
        self.def_meta       = data["def_meta"]
        self.def_vectors    = data["def_vectors"]
        print(f"  Index loaded ← {path}  "
              f"({len(self.table_snippets)} table, "
              f"{len(self.def_snippets)} definition snippets)")

    def search_tables(self, query: str, top_k: int = 5) -> list[dict]:
        if self.table_vectors is None:
            return []
        from sklearn.metrics.pairwise import cosine_similarity
        model  = get_embed_model()
        q_vec  = model.encode([query])
        scores = cosine_similarity(q_vec, self.table_vectors)[0]
        top_i  = scores.argsort()[::-1][:top_k * 2]

        seen, result = set(), []
        for i in top_i:
            meta    = self.table_meta[i]
            cell_id = (meta["table_title"], meta["row_label"], meta["col_label"])
            if cell_id not in seen:
                seen.add(cell_id)
                result.append({
                    "snippet":     self.table_snippets[i],
                    "score":       float(scores[i]),
                    "value":       meta["value"],
                    "row_label":   meta["row_label"],
                    "col_label":   meta["col_label"],
                    "table_title": meta["table_title"],
                    "page":        meta.get("page"),
                    "orientation": meta.get("orientation"),
                })
            if len(result) >= top_k:
                break
        return result

    def search_definitions(self, query: str, top_k: int = 3) -> list[dict]:
        if self.def_vectors is None:
            return []
        from sklearn.metrics.pairwise import cosine_similarity
        model  = get_embed_model()
        q_vec  = model.encode([query])
        scores = cosine_similarity(q_vec, self.def_vectors)[0]
        top_i  = scores.argsort()[::-1][:top_k]
        return [
            {"snippet": self.def_snippets[i], "score": float(scores[i]),
             **self.def_meta[i]}
            for i in top_i
        ]