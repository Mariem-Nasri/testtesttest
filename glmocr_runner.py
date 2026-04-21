#!/usr/bin/env python3
"""
OCR Standalone Runner
══════════════════════════════════════════════════════════════
Runs OCR on a PDF and writes clean, ASCII-table text.

Engines
───────
  --engine glm        GLM-OCR via Ollama (VLM, high quality, slow ~18s/page)
  --engine tesseract  Tesseract 4 (CPU, fast ~0.5-2s/page, truly parallel)

Speed optimisations:
  1. JPEG encoding  — 5-10x smaller images than PNG → faster Ollama upload
  2. Page cache     — completed pages saved to disk; re-runs skip them
  3. Resume support — crashes / Ctrl+C lose nothing; just re-run
  4. Parallel mode  — send N pages concurrently
  5. Lower DPI      — 120 DPI default (vs 150) still accurate for GLM-OCR

USAGE
──────
  python glmocr_runner.py document.pdf --engine tesseract --workers 4
  python glmocr_runner.py document.pdf --engine glm --workers 2 --dpi 100
  python glmocr_runner.py document.pdf --out result.txt --no-cache
  python glmocr_runner.py document.pdf --pages 1-10      # subset of pages

SPEED TIPS (GLM engine)
──────────
  --workers 1   Safe default (sequential). Always works.
  --workers 2   ~1.5-2x faster if GPU has ≥ 12 GB VRAM free.
  --dpi 100     Noticeably faster; slight quality drop on small fonts.
  --dpi 120     Good balance (default).
  --jpeg 75     Smaller images, faster; fine for most documents.

SPEED TIPS (Tesseract engine)
──────────────────────────────
  --workers 4   Use all CPU cores — Tesseract is truly parallel.
  --dpi 150     Higher DPI improves Tesseract accuracy (default for tesseract).
  --lang eng    Language code (default: eng). Use 'eng+fra' for multilingual.
══════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ── dependency bootstrap ─────────────────────────────────────────────────────
def _ensure(packages: list[str]) -> None:
    import importlib.util, subprocess
    missing = [p for p in packages if not importlib.util.find_spec(p.split("[")[0].replace("-", "_"))]
    if missing:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet"] + missing)

_ensure(["requests", "pdf2image", "Pillow", "tqdm", "pdfplumber", "pytesseract"])

import pdfplumber
import requests
from pdf2image import convert_from_path
from PIL import Image
from tqdm import tqdm

# ── import post-processing from ocrs/ocr_benchmark.py ───────────────────────
_PROJECT = Path(__file__).parent
_OCRS_DIR = _PROJECT / "ocrs"
if str(_OCRS_DIR) not in sys.path:
    sys.path.insert(0, str(_OCRS_DIR))

from ocr_benchmark import (
    clean_glmocr_output,
    DynamicTableCorrector,
    markdown_tables_to_ascii,
)

# ─────────────────────────────────────────────────────────────────────────────
# OLLAMA HELPERS
# ─────────────────────────────────────────────────────────────────────────────

OLLAMA_BASE   = "http://localhost:11434"
MODEL         = "glm-ocr"          # overridden by --model flag

# Single-page prompt
PROMPT_SINGLE = (
    "You are an OCR engine. Extract ALL text from this document page exactly as it appears. "
    "Rules:\n"
    "- Output tables strictly as markdown pipe tables: | col1 | col2 | col3 |\n"
    "- Do NOT use HTML tags (<table>, <tr>, <td>, etc.)\n"
    "- Do NOT skip any text, numbers, or symbols\n"
    "- Do NOT add explanations, comments, or summaries\n"
    "- Preserve headings, paragraphs, bullet points, and numbering\n"
    "Output only the extracted text."
)

# Multi-page batch prompt (N filled in at call time)
PROMPT_BATCH = (
    "You are an OCR engine processing {n} document pages shown in order as images.\n"
    "For each page output its full text preceded by a marker line: === PAGE N === (N starts at 1).\n"
    "Rules:\n"
    "- Output tables strictly as markdown pipe tables: | col1 | col2 | col3 |\n"
    "- Do NOT use HTML tags\n"
    "- Do NOT skip any text, numbers, or symbols\n"
    "- Do NOT add commentary or explanations\n"
    "- Preserve headings, paragraphs, bullet points, and numbering\n"
    "Output only the extracted text with === PAGE N === markers."
)

_OCR_OPTIONS = {"temperature": 0.0, "top_p": 1.0}


def ollama_running() -> bool:
    try:
        return requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


def model_available(model: str = MODEL) -> bool:
    try:
        tags = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3).json().get("models", [])
        return any(model in m.get("name", "") for m in tags)
    except Exception:
        return False


def list_vision_models() -> list[str]:
    """Return Ollama models that are likely vision-capable (have image support)."""
    try:
        tags = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3).json().get("models", [])
        return [m["name"] for m in tags]
    except Exception:
        return []


def pil_to_jpeg_b64(img: Image.Image, quality: int = 85) -> str:
    """Encode a PIL image as JPEG base64 (5-10x smaller than PNG)."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


