"""
run_pipeline.py — 3-Phase Multi-Agent Pipeline with integrated GLM-OCR
═══════════════════════════════════════════════════════════════════════
Architecture:

  [OCR Phase — optional]   PDF → GLM-OCR (Ollama VLM) or Tesseract → text
  Phase 1: Document Map   (1 LLM call, shared across all keys)
           → Identifies WHERE each topic is + TABLE or PARAGRAPH
  Phase 2: Per-key parallel extraction (6 workers)
           type="table"  → Tables Agent → Rules Sub-Agent
           type="paragraph" → Doc-Type Sub-Agent (Terms Agent if needed)
           Always parallel: Description Agent
  Phase 3: Validator (format check first, LLM only when needed)

Usage:
  # PDF → OCR → extract (fully integrated):
  python run_pipeline.py --pdf document.pdf --keys keys.json --backend ollama

  # Pre-OCR'd text → extract:
  python run_pipeline.py --ocr full_report.txt --keys keys.json --backend ollama

  # Cloud (Groq, free tier):
  export GROQ_API_KEY='gsk_...'
  python run_pipeline.py --pdf document.pdf --keys keys.json

  # With role/doc-type (multi-role mode):
  python run_pipeline.py --pdf document.pdf --keys keys.json \\
    --doc-type loan --role banking

  # Tesseract OCR (fast, CPU):
  python run_pipeline.py --pdf document.pdf --keys keys.json \\
    --ocr-engine tesseract --ocr-workers 4
"""

import sys
import os
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# ── GLM-OCR runner (lives one level up) ─────────────────────────────────────
_RUNNER_DIR = os.path.dirname(ROOT)
if _RUNNER_DIR not in sys.path:
    sys.path.insert(0, _RUNNER_DIR)

from core.llm_client import build_agent_clients, model_summary
from utils.format_detector import detect_format
from utils.timer import StepTimer, fmt_time
from utils.display import section, result_row

import agents.agent_document_map   as doc_map_agent
import agents.agent_tables         as tables_agent
import agents.agent_rules_extractor as rules_agent
import agents.agent_terms_extractor as terms_agent
import agents.agent_description    as description_agent
import agents.agent_validator      as validator_agent
import agents.agent5_keyword       as keyword_agent

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

# ── Config ────────────────────────────────────────────────────────────────────
SCORE_HIGH   = 0.8
SCORE_MEDIUM = 0.6
OUTPUT_DIR   = Path(__file__).parent / "outputs"


# =============================================================================
# OCR PHASE  (PDF → clean text via GLM-OCR or Tesseract)
# =============================================================================

def run_ocr_on_pdf(
    pdf_path: Path,
    ocr_engine: str = "glm",
    ocr_workers: int | None = None,
    dpi: int | None = None,
    use_cache: bool = True,
    out_dir: Path | None = None,
) -> tuple[Path, str]:
    """
    Run GLM-OCR (or Tesseract) on *pdf_path* and return
    ``(ocr_txt_path, ocr_text)`` ready to feed into the pipeline.

    The result is written next to the PDF (or into *out_dir*) as
    ``<stem>.<engine>.txt``.  Subsequent runs with the same PDF reuse
    the cached per-page results so OCR is not repeated unnecessarily.
    """
    try:
        from glmocr_runner import process_pdf, ollama_running, model_available
    except ImportError as e:
        raise ImportError(
            "glmocr_runner.py not found. Make sure it lives in the project root "
            f"({_RUNNER_DIR}).\nOriginal error: {e}"
        )

    out_dir = out_dir or pdf_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    ocr_txt_path = out_dir / f"{pdf_path.stem}.{ocr_engine}.txt"

    # Engine defaults
    _workers = ocr_workers if ocr_workers is not None else (4 if ocr_engine == "tesseract" else 2)
    _dpi     = dpi         if dpi         is not None else (150 if ocr_engine == "tesseract" else 120)

    if ocr_engine == "glm":
        if not ollama_running():
            raise RuntimeError(
                "Ollama is not running. Start it with:  ollama serve\n"
                "Then pull the model:  ollama pull glm-ocr"
            )
        if not model_available("glm-ocr"):
            raise RuntimeError(
                "Model 'glm-ocr' not found in Ollama.\n"
                "Pull it with:  ollama pull glm-ocr"
            )

    print(f"\n{BOLD}{'═'*65}{RESET}")
    print(f"  {BOLD}OCR PHASE  [{ocr_engine.upper()}]  {pdf_path.name}{RESET}")
    print(f"{'─'*65}")
    print(f"  DPI={_dpi}  workers={_workers}  cache={'on' if use_cache else 'off'}")

    text = process_pdf(
        pdf_path     = str(pdf_path),
        out_path     = ocr_txt_path,
        engine       = ocr_engine,
        dpi          = _dpi,
        workers      = _workers,
        use_cache    = use_cache,
        batch_size   = 4,
        jpeg_quality = 85,
    )

    print(f"  {GREEN}✓ OCR complete → {ocr_txt_path}  ({len(text):,} chars){RESET}")
    return ocr_txt_path, text


