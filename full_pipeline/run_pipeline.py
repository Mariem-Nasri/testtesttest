"""
run_pipeline.py [IMPROVED VERSION]
══════════════════════════════════
Entry point for the full 4-agent extraction pipeline.

IMPROVEMENTS:
  ✓ Fixed hardcoded path (now dynamic)
  ✓ Added input validation
  ✓ Added configuration constants
  ✓ Better error handling
  ✓ Magic numbers replaced with config

Usage:
    export GROQ_API_KEY='gsk_...'
    python run_pipeline.py --ocr full_report.txt --keys keys.json

    # Local phi3.5:
    python run_pipeline.py --ocr full_report.txt --keys keys.json --backend ollama

    # Use cached index (faster re-runs on same document):
    python run_pipeline.py --ocr full_report.txt --keys keys.json --use-cache
"""

import sys
import os
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core.llm_client    import build_agent_clients, model_summary
from utils.format_detector import detect_format, merge_format
from core.index_builder import DocumentIndex
from utils.timer        import StepTimer, fmt_time
from utils.display      import section, result_row, step_output

import agents.agent1_router     as agent1
import agents.agent2_table      as agent2
import agents.agent3_validator  as agent3
import agents.agent4_definition as agent4

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"


# =============================================================================
# PIPELINE CONFIGURATION
# =============================================================================

@dataclass(frozen=True)
class PipelineConfig:
    """Centralized configuration for the extraction pipeline."""
    
    # ── Agent 1: Embedding Router ─────────────────────────────────────────────
    EMBEDDING_CONFIDENCE_THRESHOLD = 0.82      # Skip Agent 2 if >= this
    ROUTER_LLM_FALLBACK_THRESHOLD = 0.45       # Use LLM if < this
    
    # ── Agent 3: Validator ─────────────────────────────────────────────────────
    SCORE_THRESHOLD_HIGH = 0.8                 # High confidence
    SCORE_THRESHOLD_MEDIUM = 0.6               # Medium confidence
    LLM_VALIDATION_THRESHOLD = 0.85             # Call LLM validator if score < this
    
    # ── Embedding validation ───────────────────────────────────────────────────
    RATIO_TOLERANCE = 0.01                     # Max difference for ratio values
    MAX_PAGES_FOR_LLM = 15                     # Max pages to summarize
    SUMMARY_CHARS_PER_PAGE = 300               # Characters per page summary
    
    # ── API & Retry Logic ──────────────────────────────────────────────────────
    MAX_RETRIES = 3                            # Max API retry attempts
    TIMEOUT_SECONDS = 60                       # API timeout
    RATE_LIMIT_WAIT_BASE = 30                  # Base wait time (seconds)
    
    # ── Paths ──────────────────────────────────────────────────────────────────
    OUTPUT_DIR = Path(__file__).parent / "outputs"
    CACHE_DIR = Path(__file__).parent / ".cache"

# Make it accessible globally
CONFIG = PipelineConfig()


# =============================================================================
# INPUT VALIDATION
# =============================================================================

