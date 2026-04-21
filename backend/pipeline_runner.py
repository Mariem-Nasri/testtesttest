"""
pipeline_runner.py
──────────────────────────────────────────────────────────────────────────────
Runs the full 3-phase extraction pipeline in a background thread.

Architecture:
  1. OCR (cached by PDF hash — zero cost on re-upload)
  2. Phase 1: Document Map  (1 LLM call, shared across all keys)
  3. Phase 2: Parallel key extraction  (6 workers, staggered starts)
  4. Phase 3: Validator  (per-key, format check first)

No embedding index. No sentence-transformers. All LLM-based extraction.

For financial data security → set backend="ollama" in upload request.
  All inference runs locally with qwen2.5:7b. Nothing leaves the machine.
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
MAX_PARALLEL_KEYS  = 6     # parallel LLM calls
WORKER_START_DELAY = 0.3   # seconds between worker launches (rate-limit protection)

_pipeline_fns = None

_OCR_PYTHON = str(PROJ_ROOT / "OCR_platform" / "ocr_env" / "bin" / "python3")
_OCR_SCRIPT = str(OCR_SCRIPTS / "pdf_pipeline.py")


# ── OCR subprocess ─────────────────────────────────────────────────────────────

def _run_ocr_subprocess(pdf_path: str):
    """
    Run YOLO+TATR+DocTr OCR pipeline in isolated subprocess.
    The ocr_env virtualenv avoids import conflicts with FastAPI packages.
    """
    import subprocess
    result = subprocess.run(
        [_OCR_PYTHON, _OCR_SCRIPT, pdf_path],
        capture_output=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"OCR subprocess failed (exit {result.returncode})")


# ── PDF hash cache ────────────────────────────────────────────────────────────

def _pdf_hash(pdf_path: str) -> str:
    """MD5 of first 1 MB — fast fingerprint, unique per PDF content."""
    h = hashlib.md5()
    with open(pdf_path, "rb") as f:
        h.update(f.read(1_048_576))
    return h.hexdigest()[:10]


_PIPELINE_VERSION = "v3"   # bump to invalidate OCR cache after pipeline changes


def _ocr_cached_path(pdf_path: str) -> Path:
    stem = Path(pdf_path).stem
    hsh  = _pdf_hash(pdf_path)
    return OCR_OUTPUT_DIR / f"{stem}_{hsh}_{_PIPELINE_VERSION}_full_report.txt"


# ── Pipeline helpers ──────────────────────────────────────────────────────────

def _get_pipeline():
    global _pipeline_fns
    if _pipeline_fns is None:
        from core.llm_client import build_agent_clients
        from run_pipeline    import load_inputs, extract_one
        import agents.agent_document_map as doc_map_mod
        _pipeline_fns = (build_agent_clients, load_inputs, extract_one, doc_map_mod)
    return _pipeline_fns


# ── Main runner ───────────────────────────────────────────────────────────────

def run_full_pipeline(
    doc_id:       str,
    pdf_path:     str,
    keys_path:    str,
    backend:      str  = "groq",
    groq_api_key: str  = "",
    doc_type:     str  = "loan",
    role:         str  = "banking",
):
    try:
        if groq_api_key:
            os.environ["GROQ_API_KEY"] = groq_api_key

        # ══════════════════════════════════════════════════════════════════
        # STEP 1 — OCR  (skipped when same PDF content already processed)
        # ══════════════════════════════════════════════════════════════════
        update_document(doc_id, {
            "status": "processing", "pipeline_step": "ocr_processing", "progress": 5,
        })

        ocr_out = _ocr_cached_path(pdf_path)

        if not ocr_out.exists():
            _run_ocr_subprocess(pdf_path)
            # pdf_pipeline.py writes to {stem}_full_report.txt — rename to versioned cache
            legacy = OCR_OUTPUT_DIR / f"{Path(pdf_path).stem}_full_report.txt"
            if legacy.exists() and not ocr_out.exists():
                legacy.rename(ocr_out)

        if not ocr_out.exists():
            raise RuntimeError(f"OCR output not found: {ocr_out}")

        ocr_text    = ocr_out.read_text(encoding="utf-8")
        total_pages = ocr_text.count("\nPAGE ") + (1 if ocr_text.startswith("PAGE ") else 0)

        update_document(doc_id, {
            "ocr_path": str(ocr_out), "total_pages": total_pages,
            "pipeline_step": "ocr_done", "progress": 20,
        })

        # ══════════════════════════════════════════════════════════════════
        # STEP 2 — LLM Clients
        # ══════════════════════════════════════════════════════════════════
        update_document(doc_id, {"pipeline_step": "initializing_agents", "progress": 25})

        build_agent_clients, load_inputs, extract_one, doc_map_mod = _get_pipeline()

        ocr_text_clean, keys = load_inputs(Path(ocr_out), Path(keys_path))

        update_document(doc_id, {
            "total_keys": len(keys),
            "pipeline_step": "initializing_agents",
            "progress": 30,
        })

        clients = build_agent_clients(backend=backend)

        # ══════════════════════════════════════════════════════════════════
        # STEP 3 — Phase 1: Document Map  (1 LLM call)
        # ══════════════════════════════════════════════════════════════════
        update_document(doc_id, {"pipeline_step": "building_document_map", "progress": 35})

        doc_map = doc_map_mod.build_document_map(ocr_text_clean, clients["doc_map"])

        update_document(doc_id, {"pipeline_step": "document_map_ready", "progress": 45})

        # ══════════════════════════════════════════════════════════════════
        # STEP 4 — Phase 2: Extract keys IN PARALLEL
        # ══════════════════════════════════════════════════════════════════
        update_document(doc_id, {"pipeline_step": "extracting_fields", "progress": 50})

        n_keys           = len(keys)
        progress_per_key = 40.0 / max(n_keys, 1)
        results_map      = {}
        processed_count  = 0
        lock             = threading.Lock()

        def process_key(args):
            nonlocal processed_count
            i, key_def, delay = args
            if delay > 0:
                time.sleep(delay)
            try:
                result = extract_one(key_def, doc_map, ocr_text_clean, clients, doc_type)
            except Exception as e:
                result = {
                    "keyName":   key_def.get("keyName", f"key_{i}"),
                    "value":     None,
                    "score":     0.0,
                    "reason":    f"Error: {str(e)[:120]}",
                    "description": "",
                    "rule_context": None,
                    "found_in":  "error",
                    "_debug":    {"error": str(e)},
                }
            with lock:
                processed_count += 1
                update_document(doc_id, {
                    "processed_keys": processed_count,
                    "progress": round(50 + processed_count * progress_per_key, 1),
                })
            return i, result

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
        update_document(doc_id, {"pipeline_step": "saving_results", "progress": 95})

        results_file = Path(keys_path).parent / "results.json"
        clean = []
        for r in results:
            entry = {k: v for k, v in r.items() if k != "_debug"}
            debug = r.get("_debug") or {}
            entry["agent_used"]   = entry.get("found_in") or "llm"
            entry["llm_calls"]    = debug.get("llm_calls", 0)
            entry["section"]      = entry.get("section", "")
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
           backend: str = "groq", groq_api_key: str = "",
           doc_type: str = "loan", role: str = "banking"):
    t = threading.Thread(
        target=run_full_pipeline,
        args=(doc_id, pdf_path, keys_path, backend, groq_api_key, doc_type, role),
        daemon=True,
    )
    t.start()
    return t