# =============================================================================
# INPUT LOADING
# =============================================================================

def load_inputs(ocr_path: Path, keys_path: Path) -> tuple[str, list]:
    """Load OCR text and keys JSON, validate both."""
    if not ocr_path.exists():
        raise FileNotFoundError(f"OCR file not found: {ocr_path}")
    if not keys_path.exists():
        raise FileNotFoundError(f"Keys file not found: {keys_path}")

    ocr_text  = ocr_path.read_text(encoding="utf-8")
    keys_raw  = keys_path.read_text(encoding="utf-8")
    keys_data = json.loads(keys_raw)

    if isinstance(keys_data, dict):
        keys = keys_data.get("keys", [])
    elif isinstance(keys_data, list):
        keys = keys_data
    else:
        raise ValueError("Keys must be a list or {keys: [...]}")

    if not keys:
        raise ValueError("Keys list is empty")

    # Normalize optional fields
    for key in keys:
        key.setdefault("keyNameDescription", "")
        key.setdefault("searchType", "")
        key.setdefault("expectedFormat", "")

    print(f"{GREEN}✓ Loaded {len(ocr_text):,} chars | {len(keys)} keys{RESET}")
    return ocr_text, keys


# =============================================================================
# SINGLE KEY EXTRACTION
# =============================================================================