def load_inputs(ocr_path: Path, keys_path: Path) -> tuple[str, list]:
    """
    Load and validate OCR text and keys JSON.
    
    Args:
        ocr_path: Path to OCR text file
        keys_path: Path to keys JSON file
    
    Returns:
        (ocr_text, keys_list)
    
    Raises:
        FileNotFoundError: If files don't exist
        ValueError: If files are invalid
        json.JSONDecodeError: If JSON is malformed
    """
    # ── Validate file existence ───────────────────────────────────────────────
    if not ocr_path.exists():
        raise FileNotFoundError(
            f"{RED}✗ OCR file not found:{RESET} {ocr_path.absolute()}\n"
            f"  Create it with: python extract_text.py"
        )
    
    if not keys_path.exists():
        raise FileNotFoundError(
            f"{RED}✗ Keys file not found:{RESET} {keys_path.absolute()}\n"
            f"  Check the path and try again."
        )
    
    # ── Load OCR text ──────────────────────────────────────────────────────────
    try:
        ocr_text = ocr_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(
            f"{RED}✗ Failed to read OCR file as UTF-8:{RESET}\n"
            f"  Error: {e}\n"
            f"  Try: file {ocr_path} (to check encoding)"
        )
    except Exception as e:
        raise ValueError(f"{RED}✗ Error reading OCR file:{RESET} {e}")
    
    if not ocr_text.strip():
        raise ValueError(
            f"{RED}✗ OCR file is empty:{RESET} {ocr_path}\n"
            f"  Expected: OCR text content"
        )
    
    # ── Load keys JSON ──────────────────────────────────────────────────────────
    try:
        keys_raw = keys_path.read_text(encoding="utf-8")
        keys_data = json.loads(keys_raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"{RED}✗ Invalid JSON in keys file:{RESET} {keys_path}\n"
            f"  Error: {e}\n"
            f"  Line {e.lineno}: {e.msg}\n"
            f"  Fix the JSON and try again"
        )
    except Exception as e:
        raise ValueError(f"{RED}✗ Error reading keys file:{RESET} {e}")
    
    # ── Extract keys list ──────────────────────────────────────────────────────
    if isinstance(keys_data, dict):
        if "keys" not in keys_data:
            raise ValueError(
                f"{RED}✗ Keys JSON is a dict but has no 'keys' field.{RESET}\n"
                f"  Expected: {{'keys': [...]}}\n"
                f"  Got: {list(keys_data.keys())}"
            )
        keys = keys_data["keys"]
    elif isinstance(keys_data, list):
        keys = keys_data
    else:
        raise ValueError(
            f"{RED}✗ Keys must be dict or list, got {type(keys_data).__name__}{RESET}\n"
            f"  Expected: {{'keys': [...]}} or [...]"
        )
    
    # ── Validate keys structure ────────────────────────────────────────────────
    if not keys:
        raise ValueError(f"{RED}✗ Keys list is empty. Nothing to extract.{RESET}")
    
    for i, key in enumerate(keys):
        if not isinstance(key, dict):
            raise ValueError(
                f"{RED}✗ Key #{i} is not a dict:{RESET} {key}\n"
                f"  All keys must be dictionaries"
            )
        if "keyName" not in key:
            raise ValueError(
                f"{RED}✗ Key #{i} missing required field 'keyName'.{RESET}\n"
                f"  Fields present: {list(key.keys())}\n"
                f"  Expected: {{'keyName': 'Your Key Name', ...}}"
            )
    
    # ── Auto-fill empty descriptions with sensible defaults ───────────────────
    # When the user uploads a keys.json with blank keyNameDescription fields,
    # the embedding query degrades to just the key name alone. These defaults
    # provide enough context for the agents to find the right snippet.
    _DEFAULT_DESCRIPTIONS = {
        "loan number":                        "Unique identifier assigned to this loan agreement, typically alphanumeric.",
        "agreement date":                     "The date on which this loan agreement was signed or became effective.",
        "program name":                       "Official name of the development program or project being financed, typically in the first 1-3 pages in the preamble, recitals, or WHEREAS clauses (e.g., 'Program for Results', 'Development Policy Loan', 'Catastrophe Deferred Drawdown Option'). Usually appears after phrases like 'the Borrower intends to carry out' or 'in support of'.",
        "borrower":                           "Name of the borrowing party — country, government entity, or institution — that receives the loan funds.",
        "lender":                             "Name of the lending institution or bank providing the loan funds.",
        "lender / bank":                      "Name of the lending institution or bank providing the loan funds.",
        "bank":                               "Name of the lending bank or financial institution providing the loan.",
        "borrower authorized representative - name": "Full name of the person authorized to sign on behalf of the Borrower (the country/government side). Found in the Borrower's signature block, NOT the Bank's signature block.",
        "borrower authorized representative - title": "Official title or position of the Borrower's authorized signatory (government minister or official). Found in the Borrower's signature block.",
        "bank authorized representative - name":     "Full name of the person authorized to sign on behalf of the Bank (the lending institution side, e.g., World Bank Country Director or Vice President). Found in the Bank's signature block, NOT the Borrower's signature block.",
        "bank authorized representative - title":    "Official title or position of the Bank's authorized signatory (e.g., Country Director, Regional Vice President). Found in the Bank's signature block, NOT the Borrower's signature block.",
        "loan amount":                        "Total principal amount of the loan in the agreed currency (e.g., EUR 386,200,000).",
        "loan currency":                      "ISO 4217 three-letter code of the loan principal denomination currency (e.g., EUR in 'EUR 386,200,000'). This is the principal denomination currency, NOT an interest rate benchmark. Extract only the 3-letter code.",
        "interest rate":                      "Applicable interest rate or spread on the loan principal.",
        "front-end fee":                      "One-time fee paid at loan effectiveness, expressed as a percentage of the loan amount.",
        "commitment charge":                  "Annual charge on the undisbursed loan balance, expressed as a percentage.",
        "maturity date":                      "Final repayment date of the loan principal.",
        "closing date":                       "Date after which no further withdrawals may be made from the loan account.",
        "effective date":                     "Date on which the loan agreement enters into force.",
        "payment dates":                      "Scheduled dates on which principal and/or interest payments are due.",
        "governing law":                      "Legal jurisdiction whose laws govern this agreement.",
        "program description":                "Brief description of the program or project being financed.",
    }
    for key in keys:
        desc = (key.get("keyNameDescription") or "").strip()
        if not desc:
            canonical = key["keyName"].lower().strip()
            key["keyNameDescription"] = _DEFAULT_DESCRIPTIONS.get(canonical, "")

    print(f"{GREEN}✓ Loaded {len(ocr_text):,} chars from {ocr_path.name}{RESET}")
    print(f"{GREEN}✓ Loaded {len(keys)} keys from {keys_path.name}{RESET}")

    return ocr_text, keys


