"""
pipeline_runner.py — Maximum speed configuration
──────────────────────────────────────────────────────────────────────────────
Optimizations applied:
  1. Sentence-transformers model pre-warmed at import time (background thread)
  2. OCR output cached by MD5 hash — same PDF content = 0 s OCR on re-upload
  3. Embedding index cached to .pkl — instant reload on same document
  4. Keys processed with ThreadPoolExecutor (MAX_PARALLEL_KEYS workers)
  5. Worker starts staggered by 0.3 s to avoid simultaneous Groq rate-limit spikes
  6. All heavy module imports cached at module level (no re-import per document)
"""

import sys
import os
import json
import time
import hashlib
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from database import update_document

# ── Project paths ─────────────────────────────────────────────────────────────
PROJ_ROOT      = Path(__file__).parent.parent
OCR_SCRIPTS    = PROJ_ROOT / "OCR_platform" / "scripts"
OCR_OUTPUT_DIR = PROJ_ROOT / "OCR_platform" / "data" / "input" / "output"
PIPELINE_ROOT  = PROJ_ROOT / "full_pipeline"

for p in [str(OCR_SCRIPTS), str(PIPELINE_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ── Tuning ────────────────────────────────────────────────────────────────────
MAX_PARALLEL_KEYS  = 6      # parallel LLM calls — safe for Groq free tier
WORKER_START_DELAY = 0.3    # seconds between worker launches to stagger API calls


# ── Module-level caches ───────────────────────────────────────────────────────
_ocr_module    = None
_pipeline_fns  = None
_prewarm_done  = False


_OCR_PYTHON = str(PROJ_ROOT / "OCR_platform" / "ocr_env" / "bin" / "python3")
_OCR_SCRIPT = str(OCR_SCRIPTS / "pdf_pipeline.py")    # YOLO + TATR + DocTr


def _run_ocr_subprocess(pdf_path: str):
    """
    Run the YOLO+TATR+DocTr pipeline in an isolated subprocess using ocr_env.
    Avoids import conflicts between FastAPI's packages and the ML libraries.
    """
    import subprocess
    result = subprocess.run(
        [_OCR_PYTHON, _OCR_SCRIPT, pdf_path],
        capture_output=False,   # let stdout/stderr flow to terminal
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"OCR subprocess failed (exit {result.returncode})")


def _get_pipeline():
    global _pipeline_fns
    if _pipeline_fns is None:
        from core.llm_client    import build_agent_clients
        from core.index_builder import DocumentIndex
        from run_pipeline        import load_inputs, extract_one
        _pipeline_fns = (build_agent_clients, DocumentIndex, load_inputs, extract_one)
    return _pipeline_fns


def prewarm():
    """
    Pre-load sentence-transformers model in a background thread at startup.
    Called once from main.py so the first document doesn't pay model-load time.
    """
    global _prewarm_done
    if _prewarm_done:
        return

    def _do():
        global _prewarm_done
        try:
            from sentence_transformers import SentenceTransformer
            SentenceTransformer("all-MiniLM-L6-v2")
            _prewarm_done = True
        except Exception:
            pass

    threading.Thread(target=_do, daemon=True).start()


# ── OCR cache by content hash ─────────────────────────────────────────────────

def _pdf_hash(pdf_path: str) -> str:
    """MD5 of first 1 MB — fast, unique per content."""
    h = hashlib.md5()
    with open(pdf_path, "rb") as f:
        h.update(f.read(1_048_576))
    return h.hexdigest()[:10]


_PIPELINE_VERSION = "v2"   # bump to invalidate cache after pipeline changes


def _ocr_cached_path(pdf_path: str) -> Path:
    """Return the expected OCR output path keyed by content hash and pipeline version."""
    stem = Path(pdf_path).stem
    hsh  = _pdf_hash(pdf_path)
    return OCR_OUTPUT_DIR / f"{stem}_{hsh}_{_PIPELINE_VERSION}_full_report.txt"


# ── Main runner ───────────────────────────────────────────────────────────────

def run_full_pipeline(
    doc_id:       str,
    pdf_path:     str,
    keys_path:    str,
    backend:      str = "groq",
    groq_api_key: str = "",
):
    try:
        if groq_api_key:
            os.environ["GROQ_API_KEY"] = groq_api_key

        # ══════════════════════════════════════════════════════════════════
        # STEP 1 — OCR  (skipped when same PDF content was already processed)
        # ══════════════════════════════════════════════════════════════════
        update_document(doc_id, {
            "status": "processing", "pipeline_step": "ocr_processing", "progress": 5,
        })

        ocr_out = _ocr_cached_path(pdf_path)

        if not ocr_out.exists():
            _run_ocr_subprocess(pdf_path)
            # pdf_pipeline.py writes to {stem}_full_report.txt — rename to versioned cache path
            legacy = OCR_OUTPUT_DIR / f"{Path(pdf_path).stem}_full_report.txt"
            if legacy.exists() and not ocr_out.exists():
                legacy.rename(ocr_out)

        if not ocr_out.exists():
            raise RuntimeError(f"OCR output not found: {ocr_out}")

        ocr_text    = ocr_out.read_text(encoding="utf-8")
        total_pages = ocr_text.count("\nPAGE ") + (1 if ocr_text.startswith("PAGE ") else 0)

        update_document(doc_id, {
            "ocr_path": str(ocr_out), "total_pages": total_pages,
            "pipeline_step": "ocr_done", "progress": 25,
        })

        # ══════════════════════════════════════════════════════════════════
        # STEP 2 — Embedding index  (loaded from .pkl cache when available)
        # ══════════════════════════════════════════════════════════════════
        update_document(doc_id, {"pipeline_step": "building_index", "progress": 30})

        build_agent_clients, DocumentIndex, load_inputs, extract_one = _get_pipeline()
        ocr_text_clean, keys = load_inputs(Path(ocr_out), Path(keys_path))

        update_document(doc_id, {
            "total_keys": len(keys), "pipeline_step": "building_index", "progress": 35,
        })

        index      = DocumentIndex()
        # Cache index next to the OCR file so same content always reuses it
        cache_path = ocr_out.with_suffix(".pkl")
        if cache_path.exists():
            try:
                index.load(str(cache_path))
            except Exception:
                index.build(ocr_text_clean)
                index.save(str(cache_path))
        else:
            index.build(ocr_text_clean)
            index.save(str(cache_path))

        update_document(doc_id, {"pipeline_step": "index_ready", "progress": 45})

        # ══════════════════════════════════════════════════════════════════
        # STEP 3 — LLM clients
        # ══════════════════════════════════════════════════════════════════
        update_document(doc_id, {"pipeline_step": "initializing_agents", "progress": 50})
        clients = build_agent_clients(backend=backend)

        # ══════════════════════════════════════════════════════════════════
        # STEP 4 — Extract keys IN PARALLEL (staggered starts)
        # ══════════════════════════════════════════════════════════════════
        update_document(doc_id, {"pipeline_step": "extracting_fields", "progress": 55})

        n_keys           = len(keys)
        progress_per_key = 40.0 / max(n_keys, 1)
        results_map      = {}
        processed_count  = 0
        lock             = threading.Lock()

        def process_key(args):
            nonlocal processed_count
            i, key_def, delay = args
            if delay > 0:
                time.sleep(delay)   # stagger to spread API calls over time
            try:
                result = extract_one(key_def, index, ocr_text_clean, clients)
            except Exception as e:
                result = {
                    "keyName": key_def.get("keyName", f"key_{i}"),
                    "value":   None,
                    "score":   0.0,
                    "reason":  f"Error: {str(e)[:120]}",
                    "_debug":  {"error": str(e)},
                }
            with lock:
                processed_count += 1
                update_document(doc_id, {
                    "processed_keys": processed_count,
                    "progress": round(55 + processed_count * progress_per_key, 1),
                })
            return i, result

        # Build task list — workers within same batch get staggered delays
        tasks = [
            (i, kd, (i % MAX_PARALLEL_KEYS) * WORKER_START_DELAY)
            for i, kd in enumerate(keys)
        ]

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_KEYS) as pool:
            futures = {pool.submit(process_key, t): t[0] for t in tasks}
            for future in as_completed(futures):
                i, result = future.result()
                results_map[i] = result

        results = [results_map[i] for i in range(n_keys)]

        # ══════════════════════════════════════════════════════════════════
        # STEP 5 — Save results
        # ══════════════════════════════════════════════════════════════════
        update_document(doc_id, {"pipeline_step": "saving_results", "progress": 96})

        results_file = Path(keys_path).parent / "results.json"
        # Keep agent_used and flatten key _debug fields into top-level for frontend
        clean = []
        for r in results:
            entry = {k: v for k, v in r.items() if k != "_debug"}
            debug = r.get("_debug") or {}
            entry["agent_used"]           = entry.get("agent_used") or "agent1_router"
            entry["embedding_confidence"] = debug.get("embedding_confidence")
            entry["llm_calls"]            = debug.get("llm_calls", 0)
            entry["router_used_llm"]      = debug.get("router_used_llm", False)
            entry["row_label"]            = debug.get("row_label")
            entry["col_label"]            = debug.get("col_label")
            clean.append(entry)
        results_file.write_text(json.dumps(clean, indent=2, ensure_ascii=False))

        scores   = [r.get("score") or 0 for r in clean]
        avg_conf = round(sum(scores) / max(len(scores), 1), 3)

        update_document(doc_id, {
            "status":         "completed",
            "pipeline_step":  "completed",
            "progress":       100,
            "completed_at":   datetime.utcnow().isoformat(),
            "results_path":   str(results_file),
            "avg_confidence": avg_conf,
        })

    except Exception as exc:
        update_document(doc_id, {
            "status":        "error",
            "pipeline_step": "error",
            "error_msg":     f"{exc}\n\n{traceback.format_exc()}",
        })


def launch(doc_id: str, pdf_path: str, keys_path: str,
           backend: str = "groq", groq_api_key: str = ""):
    t = threading.Thread(
        target=run_full_pipeline,
        args=(doc_id, pdf_path, keys_path, backend, groq_api_key),
        daemon=True,
    )
    t.start()
    return t