# ─────────────────────────────────────────────────────────────────────────────
# TESSERACT ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def ocr_page_tesseract(img: Image.Image, lang: str = "eng") -> str:
    """Run Tesseract on one page image and return plain text."""
    import pytesseract
    text = pytesseract.image_to_string(img, config="--psm 6 --oem 1", lang=lang)
    return text.strip()


def ocr_page(img: Image.Image, model: str = MODEL,
             jpeg_quality: int = 85, timeout: int = 180) -> str:
    """Send one page to Ollama and return the OCR text."""
    payload = {
        "model":   model,
        "prompt":  PROMPT_SINGLE,
        "images":  [pil_to_jpeg_b64(img, jpeg_quality)],
        "stream":  False,
        "options": _OCR_OPTIONS,
    }
    try:
        r = requests.post(f"{OLLAMA_BASE}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except Exception as e:
        return f"[OCR ERROR: {e}]"


def ocr_batch(imgs: list[Image.Image], model: str = MODEL,
              jpeg_quality: int = 85, timeout: int = 360) -> list[str]:
    """
    Send multiple pages in ONE Ollama request.
    Returns a list of per-page text strings (same length as imgs).

    Sending N pages together is faster than N separate calls because:
    - Only one API round-trip
    - Model shares KV-cache context across the batch
    Empirically 4 pages together take ~1.5-2x single-page time (not 4x).
    """
    n = len(imgs)
    if n == 1:
        return [ocr_page(imgs[0], model=model, jpeg_quality=jpeg_quality, timeout=timeout)]

    payload = {
        "model":   model,
        "prompt":  PROMPT_BATCH.format(n=n),
        "images":  [pil_to_jpeg_b64(img, jpeg_quality) for img in imgs],
        "stream":  False,
        "options": _OCR_OPTIONS,
    }
    try:
        r = requests.post(f"{OLLAMA_BASE}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
        raw = r.json().get("response", "").strip()

        # Parse === PAGE N === markers back into per-page texts
        parts = re.split(r"===\s*PAGE\s*\d+\s*===", raw, flags=re.IGNORECASE)
        texts = [p.strip() for p in parts[1:]]
        # If model ignored the markers, treat the whole response as page 1
        if not texts:
            texts = [raw]
        while len(texts) < n:
            texts.append("")
        return texts[:n]

    except requests.HTTPError:
        # Model doesn't support multiple images — fall back to one call per page
        return [ocr_page(img, model=model, jpeg_quality=jpeg_quality, timeout=timeout)
                for img in imgs]
    except Exception as e:
        return [f"[OCR ERROR: {e}]"] * n


# ─────────────────────────────────────────────────────────────────────────────
# PAGE CACHE  (saves each page result immediately → crash-safe)
# ─────────────────────────────────────────────────────────────────────────────

def _cache_file(cache_dir: Path, page_idx: int) -> Path:
    return cache_dir / f"page_{page_idx:04d}.json"


def _load_cache(cache_dir: Path, page_idx: int) -> str | None:
    f = _cache_file(cache_dir, page_idx)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))["text"]
        except Exception:
            return None
    return None


def _save_cache(cache_dir: Path, page_idx: int, text: str) -> None:
    _cache_file(cache_dir, page_idx).write_text(
        json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8"
    )


# ─────────────────────────────────────────────────────────────────────────────
# PDF LOADING
# ─────────────────────────────────────────────────────────────────────────────