# =============================================================================
# SINGLE KEY EXTRACTION
# =============================================================================

def extract_one(key_def: dict, index: DocumentIndex,
                ocr_text: str, clients: dict) -> dict:
    """
    Run all 4 agents for one key.

    Args:
        key_def  : {keyName, keyNameDescription, ...}
        index    : pre-built DocumentIndex
        ocr_text : full OCR text
        clients  : dict of LLMClient per agent
                   {"agent1", "agent2", "agent3", "agent4"}

    Returns:
        result dict with value, score, reason, _debug
    """
    key_name = key_def["keyName"]
    key_desc = key_def.get("keyNameDescription", "")
    timing   = {}
    llm_calls = 0

    # ── Agent 1 — Embedding Router ────────────────────────────────────────────
    # Primary: cosine similarity (no LLM, ~2ms)
    # Fallback: llama-4-scout when confidence < 0.45
    t0    = time.time()
    a1out = agent1.run(
        key_name        = key_name,
        key_description = key_desc,
        index           = index,
        client          = clients["agent1"],
        ocr_text        = ocr_text,
        thresholds      = {
            "HIGH_CONFIDENCE": CONFIG.EMBEDDING_CONFIDENCE_THRESHOLD,
            "VERY_LOW_CONF":   CONFIG.ROUTER_LLM_FALLBACK_THRESHOLD,
        },
    )
    timing["agent1_router"] = time.time() - t0
    if a1out.get("router_used_llm"):
        llm_calls += 1

    # ── Agent 4 — Definition Extractor ───────────────────────────────────────
    # Always runs — feeds definition + expected_format into Agent 3
    # Uses llama-4-scout (fast)
    t0    = time.time()
    a4out = agent4.run(
        key_name        = key_name,
        top_definitions = a1out["top_definitions"],
        client          = clients["agent4"],
    )
    timing["agent4_definition"] = time.time() - t0
    llm_calls += 1

    # ── Agent 2 — Table Specialist ────────────────────────────────────────────
    # Only called when Agent 1 confidence < threshold (configurable)
    # Uses llama-4-maverick (best accuracy for table reading)
    if a1out["needs_llm"]:
        t0    = time.time()
        a2out = agent2.run(
            key_name        = key_name,
            key_description = key_desc,
            top_cells       = a1out["top_cells"],
            client          = clients["agent2"],
        )
        timing["agent2_table"] = time.time() - t0
        llm_calls += 1

        extracted_value = a2out.get("value")
        row_label       = a2out.get("row_label")
        col_label       = a2out.get("column_label")

        # If Agent 2 returns null:
        #   1. Try value_hint from Agent 4 (for covenant keys)
        #   2. Fall back to top embedding match
        if extracted_value is None:
            if a4out.get("value_hint"):
                extracted_value = a4out["value_hint"]
                row_label       = "covenant"
                col_label       = "threshold"
                a1out["confidence"] = 0.90  # treat value_hint as high confidence
                print(f"  {GREEN}✓ Agent 2 null → using Agent 4 value_hint: {extracted_value}{RESET}")
            elif a1out["top_cells"]:
                extracted_value = a1out["top_cells"][0]["value"]
                row_label       = a1out["top_cells"][0]["row_label"]
                col_label       = a1out["top_cells"][0]["col_label"]
                print(f"  {YELLOW}⚠ Agent 2 null → using embedding fallback{RESET}")
    else:
        # High confidence: extract directly from embedding, skip Agent 2
        extracted_value = a1out["best_value"]
        row_label       = a1out["top_cells"][0]["row_label"] if a1out["top_cells"] else None
        col_label       = a1out["top_cells"][0]["col_label"] if a1out["top_cells"] else None
        timing["agent2_table"] = 0.0
        print(f"  {GREEN}✓ Agent 2 skipped (confidence={a1out['confidence']:.3f} ≥ {CONFIG.EMBEDDING_CONFIDENCE_THRESHOLD}){RESET}")

    # ── Agent 3 — Validator ───────────────────────────────────────────────────
    # Determine format: rule-based first, Agent 4 as fallback
    rule_format     = detect_format(key_name, key_desc)
    expected_format = merge_format(
        rule_based    = rule_format,
        agent4_format = a4out.get("expected_format", "text"),
        key_name      = key_name,
    )
    print(f"  Format: rule={rule_format}  agent4={a4out.get('expected_format','?')}  final={expected_format}")

    t0    = time.time()
    a3out = agent3.run(
        key_name        = key_name,
        value           = extracted_value,
        row_label       = row_label,
        col_label       = col_label,
        embedding_score = a1out["confidence"],
        expected_format = expected_format,
        definition_text = a4out.get("definition_text"),
        value_hint      = a4out.get("value_hint"),
        ocr_text        = ocr_text,
        page_hint       = a1out["page_hint"],
        client          = clients["agent3"],
    )
    timing["agent3_validator"] = time.time() - t0
    if a3out.get("score", 1.0) < CONFIG.LLM_VALIDATION_THRESHOLD:
        llm_calls += 1

    # ── Per-key timing display ────────────────────────────────────────────────
    section("Per-key timing")
    for agent_name, duration in timing.items():
        skipped = duration == 0.0
        color   = DIM if skipped else ""
        tag     = " (skipped)" if skipped else ""
        print(f"    {color}{agent_name:28s} {fmt_time(duration)}{tag}{RESET}")
    print(f"    {'llm_calls':28s} {llm_calls}")

    # Determine which agent was the primary extractor
    if timing.get("agent2_table", 0.0) > 0:
        agent_used = "agent2_table"
    elif a1out.get("router_used_llm"):
        agent_used = "agent1_router"
    else:
        agent_used = "agent1_router"

    return {
        "keyName":            key_name,
        "keyNameDescription": a4out.get("definition_text", key_desc),
        "page":               a1out["page_hint"],
        "value":              a3out.get("value"),
        "score":              a3out.get("score"),
        "reason":             a3out.get("reason"),
        "expected_format":    expected_format,
        "format_valid":       a3out.get("format_valid", True),
        "agent_used":         agent_used,
        "_debug": {
            "embedding_confidence": a1out["confidence"],
            "llm_calls":            llm_calls,
            "router_used_llm":      a1out.get("router_used_llm", False),
            "row_label":            row_label,
            "col_label":            col_label,
            "value_hint":           a4out.get("value_hint"),
            "timing":               timing,
        }
    }