def extract_one(key_def: dict,
                doc_map: dict,
                ocr_text: str,
                clients: dict,
                doc_type: str = "loan") -> dict:
    """
    Run the full agent pipeline for one key.

    Args:
        key_def  : {keyName, keyNameDescription, searchType, expectedFormat}
        doc_map  : output from Phase 1 Document Map
        ocr_text : full OCR text
        clients  : {doc_map, tables, rules, terms, description, validator, keyword}
        doc_type : "loan", "isda", "invoice", "compliance_report"

    Returns:
        result dict with value, score, reason, page, description, rule_context, found_in
    """
    key_name  = key_def["keyName"]
    key_desc  = key_def.get("keyNameDescription", "")
    timing    = {}
    llm_calls = 0

    # ── Keyword-only search (explicit) ────────────────────────────────────────
    if key_def.get("searchType", "").strip().lower() == "keyword":
        t0     = time.time()
        a5out  = keyword_agent.run(key_name, key_desc, ocr_text, client=None)
        timing["keyword_search"] = time.time() - t0
        return {
            "keyName":            key_name,
            "keyNameDescription": key_desc,
            "page":               ", ".join(str(m["page"]) for m in a5out["matches"]),
            "value":              a5out["value"],
            "score":              1.0 if a5out["count"] > 0 else 0.0,
            "reason":             f"Found {a5out['count']} occurrences",
            "description":        "",
            "rule_context":       None,
            "found_in":           "keyword_search",
            "_debug":             {"timing": timing, "llm_calls": 0},
        }

    # ── Determine expected format ─────────────────────────────────────────────
    rule_format     = detect_format(key_name, key_desc)
    expected_format = key_def.get("expectedFormat") or rule_format or "text"

    # ── Find relevant section from Document Map ───────────────────────────────
    section_info = doc_map_agent.find_section_for_key(key_name, key_desc, doc_map)
    relevant_pages = section_info.get("pages", [])
    content_type   = section_info.get("type", "paragraph")

    print(f"  Route: '{section_info['topic'][:40]}' p.{relevant_pages} → {content_type}")

    page_text = doc_map_agent.get_page_texts(ocr_text, relevant_pages)

    # ── Description Agent (always runs, parallel) ─────────────────────────────
    t_desc_start = time.time()
    def _run_description():
        return description_agent.run(
            key_name          = key_name,
            ocr_text          = ocr_text,
            definitions_pages = doc_map.get("definitions_pages", []),
            client            = clients["description"],
        )

    # ── Extraction branch ─────────────────────────────────────────────────────
    value_result   = {}
    rule_context   = None
    found_in       = "not_found"
    extraction_page = None

    with ThreadPoolExecutor(max_workers=2) as ex:
        # Start description agent in parallel
        desc_future = ex.submit(_run_description)

        t0 = time.time()

        if content_type == "table":
            # ── Table path: Tables Agent → Rules Sub-Agent ────────────────────
            table_result = tables_agent.run(
                key_name   = key_name,
                key_desc   = key_desc,
                page_texts = page_text,
                client     = clients["tables"],
            )
            timing["tables_agent"] = time.time() - t0
            llm_calls += 1

            if table_result.get("value") is not None:
                found_in = "table"
                extraction_page = table_result.get("page")

                # Always run Rules Sub-Agent to add rule context
                # Pass table_text so surrounding search is term-driven
                surrounding = doc_map_agent.get_surrounding_paragraphs(
                    ocr_text, relevant_pages,
                    context_pages=1,
                    table_text=page_text,
                )
                t_rules = time.time()
                rules_result = rules_agent.run(
                    key_name         = key_name,
                    key_desc         = key_desc,
                    table_result     = table_result,
                    surrounding_text = surrounding,
                    client           = clients["rules"],
                    doc_type         = doc_type,
                )
                timing["rules_agent"] = time.time() - t_rules
                llm_calls += 1

                value_result = rules_result
                rule_context = rules_result.get("rule_context")
            else:
                # Table agent found nothing → fallback to paragraph
                # Include adjacent pages (cross-page table headers live there)
                print(f"  {YELLOW}⚠ Table agent null → fallback to paragraph{RESET}")
                surrounding = doc_map_agent.get_surrounding_paragraphs(
                    ocr_text, relevant_pages,
                    context_pages=2,
                    table_text=page_text,
                )
                fallback_text = (surrounding + "\n\n" + page_text) if surrounding else page_text
                t_terms = time.time()
                value_result = terms_agent.run(
                    key_name  = key_name,
                    key_desc  = key_desc,
                    page_text = fallback_text,
                    client    = clients["terms"],
                    doc_type  = doc_type,
                )
                timing["terms_fallback"] = time.time() - t_terms
                llm_calls += 1
                found_in = value_result.get("found_in", "not_found")
                extraction_page = value_result.get("page")

        else:
            # ── Paragraph path: Doc-Type Sub-Agent (Terms Agent) ──────────────
            t_terms = time.time()
            value_result = terms_agent.run(
                key_name  = key_name,
                key_desc  = key_desc,
                page_text = page_text,
                client    = clients["terms"],
                doc_type  = doc_type,
            )
            timing["terms_agent"] = time.time() - t_terms
            llm_calls += 1
            found_in        = value_result.get("found_in", "not_found")
            extraction_page = value_result.get("page")

            # If nothing found in primary pages, extend search to nearby pages
            if value_result.get("value") is None:
                all_pages = list(doc_map.get("_page_index", {}).keys())
                broader_pages = [p for p in all_pages if p not in relevant_pages][:4]
                if broader_pages:
                    print(f"  {YELLOW}⚠ Not found in p.{relevant_pages} → trying p.{broader_pages}{RESET}")
                    broader_text = doc_map_agent.get_page_texts(ocr_text, broader_pages)
                    t_broad = time.time()
                    broad_result = terms_agent.run(
                        key_name  = key_name,
                        key_desc  = key_desc,
                        page_text = broader_text,
                        client    = clients["terms"],
                        doc_type  = doc_type,
                    )
                    timing["terms_broader"] = time.time() - t_broad
                    llm_calls += 1
                    if broad_result.get("value") is not None:
                        value_result    = broad_result
                        found_in        = broad_result.get("found_in", "paragraph")
                        extraction_page = broad_result.get("page")

        # Wait for description agent
        try:
            desc_result = desc_future.result(timeout=30)
        except Exception as e:
            print(f"  {YELLOW}⚠ Description agent failed: {e}{RESET}")
            desc_result = {"definition_text": "", "source_page": None}
        timing["description_agent"] = time.time() - t_desc_start
        llm_calls += 1

    # ── Phase 3: Validator ────────────────────────────────────────────────────
    extracted_value = value_result.get("value")
    raw_confidence  = _confidence_from_result(value_result)

    # Give the validator all relevant text + a window of the full doc for rescue scans
    all_section_pages = doc_map_agent.get_page_texts(ocr_text, relevant_pages)
    # Include first 3000 chars of full OCR so metadata embedded in page headers
    # (e.g. currency in column headers on cross-page tables) is always reachable
    full_doc_prefix = ocr_text[:3000]
    validator_context = ((all_section_pages or page_text) + "\n\n" + full_doc_prefix)[:6000]

    t0 = time.time()
    validated = validator_agent.run(
        key_name        = key_name,
        value           = extracted_value,
        expected_format = expected_format,
        definition_text = desc_result.get("definition_text", ""),
        page_text       = validator_context,
        client          = clients["validator"],
        confidence      = raw_confidence,
    )
    timing["validator"] = time.time() - t0
    if validated.get("score", 1.0) < 0.7:
        llm_calls += 1

    # ── Build result ──────────────────────────────────────────────────────────
    return {
        "keyName":            key_name,
        "keyNameDescription": desc_result.get("definition_text") or key_desc,
        "page":               str(extraction_page) if extraction_page else "",
        "value":              validated.get("value"),
        "score":              validated.get("score"),
        "reason":             validated.get("reason"),
        "expected_format":    expected_format,
        "format_valid":       validated.get("format_valid", True),
        "description":        desc_result.get("definition_text", ""),
        "rule_context":       rule_context or value_result.get("rule_context"),
        "found_in":           found_in,
        "section":            section_info.get("topic"),
        "_debug": {
            "content_type":   content_type,
            "section_pages":  relevant_pages,
            "llm_calls":      llm_calls,
            "timing":         timing,
        },
    }