def _is_digital_pdf(pdf_path: str, sample: int = 3) -> bool:
    """Return True if the PDF has embedded selectable text (not scanned)."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:min(sample, len(pdf.pages))]:
                if len((page.extract_text() or "").strip()) > 50:
                    return True
    except Exception:
        pass
    return False


def load_pages(pdf_path: str, dpi: int = 120) -> list[Image.Image]:
    """
    Load PDF pages as PIL images.
    Digital PDFs → rendered directly (no preprocessing needed for GLM-OCR).
    Scanned PDFs → same (GLM-OCR handles raw images better than binarized ones).
    """
    return convert_from_path(pdf_path, dpi=dpi)


# ─────────────────────────────────────────────────────────────────────────────
# CORE PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def process_pdf(
    pdf_path: str,
    out_path: Path,
    *,
    engine: str = "glm",
    model: str = MODEL,
    lang: str = "eng",
    dpi: int = 120,
    workers: int = 1,
    batch_size: int = 1,
    jpeg_quality: int = 85,
    use_cache: bool = True,
    cache_dir: Path | None = None,
    page_range: tuple[int, int] | None = None,
) -> str:
    """
    Run OCR on *pdf_path*, write result to *out_path*.

    Parameters
    ----------
    engine       'glm' (Ollama VLM) or 'tesseract' (fast CPU OCR).
    model        Ollama model name (glm engine only).
    lang         Tesseract language code, e.g. 'eng', 'eng+fra' (tesseract only).
    workers      Concurrent requests (1 = sequential).
                 For tesseract, use workers=4 to saturate CPU cores.
    batch_size   Pages per Ollama request (glm engine only).
    jpeg_quality JPEG quality sent to Ollama (glm engine only).
    use_cache    Save per-page results to disk (crash-safe, resumable).
    page_range   (start, end) 1-indexed to process only a page slice.
    """
    t_start = time.time()

    # ── load pages ───────────────────────────────────────────────────────────
    eff_dpi = dpi if engine == "glm" else max(dpi, 150)  # tesseract needs ≥150 DPI
    print(f"[runner] Rendering PDF at {eff_dpi} DPI …")
    all_pages = load_pages(pdf_path, dpi=eff_dpi)
    n_total = len(all_pages)

    if page_range:
        s = max(0, page_range[0] - 1)
        e = min(n_total, page_range[1])
        page_indices = list(range(s, e))
    else:
        page_indices = list(range(n_total))

    n = len(page_indices)

    if engine == "tesseract":
        print(f"[runner] {n_total} pages total | processing {n} | "
              f"engine=tesseract | lang={lang} | workers={workers}")
    else:
        eff_batch = min(batch_size, n)
        n_batches = (n + eff_batch - 1) // eff_batch
        print(f"[runner] {n_total} pages total | processing {n} | "
              f"batch={eff_batch} → {n_batches} requests | workers={workers} | model={model}")

    # ── cache setup ──────────────────────────────────────────────────────────
    if cache_dir is None:
        cache_dir = out_path.parent / f".{engine}_cache" / Path(pdf_path).stem
    if use_cache:
        cache_dir.mkdir(parents=True, exist_ok=True)

    results: dict[int, str] = {}
    to_run: list[int] = []
    for idx in page_indices:
        cached = _load_cache(cache_dir, idx) if use_cache else None
        if cached is not None:
            results[idx] = cached
        else:
            to_run.append(idx)

    if len(to_run) < n:
        print(f"[runner] {n - len(to_run)} pages from cache — {len(to_run)} remaining")

    # ── OCR ──────────────────────────────────────────────────────────────────
    if engine == "tesseract":
        # One task per page — truly parallel on CPU
        def _run_page(idx: int) -> tuple[int, str]:
            text = ocr_page_tesseract(all_pages[idx], lang=lang)
            if use_cache:
                _save_cache(cache_dir, idx, text)
            return idx, text

        if to_run:
            if workers == 1:
                pbar = tqdm(total=len(to_run), desc="OCR", unit="page")
                for idx in to_run:
                    i, t = _run_page(idx)
                    results[i] = t
                    pbar.update(1)
                pbar.close()
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(_run_page, idx): idx for idx in to_run}
                    pbar = tqdm(total=len(to_run), desc="OCR", unit="page")
                    for fut in as_completed(futures):
                        i, t = fut.result()
                        results[i] = t
                        pbar.update(1)
                    pbar.close()

    else:
        # GLM / Ollama engine — batch per request
        eff_batch = min(batch_size, n)
        batches: list[list[int]] = [
            to_run[i : i + eff_batch] for i in range(0, len(to_run), eff_batch)
        ]

        def _run_batch(idx_list: list[int]) -> list[tuple[int, str]]:
            imgs  = [all_pages[i] for i in idx_list]
            texts = ocr_batch(imgs, model=model, jpeg_quality=jpeg_quality)
            pairs = list(zip(idx_list, texts))
            if use_cache:
                for i, t in pairs:
                    _save_cache(cache_dir, i, t)
            return pairs

        if batches:
            if workers == 1:
                pbar = tqdm(total=len(to_run), desc="OCR", unit="page")
                for batch in batches:
                    for i, t in _run_batch(batch):
                        results[i] = t
                    pbar.update(len(batch))
                pbar.close()
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(_run_batch, b): b for b in batches}
                    pbar = tqdm(total=len(to_run), desc="OCR", unit="page")
                    for fut in as_completed(futures):
                        for i, t in fut.result():
                            results[i] = t
                        pbar.update(len(futures[fut]))
                    pbar.close()

    # ── assemble & post-process ───────────────────────────────────────────────
    print("[runner] Post-processing …")
    ordered  = [f"── Page {idx+1} ──\n{results[idx]}" for idx in page_indices]
    raw_text = "\n\n".join(ordered)

    cleaned   = clean_glmocr_output(raw_text)
    corrector = DynamicTableCorrector()
    corrected = corrector.correct_ocr_output(cleaned)
    final     = markdown_tables_to_ascii(corrected)

    out_path.write_text(final, encoding="utf-8")

    elapsed = time.time() - t_start
    mins, secs = divmod(int(elapsed), 60)
    speed = n / elapsed * 60
    print(f"[runner] Done in {mins}m {secs}s  ({speed:.1f} pages/min) | "
          f"{len(final):,} chars → {out_path}")
    if use_cache:
        print(f"[runner] Cache: {cache_dir}")
    return final


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_page_range(s: str) -> tuple[int, int]:
    if "-" in s:
        a, b = s.split("-", 1)
        return int(a.strip()), int(b.strip())
    p = int(s.strip())
    return p, p


def main() -> None:
    ap = argparse.ArgumentParser(
        description="OCR runner — fast, resumable PDF OCR (Tesseract or GLM via Ollama)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("pdf", help="Path to the PDF file")
    ap.add_argument("--out", default=None,
                    help="Output .txt file (default: <pdf_stem>.<engine>.txt)")
    ap.add_argument("--engine", default="glm", choices=["glm", "tesseract"],
                    help="OCR engine: 'tesseract' (fast, CPU) or 'glm' (quality, GPU). Default: glm")
    ap.add_argument("--model", default=MODEL,
                    help=f"Ollama model — glm engine only (default: {MODEL})")
    ap.add_argument("--lang", default="eng",
                    help="Tesseract language code — tesseract engine only (default: eng)")
    ap.add_argument("--dpi", type=int, default=None,
                    help="Page render DPI (default: 120 for glm, 150 for tesseract)")
    ap.add_argument("--workers", type=int, default=None,
                    help="Concurrent workers (default: 2 for glm, 4 for tesseract)")
    ap.add_argument("--batch", type=int, default=4, dest="batch_size",
                    help="Pages per Ollama request — glm engine only (default: 4)")
    ap.add_argument("--jpeg", type=int, default=85, dest="jpeg_quality",
                    help="JPEG quality 1-95 — glm engine only (default: 85)")
    ap.add_argument("--no-cache", action="store_true",
                    help="Disable page cache, reprocess everything")
    ap.add_argument("--cache-dir", default=None,
                    help="Custom cache directory")
    ap.add_argument("--pages", default=None,
                    help="Page range to process, e.g. '1-10' or '5'")
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"[ERROR] PDF not found: {pdf_path}")
        sys.exit(1)

    # Engine-specific defaults
    workers = args.workers if args.workers is not None else (4 if args.engine == "tesseract" else 2)
    dpi     = args.dpi     if args.dpi     is not None else (150 if args.engine == "tesseract" else 120)

    # GLM-only checks
    if args.engine == "glm":
        if not ollama_running():
            print("[ERROR] Ollama is not running.\n  Start with:  ollama serve")
            sys.exit(1)
        if not model_available(args.model):
            available = list_vision_models()
            print(f"[ERROR] Model '{args.model}' not found in Ollama.")
            print(f"  Available: {available}")
            print(f"  Pull with: ollama pull {args.model}")
            sys.exit(1)

    out_path   = Path(args.out) if args.out else pdf_path.with_suffix(f".{args.engine}.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cache_dir  = Path(args.cache_dir) if args.cache_dir else None
    page_range = _parse_page_range(args.pages) if args.pages else None

    print(f"\nOCR Runner")
    print(f"  PDF      : {pdf_path}")
    print(f"  Output   : {out_path}")
    print(f"  Engine   : {args.engine}")
    if args.engine == "glm":
        print(f"  Model    : {args.model}")
        print(f"  Batch    : {args.batch_size} pages/request")
        print(f"  JPEG Q   : {args.jpeg_quality}")
    else:
        print(f"  Lang     : {args.lang}")
    print(f"  DPI      : {dpi}")
    print(f"  Workers  : {workers}")
    print(f"  Cache    : {'off' if args.no_cache else 'on'}")
    if page_range:
        print(f"  Pages    : {page_range[0]}–{page_range[1]}")
    print()

    process_pdf(
        pdf_path     = str(pdf_path),
        out_path     = out_path,
        engine       = args.engine,
        model        = args.model,
        lang         = args.lang,
        dpi          = dpi,
        workers      = workers,
        batch_size   = args.batch_size,
        jpeg_quality = args.jpeg_quality,
        use_cache    = not args.no_cache,
        cache_dir    = cache_dir,
        page_range   = page_range,
    )


if __name__ == "__main__":
    main()