# =============================================================================
# FULL PIPELINE
# =============================================================================

def run_pipeline(ocr_path: Path, keys_path: Path,
                 out_path: Path, backend: str,
                 model: str, use_cache: bool):

    timer = StepTimer(f"Financial Extraction Pipeline — {ocr_path.name}")

    # ── Load inputs ───────────────────────────────────────────────────────────
    timer.start("Loading inputs")
    try:
        ocr_text, keys = load_inputs(ocr_path, keys_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"\n{e}\n")
        sys.exit(1)
    timer.end(f"{len(ocr_text):,} chars  |  {len(keys)} keys")

    # ── LLM clients (one per agent, each with optimal model) ─────────────────
    timer.start("Initialising LLM clients", f"backend={backend}")
    try:
        model_summary(backend)
        clients = build_agent_clients(backend=backend)
    except RuntimeError as e:
        print(f"\n{RED}✗ LLM Client Error:{RESET}\n{e}\n")
        sys.exit(1)
    timer.end("4 clients ready")

    # ── Build / load embedding index ──────────────────────────────────────────
    cache_path = out_path.parent / f"{ocr_path.stem}_index.pkl"
    index      = DocumentIndex()

    if use_cache and cache_path.exists():
        timer.start("Loading cached index")
        try:
            index.load(str(cache_path))
            timer.end()
        except Exception as e:
            print(f"{YELLOW}⚠ Failed to load cache, rebuilding:{RESET} {e}")
            timer.start("Building embedding index")
            index.build(ocr_text, timer=timer)
            index.save(str(cache_path))
            timer.end(f"Cached → {cache_path}")
    else:
        timer.start("Building embedding index")
        index.build(ocr_text, timer=timer)
        index.save(str(cache_path))
        timer.end(f"Cached → {cache_path}")

    section("Index Summary")
    print(f"    Table snippets   : {len(index.table_snippets)}")
    print(f"    Definition snippets : {len(index.def_snippets)}")
    if index.table_vectors is not None:
        print(f"    Embedding dims   : {index.table_vectors.shape[1]}")

    # ── Extract each key ──────────────────────────────────────────────────────
    results         = []
    total_llm_calls = 0
    skipped_llm     = 0

    print(f"\n{'═'*65}")
    print(f"  {BOLD}EXTRACTING {len(keys)} KEYS{RESET}")
    print(f"{'═'*65}")

    for i, key_def in enumerate(keys):
        print(f"\n{'─'*65}")
        print(f"  {BOLD}KEY {i+1}/{len(keys)}:{RESET} {key_def['keyName']}")
        print(f"{'─'*65}")

        try:
            timer.start(f"Key {i+1}: {key_def['keyName'][:40]}")
            result = extract_one(key_def, index, ocr_text, clients)
            timer.end(f"value={result.get('value')!r}  score={result.get('score')}")

            results.append(result)
            total_llm_calls += result["_debug"]["llm_calls"]
            if result["_debug"]["llm_calls"] == 0:
                skipped_llm += 1
        except Exception as e:
            print(f"  {RED}✗ Error extracting key {key_def['keyName']}:{RESET} {e}")
            # Still add result but with error flag
            results.append({
                "keyName": key_def["keyName"],
                "value": None,
                "score": 0.0,
                "reason": f"Error: {str(e)[:100]}",
                "_debug": {"error": str(e)}
            })

    # ── Save results ──────────────────────────────────────────────────────────
    timer.start("Saving results")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    latest = out_path.parent / "results_latest.json"
    timed  = out_path.parent / f"results_{timestamp}.json"

    clean  = [{k: v for k, v in r.items() if k != "_debug"} for r in results]
    latest.write_text(json.dumps(clean,   indent=2, ensure_ascii=False))
    timed.write_text( json.dumps(results, indent=2, ensure_ascii=False))
    timer.end(f"→ {latest}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*65}")
    print(f"  {BOLD}RESULTS SUMMARY{RESET}")
    print(f"{'─'*65}")

    high   = sum(1 for r in results if (r.get("score") or 0) >= CONFIG.SCORE_THRESHOLD_HIGH)
    medium = sum(1 for r in results if CONFIG.SCORE_THRESHOLD_MEDIUM <= (r.get("score") or 0) < CONFIG.SCORE_THRESHOLD_HIGH)
    low    = sum(1 for r in results if (r.get("score") or 0) < CONFIG.SCORE_THRESHOLD_MEDIUM)

    for r in results:
        score = r.get("score") or 0
        result_row(r["keyName"], r["value"], score,
                   extra=f"fmt={r.get('expected_format','?')}")

    print(f"\n  {GREEN}High  (≥{CONFIG.SCORE_THRESHOLD_HIGH}){RESET}  : {high}/{len(results)}")
    print(f"  {YELLOW}Medium ({CONFIG.SCORE_THRESHOLD_MEDIUM}-{CONFIG.SCORE_THRESHOLD_HIGH}){RESET}: {medium}/{len(results)}")
    print(f"  {RED}Low   (<{CONFIG.SCORE_THRESHOLD_MEDIUM}){RESET}  : {low}/{len(results)}")
    print(f"\n  Total LLM calls  : {total_llm_calls}  "
          f"(avg {total_llm_calls/max(len(keys),1):.1f}/key)")
    print(f"  Keys no LLM      : {skipped_llm}/{len(keys)}")

    timer.summary()