def _confidence_from_result(result: dict) -> float:
    """Map textual confidence to float."""
    conf_map = {"high": 0.85, "medium": 0.6, "low": 0.35}
    conf_str = result.get("confidence", "medium")
    if isinstance(conf_str, (int, float)):
        return float(conf_str)
    return conf_map.get(str(conf_str).lower(), 0.5)


# =============================================================================
# FULL PIPELINE
# =============================================================================

def run_pipeline(ocr_path: Path, keys_path: Path,
                 out_path: Path, backend: str,
                 doc_type: str = "loan",
                 role: str = "banking",
                 max_workers: int = 6,
                 worker_delay: float = 0.3,
                 # OCR integration
                 pdf_path: Path | None = None,
                 ocr_engine: str = "glm",
                 ocr_workers: int | None = None,
                 ocr_dpi: int | None = None,
                 ocr_cache: bool = True):

    timer = StepTimer(f"DocAI Extraction Pipeline — {(pdf_path or ocr_path).name}")

    # ── OCR Phase (optional) ──────────────────────────────────────────────────
    if pdf_path is not None:
        timer.start("OCR Phase")
        ocr_path, ocr_text_direct = run_ocr_on_pdf(
            pdf_path   = pdf_path,
            ocr_engine = ocr_engine,
            ocr_workers= ocr_workers,
            dpi        = ocr_dpi,
            use_cache  = ocr_cache,
            out_dir    = out_path.parent,
        )
        timer.end(f"{len(ocr_text_direct):,} chars")

    # ── Load inputs ───────────────────────────────────────────────────────────
    timer.start("Loading inputs")
    ocr_text, keys = load_inputs(ocr_path, keys_path)
    timer.end(f"{len(ocr_text):,} chars | {len(keys)} keys | doc_type={doc_type}")

    # ── LLM clients ───────────────────────────────────────────────────────────
    timer.start("Initialising LLM clients", f"backend={backend}")
    model_summary(backend)
    clients = build_agent_clients(backend=backend)
    timer.end("All clients ready")

    # ── Phase 1: Document Map ─────────────────────────────────────────────────
    timer.start("Phase 1 — Document Map")
    print(f"\n{BOLD}{'═'*65}{RESET}")
    print(f"  {BOLD}PHASE 1: DOCUMENT MAP{RESET}")
    print(f"{'─'*65}")
    doc_map = doc_map_agent.build_document_map(ocr_text, clients["doc_map"])
    timer.end(f"{len(doc_map.get('sections', []))} sections identified")

    # ── Phase 2: Extract all keys in parallel ─────────────────────────────────
    timer.start("Phase 2 — Parallel key extraction")
    print(f"\n{BOLD}{'═'*65}{RESET}")
    print(f"  {BOLD}PHASE 2: EXTRACTING {len(keys)} KEYS ({max_workers} workers){RESET}")
    print(f"{'─'*65}")

    results_map     = {}
    total_llm_calls = 0
    import threading
    lock            = threading.Lock()
    processed       = 0

    def process_key(args):
        nonlocal processed
        i, key_def, delay = args
        if delay > 0:
            time.sleep(delay)
        try:
            result = extract_one(key_def, doc_map, ocr_text, clients, doc_type)
        except Exception as e:
            import traceback
            print(f"  {RED}✗ Error on key {key_def.get('keyName')}: {e}{RESET}")
            result = {
                "keyName":  key_def.get("keyName", f"key_{i}"),
                "value":    None,
                "score":    0.0,
                "reason":   f"Error: {str(e)[:100]}",
                "description": "",
                "rule_context": None,
                "found_in": "error",
                "_debug":   {"error": str(e), "traceback": traceback.format_exc()},
            }
        with lock:
            processed += 1
            print(f"  {DIM}[{processed}/{len(keys)}] {key_def['keyName'][:45]}{RESET}")
        return i, result

    tasks = [
        (i, kd, (i % max_workers) * worker_delay)
        for i, kd in enumerate(keys)
    ]

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(process_key, t): t[0] for t in tasks}
        for future in as_completed(futures):
            i, result = future.result()
            results_map[i] = result
            total_llm_calls += result.get("_debug", {}).get("llm_calls", 0)

    results = [results_map[i] for i in range(len(keys))]
    timer.end(f"{total_llm_calls} total LLM calls")

    # ── Save results ──────────────────────────────────────────────────────────
    timer.start("Saving results")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    latest = out_path.parent / "results_latest.json"
    timed  = out_path.parent / f"results_{timestamp}.json"

    clean = [{k: v for k, v in r.items() if k != "_debug"} for r in results]
    latest.write_text(json.dumps(clean,   indent=2, ensure_ascii=False))
    timed.write_text( json.dumps(results, indent=2, ensure_ascii=False))
    timer.end(f"→ {latest}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'═'*65}{RESET}")
    print(f"  {BOLD}RESULTS SUMMARY{RESET}")
    print(f"{'─'*65}")
    high   = sum(1 for r in results if (r.get("score") or 0) >= SCORE_HIGH)
    medium = sum(1 for r in results if SCORE_MEDIUM <= (r.get("score") or 0) < SCORE_HIGH)
    low    = sum(1 for r in results if (r.get("score") or 0) < SCORE_MEDIUM)
    for r in results:
        score = r.get("score") or 0
        result_row(r["keyName"], r["value"], score,
                   extra=f"fmt={r.get('expected_format','?')} found_in={r.get('found_in','?')}")
    print(f"\n  {GREEN}High  (≥{SCORE_HIGH}):{RESET} {high}/{len(results)}")
    print(f"  {YELLOW}Med   (≥{SCORE_MEDIUM}):{RESET} {medium}/{len(results)}")
    print(f"  {RED}Low   (<{SCORE_MEDIUM}):{RESET} {low}/{len(results)}")
    print(f"\n  Total LLM calls: {total_llm_calls} "
          f"(avg {total_llm_calls/max(len(keys),1):.1f}/key)")
    timer.summary()

    return results


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="DocAI — Multi-Agent Document Extraction Pipeline (with integrated GLM-OCR)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # PDF → OCR → extract (one command, fully integrated):
  python run_pipeline.py --pdf loan.pdf --keys keys.json --backend ollama

  # Pre-OCR'd text → extract:
  python run_pipeline.py --ocr loan.txt --keys keys.json --backend ollama

  # Cloud (Groq) with PDF input:
  export GROQ_API_KEY='gsk_...'
  python run_pipeline.py --pdf loan.pdf --keys keys.json

  # Tesseract OCR (fast CPU) + Groq extraction:
  python run_pipeline.py --pdf scan.pdf --keys keys.json \\
    --ocr-engine tesseract --ocr-workers 4

  # With role and doc type:
  python run_pipeline.py --pdf isda.pdf --keys isda_keys.json \\
    --doc-type isda --role banking --backend ollama
        """
    )

    # ── Input source (mutually exclusive: PDF or pre-OCR'd text) ─────────────
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf", default=None,
                     help="Path to PDF — runs GLM-OCR then extracts keys")
    src.add_argument("--ocr", default=None,
                     help="Path to already-OCR'd text file — skips OCR step")

    parser.add_argument("--keys",       required=True, help="Path to keys JSON file")
    parser.add_argument("--out",        default=str(OUTPUT_DIR / "results.json"))
    parser.add_argument("--backend",    default="groq", choices=["groq", "ollama"],
                        help="LLM backend for extraction agents (default: groq)")
    parser.add_argument("--doc-type",   default="loan",
                        choices=["loan", "isda", "invoice", "compliance_report"],
                        help="Document type — determines prompt variant (default: loan)")
    parser.add_argument("--role",       default="banking",
                        choices=["banking", "insurance", "compliance"],
                        help="User role (default: banking)")
    parser.add_argument("--workers",    type=int, default=None,
                        help="Parallel extraction workers (default: 1 for ollama, 6 for groq)")

    # ── OCR options (only used with --pdf) ────────────────────────────────────
    ocr_grp = parser.add_argument_group("OCR options (only with --pdf)")
    ocr_grp.add_argument("--ocr-engine",   default="glm", choices=["glm", "tesseract"],
                         help="OCR engine: 'glm' (quality, GPU) or 'tesseract' (fast, CPU). Default: glm")
    ocr_grp.add_argument("--ocr-workers",  type=int, default=None,
                         help="OCR concurrent workers (default: 2 for glm, 4 for tesseract)")
    ocr_grp.add_argument("--ocr-dpi",      type=int, default=None,
                         help="PDF render DPI for OCR (default: 120 for glm, 150 for tesseract)")
    ocr_grp.add_argument("--no-ocr-cache", action="store_true",
                         help="Disable per-page OCR cache (re-runs OCR on every page)")

    args = parser.parse_args()

    # Validate --pdf with ocr engine options
    if args.ocr and any([args.ocr_engine != "glm", args.ocr_workers, args.ocr_dpi, args.no_ocr_cache]):
        print(f"{YELLOW}[warn] --ocr-engine / --ocr-workers / --ocr-dpi / --no-ocr-cache "
              f"are ignored when --ocr is used instead of --pdf{RESET}")

    # Extraction worker default depends on backend
    if args.workers is None:
        args.workers = 1 if args.backend == "ollama" else 6

    pdf_path = Path(args.pdf) if args.pdf else None
    ocr_path = Path(args.ocr) if args.ocr else Path(args.out).parent / "_ocr_placeholder.txt"

    run_pipeline(
        ocr_path    = ocr_path,
        keys_path   = Path(args.keys),
        out_path    = Path(args.out),
        backend     = args.backend,
        doc_type    = args.doc_type,
        role        = args.role,
        max_workers = args.workers,
        pdf_path    = pdf_path,
        ocr_engine  = args.ocr_engine,
        ocr_workers = args.ocr_workers,
        ocr_dpi     = args.ocr_dpi,
        ocr_cache   = not args.no_ocr_cache,
    )


if __name__ == "__main__":
    main()