# =============================================================================
# CLI
# =============================================================================

def main():
    # Compute dynamic default path
    DEFAULT_OUTPUT_PATH = CONFIG.OUTPUT_DIR / "results.json"
    
    parser = argparse.ArgumentParser(
        description="Financial extraction pipeline — embeddings + 4 agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Groq (recommended, free):
  export GROQ_API_KEY='gsk_...'
  python run_pipeline.py --ocr full_report.txt --keys keys.json

  # Local phi3.5 via Ollama:
  python run_pipeline.py --ocr full_report.txt --keys keys.json --backend ollama

  # Reuse cached index (faster on second run):
  python run_pipeline.py --ocr full_report.txt --keys keys.json --use-cache
        """
    )
    parser.add_argument("--ocr",       required=True, help="Path to OCR text file")
    parser.add_argument("--keys",      required=True, help="Path to keys JSON file")
    parser.add_argument("--out",       default=str(DEFAULT_OUTPUT_PATH),
                        help=f"Output path (default: {DEFAULT_OUTPUT_PATH})")
    parser.add_argument("--backend",   default="groq", choices=["groq", "ollama"],
                        help="LLM backend (default: groq)")
    parser.add_argument("--model",     default=None,
                        help="Override model for all agents")
    parser.add_argument("--use-cache", action="store_true",
                        help="Load pre-built index from disk")
    args = parser.parse_args()

    run_pipeline(
        ocr_path  = Path(args.ocr),
        keys_path = Path(args.keys),
        out_path  = Path(args.out),
        backend   = args.backend,
        model     = args.model,
        use_cache = args.use_cache,
    )


if __name__ == "__main__":
    main()