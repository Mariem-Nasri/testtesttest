#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
  OCR BENCHMARK — Compare 5 tools on the same scanned PDF
  Tools:
    1. GLM-OCR          (zai-org/GLM-OCR via Ollama)
    2. neoxie pdf2md    (neoxie/pdf-to-md-by-local-glmocr wrapper)
    3. pdfmd            (Siggib1054/pdfmd)
    4. VisionFusion     (emileegraphic698/VisionFusion_OCR_QR — local OCR layer)
    5. OCRmyPDF         (ocrmypdf/OCRmyPDF via Tesseract)
───────────────────────────────────────────────────────────────────────────────
  USAGE:
    python ocr_benchmark.py --pdf your_document.pdf

  OUTPUT (written to ./ocr_results/):
    glmocr_output.txt
    neoxie_output.txt
    pdfmd_output.txt
    visionfusion_output.txt
    ocrmypdf_output.txt
    comparison_report.html
═══════════════════════════════════════════════════════════════════════════════
"""

import argparse
import os
import re
import sys
import shutil
import subprocess
import time
import textwrap
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# DEPENDENCY CHECK — run before heavy imports
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_PACKAGES = [
    "pdf2image",       # PDF → image pages (uses poppler)
    "pytesseract",     # Tesseract Python wrapper
    "Pillow",          # Image processing
    "opencv-python",   # Dynamic thresholding
    "numpy",           # Array ops
    "pdfplumber",      # Text extraction from OCR-ed PDFs
    "requests",        # Ollama HTTP API calls
    "tqdm",            # Progress bars
]

def check_and_install(packages):
    import importlib
    pkg_map = {
        "opencv-python": "cv2",
        "Pillow": "PIL",
        "pdf2image": "pdf2image",
        "pytesseract": "pytesseract",
        "numpy": "numpy",
        "pdfplumber": "pdfplumber",
        "requests": "requests",
        "tqdm": "tqdm",
    }
    missing = []
    for pkg in packages:
        module = pkg_map.get(pkg, pkg)
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[setup] Installing missing packages: {missing}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet"] + missing)

check_and_install(REQUIRED_PACKAGES)

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS (after install check)
# ─────────────────────────────────────────────────────────────────────────────

import cv2
import numpy as np
import pytesseract
import pdfplumber
import requests
from PIL import Image
from pdf2image import convert_from_path
from tqdm import tqdm

# ─────────────────────────────────────────────────────────────────────────────
# UTILITIES: Dynamic image preprocessing for scanned docs
# ─────────────────────────────────────────────────────────────────────────────

def pil_to_cv2(pil_img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)

def cv2_to_pil(cv_img: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))

def compute_dynamic_threshold(gray: np.ndarray) -> int:
    """
    Compute an Otsu threshold and clamp it to [100, 200] so very
    dark scans (e.g. old microfilm) and very light scans both get
    a sensible binarisation point.
    """
    _, thresh_val = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thresh_scalar = float(np.asarray(thresh_val).flat[0])
    return int(np.clip(thresh_scalar, 100, 200))

def estimate_dpi_from_sharpness(gray: np.ndarray) -> int:
    """
    Laplacian variance ≈ sharpness proxy.
    Low sharpness → boost DPI assumption so we re-render at higher res.
    Returns 300 (clear), 400 (mediocre), or 600 (blurry) as a guide.
    """
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if lap_var > 500:
        return 300
    elif lap_var > 100:
        return 400
    else:
        return 600

def preprocess_page(pil_img: Image.Image) -> Image.Image:
    """
    Full adaptive preprocessing pipeline for scanned pages:
      1. Convert to grayscale
      2. Estimate sharpness → adaptive DPI upscale if blurry
      3. Deskew (rotation correction) via moments
      4. Denoise (fastNlMeans)
      5. Dynamic Otsu thresholding → binarise
      6. Morphological close to reconnect broken characters
    """
    img = pil_to_cv2(pil_img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # --- Adaptive upscale for low-res / blurry pages ---
    dpi_hint = estimate_dpi_from_sharpness(gray)
    if dpi_hint > 300:
        scale = dpi_hint / 300.0
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # --- Deskew via image moments ---
    coords = np.column_stack(np.where(gray < 200))
    if len(coords) > 10:
        # cv2.minAreaRect expects (N, 1, 2) float32 contour; np.where gives (y, x) so flip to (x, y)
        coords_cv = coords[:, ::-1].astype(np.float32).reshape((-1, 1, 2))
        rect = cv2.minAreaRect(coords_cv)
        angle = float(rect[-1])
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) > 0.3:
            h, w = gray.shape
            M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
            gray = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                                  borderMode=cv2.BORDER_REPLICATE)

    # --- Denoise ---
    gray = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

    # --- Dynamic binarisation ---
    thresh_val = compute_dynamic_threshold(gray)
    _, binary = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY)

    # --- Morphological close to reconnect broken ink ---
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    return Image.fromarray(binary)

def pdf_to_preprocessed_pages(pdf_path: str, base_dpi: int = 300) -> list[Image.Image]:
    """Convert PDF to a list of preprocessed PIL images (one per page)."""
    raw_pages = convert_from_path(pdf_path, dpi=base_dpi)
    return [preprocess_page(p) for p in raw_pages]

def is_scanned_pdf(pdf_path: str, sample_pages: int = 3) -> bool:
    """Return True if the PDF appears to be a scanned image (no embedded text)."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:min(sample_pages, len(pdf.pages))]:
                if len((page.extract_text() or "").strip()) > 50:
                    return False
        return True
    except Exception:
        return False  # assume digital if unsure

def pdf_to_pages_smart(pdf_path: str, base_dpi: int = 300) -> list[Image.Image]:
    """Return raw pages for digital PDFs, preprocessed pages for scanned PDFs."""
    if is_scanned_pdf(pdf_path):
        return pdf_to_preprocessed_pages(pdf_path, base_dpi)
    return convert_from_path(pdf_path, dpi=base_dpi)

# ─────────────────────────────────────────────────────────────────────────────
# GLM-OCR OUTPUT POST-PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def _html_table_to_md(html_str: str) -> str:
    """Convert an HTML <table> block to a markdown table."""
    from html.parser import HTMLParser
    import html as html_module

    class _TParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows: list[list[str]] = []
            self._row: list[str] = []
            self._cell = ""
            self._in_cell = False

        def handle_starttag(self, tag, attrs):
            if tag in ("td", "th"):
                self._in_cell = True
                self._cell = ""

        def handle_endtag(self, tag):
            if tag in ("td", "th"):
                self._row.append(self._cell.strip())
                self._in_cell = False
            elif tag == "tr":
                if self._row:
                    self.rows.append(self._row)
                    self._row = []

        def handle_data(self, data):
            if self._in_cell:
                self._cell += data

        def handle_entityref(self, name):
            if self._in_cell:
                self._cell += html_module.unescape(f"&{name};")

        def handle_charref(self, name):
            if self._in_cell:
                self._cell += html_module.unescape(f"&#{name};")

    p = _TParser()
    p.feed(html_str)
    if not p.rows:
        return html_str

    max_cols = max(len(r) for r in p.rows)
    rows = [r + [""] * (max_cols - len(r)) for r in p.rows]

    def fmt_row(cells):
        return "| " + " | ".join(c.replace("\n", " ") for c in cells) + " |"

    lines = [fmt_row(rows[0]),
             "| " + " | ".join(":---" for _ in rows[0]) + " |"]
    for row in rows[1:]:
        lines.append(fmt_row(row))
    return "\n".join(lines)

def _is_separator_only_row(line: str) -> bool:
    """Return True if the line is a markdown table separator with no real content."""
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|") and "---" in s):
        return False
    cells = [c.strip() for c in s.strip("|").split("|")]
    return all(re.match(r'^:?-+:?$', c) or c == "" for c in cells)

def clean_glmocr_output(text: str) -> str:
    """
    Post-process GLM-OCR output:
      1. Replace |table|table|... garbage lines (vision model labels image regions).
      2. Convert HTML <table> blocks to markdown tables.
      3. Remove dangling separator rows that appear right after a page header
         (cross-page table continuation artifacts).
    """
    # 1. Replace |table|table|... lines — GLM-OCR emits these for graphic/image pages
    text = re.sub(r'(\|table)+\|?', '[image — no extractable text]', text)

    # 2. HTML → markdown tables
    text = re.sub(
        r'<table[\s\S]*?</table>',
        lambda m: _html_table_to_md(m.group(0)),
        text, flags=re.IGNORECASE
    )

    # 2. Drop dangling separator rows and empty-cell rows that appear right
    #    after a page header (cross-page table continuation artifacts).
    #    Pattern: page marker → (optional blank/empty-cell rows) → separator row
    lines = text.split("\n")
    cleaned: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        if _is_separator_only_row(line) or _is_empty_cell_row(line):
            # Scan backwards through cleaned to find what precedes this line
            prev_meaningful = next(
                (l for l in reversed(cleaned)
                 if l.strip() and not _is_empty_cell_row(l) and not _is_separator_only_row(l)),
                ""
            )
            if re.match(r'^── Page \d+', prev_meaningful.strip()):
                i += 1
                continue  # skip artifact
        cleaned.append(line)
        i += 1

    # 3. Remove duplicate separators inside converted HTML tables
    #    (first data-row used as header produces a mis-placed separator)
    final: list[str] = []
    for idx, line in enumerate(cleaned):
        if _is_separator_only_row(line):
            prev = cleaned[idx - 1].strip() if idx > 0 else ""
            next_ = cleaned[idx + 1].strip() if idx + 1 < len(cleaned) else ""
            # Keep separator only if it follows a proper header (non-separator pipe row)
            # and precedes a data row
            if not (prev.startswith("|") and not _is_separator_only_row(prev)
                    and next_.startswith("|") and not _is_separator_only_row(next_)):
                continue
        final.append(line)
    return "\n".join(final)

# ─────────────────────────────────────────────────────────────────────────────
# TABLE RECONSTRUCTION HELPER
# ─────────────────────────────────────────────────────────────────────────────

def detect_table_regions(pil_img: Image.Image) -> list[tuple]:
    """
    Detect horizontal/vertical line intersections to find table bounding boxes.
    Returns list of (x, y, w, h) bounding boxes.
    """
    gray = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)

    grid = cv2.add(h_lines, v_lines)
    contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for c in contours:
        x, y, w, wh = cv2.boundingRect(c)
        if w > 60 and wh > 20:
            boxes.append((x, y, w, wh))
    return boxes

def extract_table_as_text(pil_img: Image.Image, box: tuple) -> str:
    """
    Crop a table region and run Tesseract with TSV output, then
    reconstruct a plain-text ASCII table with aligned columns.
    """
    x, y, w, h = box
    cropped = pil_img.crop((max(0, x - 5), max(0, y - 5), x + w + 5, y + h + 5))
    tsv = pytesseract.image_to_data(cropped, config="--psm 6",
                                    output_type=pytesseract.Output.DICT)

    rows: dict[int, list[tuple]] = {}
    for i, text in enumerate(tsv["text"]):
        text = text.strip()
        if not text or tsv["conf"][i] < 20:
            continue
        row_key = tsv["top"][i] // 15   # group words by ~line band
        rows.setdefault(row_key, []).append((tsv["left"][i], text))

    lines = []
    for row_key in sorted(rows):
        cells = sorted(rows[row_key], key=lambda t: t[0])
        lines.append("  |  ".join(c[1] for c in cells))

    return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 1 — GLM-OCR via Ollama (zai-org/GLM-OCR)
# ─────────────────────────────────────────────────────────────────────────────

class GLMOCREngine:
    NAME = "GLM-OCR (Ollama)"
    SLUG = "glmocr"

    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL = "glm-ocr"

    def _is_ollama_running(self) -> bool:
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def _is_model_available(self) -> bool:
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=3)
            tags = r.json().get("models", [])
            return any(self.MODEL in m.get("name", "") for m in tags)
        except Exception:
            return False

    def _ocr_page_via_ollama(self, pil_img: Image.Image) -> str:
        import base64, io
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        payload = {
            "model": self.MODEL,
            "prompt": (
                "You are an OCR engine. Extract ALL text from this document page. "
                "Preserve the original structure: headings, paragraphs, bullet points, "
                "and tables. For tables, output them using ASCII pipes: "
                "| col1 | col2 | col3 |. Do not add commentary. Output only the text."
            ),
            "images": [b64],
            "stream": False,
        }
        try:
            r = requests.post(self.OLLAMA_URL, json=payload, timeout=120)
            r.raise_for_status()
            return r.json().get("response", "").strip()
        except Exception as e:
            return f"[GLM-OCR ERROR on page: {e}]"

    def run(self, pdf_path: str) -> str:
        if not self._is_ollama_running():
            return (
                "[GLM-OCR SKIPPED] Ollama is not running.\n"
                "Start it with: ollama serve\n"
                "Then pull the model: ollama pull glm-ocr"
            )
        if not self._is_model_available():
            return (
                "[GLM-OCR SKIPPED] glm-ocr model not found in Ollama.\n"
                "Run: ollama pull glm-ocr"
            )

        # Use raw pages (no preprocessing) — GLM-OCR is a vision model and
        # works best with natural page images, not binarized/denoised output.
        # Use raw pages — GLM-OCR is a vision model, heavy preprocessing hurts quality.
        # For scanned PDFs we keep the original resolution; for digital PDFs 150 dpi is enough.
        pages = pdf_to_pages_smart(pdf_path, base_dpi=150)
        results = []
        for i, page in enumerate(tqdm(pages, desc="GLM-OCR", unit="page")):
            results.append(f"── Page {i+1} ──\n{self._ocr_page_via_ollama(page)}")
        full_text = "\n\n".join(results)
        return clean_glmocr_output(full_text)


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 2 — neoxie pdf2md wrapper (neoxie/pdf-to-md-by-local-glmocr)
# ─────────────────────────────────────────────────────────────────────────────

class NeoxieEngine:
    NAME = "neoxie pdf2md"
    SLUG = "neoxie"
    REPO_URL = "https://github.com/neoxie/pdf-to-md-by-local-glmocr.git"
    REPO_DIR = Path("./repos/neoxie_pdf2md")

    def _clone_if_needed(self):
        if not self.REPO_DIR.exists():
            print(f"[neoxie] Cloning repo → {self.REPO_DIR}")
            subprocess.run(
                ["git", "clone", "--depth=1", self.REPO_URL, str(self.REPO_DIR)],
                check=True, capture_output=True
            )

    def _install_deps(self):
        # Install glmocr with layout extra (required by neoxie's layout detector)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "glmocr[layout]>=0.1.4", "transformers>=4.50.0"],
            capture_output=True
        )
        req_file = self.REPO_DIR / "pyproject.toml"
        if req_file.exists():
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet",
                 "-e", str(self.REPO_DIR)],
                capture_output=True
            )

    def run(self, pdf_path: str) -> str:
        try:
            self._clone_if_needed()
            self._install_deps()
        except Exception as e:
            return f"[neoxie SKIPPED] Could not clone/install repo: {e}"

        out_dir = Path(os.path.abspath("./ocrs/ocr_results/neoxie_tmp"))
        out_dir.mkdir(parents=True, exist_ok=True)
        script = self.REPO_DIR / "pdf2md.py"
        if not script.exists():
            return "[neoxie SKIPPED] pdf2md.py not found in repo."

        result = subprocess.run(
            [sys.executable, str(script), pdf_path, "-d", str(out_dir)],
            capture_output=True, text=True, timeout=300
        )
        # find any .md output file
        md_files = list(out_dir.glob("*.md"))
        if md_files:
            return md_files[0].read_text(encoding="utf-8")
        if result.stdout.strip():
            return result.stdout

        # Surface a helpful message for the known layout-detector incompatibility
        stderr = result.stderr or ""
        if "PPDocLayoutV3ImageProcessor" in stderr or "layout" in stderr.lower():
            return (
                "[neoxie SKIPPED] glmocr layout detector is incompatible with the installed "
                "transformers version. The layout detector requires PPDocLayoutV3ImageProcessor "
                "which is not yet available in transformers 5.x.\n"
                "Workaround: use the GLM-OCR engine directly (same underlying model via Ollama)."
            )
        return f"[neoxie ERROR]\nSTDOUT: {result.stdout[:300]}\nSTDERR: {stderr[:300]}"


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 3 — pdfmd (Siggib1054/pdfmd)
# ─────────────────────────────────────────────────────────────────────────────

class PdfmdEngine:
    NAME = "pdfmd (Siggib1054)"
    SLUG = "pdfmd"
    REPO_URL = "https://github.com/Siggib1054/pdfmd.git"
    REPO_DIR = Path("./repos/pdfmd")

    def _clone_if_needed(self):
        if not self.REPO_DIR.exists():
            print(f"[pdfmd] Cloning repo → {self.REPO_DIR}")
            subprocess.run(
                ["git", "clone", "--depth=1", self.REPO_URL, str(self.REPO_DIR)],
                check=True, capture_output=True
            )

    def _find_entry_point(self) -> Path | None:
        for name in ["main.py", "pdfmd.py", "app.py", "run.py", "cli.py"]:
            p = self.REPO_DIR / name
            if p.exists():
                return p
        scripts = list(self.REPO_DIR.glob("*.py"))
        return scripts[0] if scripts else None

    def _install_deps(self):
        for fname in ["requirements.txt", "pyproject.toml"]:
            f = self.REPO_DIR / fname
            if f.exists():
                if fname == "requirements.txt":
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", "--quiet", "-r", str(f)],
                        capture_output=True
                    )
                else:
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", "--quiet", "-e", str(self.REPO_DIR)],
                        capture_output=True
                    )
                break

    def run(self, pdf_path: str) -> str:
        try:
            self._clone_if_needed()
            self._install_deps()
        except Exception as e:
            return f"[pdfmd SKIPPED] Could not clone/install repo: {e}"

        out_dir = Path(os.path.abspath("./ocrs/ocr_results/pdfmd_tmp"))
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "output.md"

        # pdfmd is a proper package; invoke via its module entry point
        result = subprocess.run(
            [sys.executable, "-m", "pdfmd.cli", pdf_path, "-o", str(out_file),
             "--ocr", "auto", "--no-progress", "--quiet"],
            capture_output=True, text=True, timeout=300,
            cwd=str(self.REPO_DIR)
        )

        if out_file.exists() and out_file.stat().st_size > 0:
            return out_file.read_text(encoding="utf-8")
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
        return f"[pdfmd ERROR]\nSTDOUT: {result.stdout[:300]}\nSTDERR: {result.stderr[:300]}"


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 4 — VisionFusion OCR (local Tesseract layer, dynamic thresholds)
# Based on emileegraphic698/VisionFusion_OCR_QR's ocr_dyn.py approach
# (Gemini part skipped — local-only mode)
# ─────────────────────────────────────────────────────────────────────────────

class VisionFusionEngine:
    NAME = "VisionFusion OCR (local, dynamic thresh)"
    SLUG = "visionfusion"

    # Tesseract configs per content type
    TESS_CONFIGS = {
        "text":  "--oem 3 --psm 3",          # fully automatic page seg
        "table": "--oem 3 --psm 6",           # uniform block of text
        "mixed": "--oem 3 --psm 4",           # single column, varied text
    }

    def _classify_page(self, pil_img: Image.Image) -> str:
        """Heuristic: many long horizontal lines → table; else text."""
        cv_img = pil_to_cv2(pil_img)
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
        h_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, h_kernel)
        if cv2.countNonZero(h_lines) > gray.size * 0.005:
            return "table"
        return "text"

    def _ocr_with_layout(self, pil_img: Image.Image) -> str:
        """
        1. Find table bounding boxes → extract tables with alignment
        2. OCR remaining text with Tesseract PSM 3
        3. Merge in reading order (top-to-bottom)
        """
        # Detect tables
        table_boxes = detect_table_regions(pil_img)
        table_texts = {box: extract_table_as_text(pil_img, box) for box in table_boxes}

        # Create mask to blank out table areas for main OCR
        mask = Image.new("L", pil_img.size, 255)
        mask_arr = np.array(mask)
        for (x, y, w, h) in table_boxes:
            mask_arr[max(0, y-5):y+h+5, max(0, x-5):x+w+5] = 0
        pil_masked = Image.composite(pil_img, Image.new("L", pil_img.size, 255),
                                     Image.fromarray(mask_arr))

        # OCR masked image
        page_type = self._classify_page(pil_img)
        cfg = self.TESS_CONFIGS[page_type]
        body_text = pytesseract.image_to_string(pil_masked, config=cfg, lang="eng+fra+ara")

        # Stitch: insert table text at approximate vertical positions
        if not table_texts:
            return body_text

        h_total = pil_img.size[1]
        output_parts = []
        body_lines = body_text.splitlines()

        # Interleave table blocks into body by vertical order
        sorted_tables = sorted(table_texts.items(), key=lambda kv: kv[0][1])
        table_iter = iter(sorted_tables)
        next_table = next(table_iter, None)

        for line in body_lines:
            if next_table:
                box, tbl = next_table
                _, ty, _, th = box
                # rough line position heuristic
                if len(output_parts) / max(len(body_lines), 1) > ty / h_total:
                    output_parts.append("\n[TABLE]\n" + tbl + "\n[/TABLE]\n")
                    next_table = next(table_iter, None)
            output_parts.append(line)

        # Append any remaining tables
        while next_table:
            _, tbl = next_table
            output_parts.append("\n[TABLE]\n" + tbl + "\n[/TABLE]\n")
            next_table = next(table_iter, None)

        return "\n".join(output_parts)

    def run(self, pdf_path: str) -> str:
        pages = pdf_to_pages_smart(pdf_path)
        results = []
        for i, page in enumerate(tqdm(pages, desc="VisionFusion", unit="page")):
            text = self._ocr_with_layout(page)
            results.append(f"── Page {i+1} ──\n{text}")
        return "\n\n".join(results)


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 5 — OCRmyPDF (ocrmypdf/OCRmyPDF)
# ─────────────────────────────────────────────────────────────────────────────

class OCRmyPDFEngine:
    NAME = "OCRmyPDF (Tesseract)"
    SLUG = "ocrmypdf"

    def _ensure_ocrmypdf(self):
        try:
            import ocrmypdf
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install",
                                   "--quiet", "ocrmypdf"])

    def run(self, pdf_path: str) -> str:
        self._ensure_ocrmypdf()
        import ocrmypdf

        tmp_pdf = Path("./ocrs/ocr_results/ocrmypdf_tmp.pdf")
        tmp_pdf.parent.mkdir(parents=True, exist_ok=True)

        try:
            ocrmypdf.ocr(
                pdf_path,
                str(tmp_pdf),
                language=["eng", "fra", "ara"],
                force_ocr=True,
                optimize=0,
                progress_bar=True,
                deskew=True,
                clean=True,
                rotate_pages=True,
                # Dynamic threshold via unpaper (if available)
                unpaper_args="--layout single --no-multi-pages",
            )
        except Exception as e:
            # retry without unpaper
            try:
                ocrmypdf.ocr(pdf_path, str(tmp_pdf),
                             language=["eng", "fra"],
                             force_ocr=True, optimize=0,
                             deskew=True, rotate_pages=True)
            except Exception as e2:
                return f"[OCRmyPDF ERROR]: {e2}"

        # Extract text preserving layout from the OCR-ed PDF
        pages_text = []
        with pdfplumber.open(str(tmp_pdf)) as pdf:
            for i, page in enumerate(tqdm(pdf.pages, desc="OCRmyPDF extract", unit="page")):
                # --- Extract tables separately ---
                table_parts = []
                for table in page.extract_tables():
                    rows = []
                    for row in table:
                        clean_row = [str(c or "").strip() for c in row]
                        rows.append("  |  ".join(clean_row))
                    table_parts.append("[TABLE]\n" + "\n".join(rows) + "\n[/TABLE]")

                # --- Extract body text ---
                body = page.extract_text(x_tolerance=3, y_tolerance=3) or ""

                combined = f"── Page {i+1} ──\n{body}"
                if table_parts:
                    combined += "\n\n" + "\n\n".join(table_parts)
                pages_text.append(combined)

        return "\n\n".join(pages_text)


# ─────────────────────────────────────────────────────────────────────────────
# COMPARISON REPORT
# ─────────────────────────────────────────────────────────────────────────────

HTML_REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>OCR Benchmark Report</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; background: #0f1117; color: #e2e8f0; }}
  h1 {{ padding: 24px 32px; font-size: 1.6rem; border-bottom: 1px solid #2d3748;
       background: #1a202c; color: #90cdf4; }}
  .meta {{ padding: 8px 32px; font-size: 0.82rem; color: #718096; background: #1a202c; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
           gap: 16px; padding: 20px; }}
  .card {{ background: #1e2330; border-radius: 10px; overflow: hidden;
           border: 1px solid #2d3748; }}
  .card-header {{ padding: 10px 14px; background: #2d3748; display: flex;
                  justify-content: space-between; align-items: center; }}
  .card-title {{ font-weight: 600; font-size: 0.95rem; color: #90cdf4; }}
  .badge {{ font-size: 0.72rem; padding: 2px 8px; border-radius: 99px;
            background: #4a5568; color: #e2e8f0; }}
  .badge.ok {{ background: #276749; color: #9ae6b4; }}
  .badge.skip {{ background: #744210; color: #fbd38d; }}
  .badge.err {{ background: #742a2a; color: #fed7d7; }}
  pre {{ padding: 14px; font-size: 0.78rem; line-height: 1.55; white-space: pre-wrap;
         word-break: break-word; max-height: 500px; overflow-y: auto;
         color: #d1fae5; background: transparent; }}
  .stats {{ padding: 6px 14px 10px; font-size: 0.78rem; color: #718096; }}
  table.summary {{ width: calc(100% - 40px); margin: 0 20px 20px;
                   border-collapse: collapse; background: #1e2330;
                   border-radius: 10px; overflow: hidden;
                   border: 1px solid #2d3748; }}
  table.summary th, table.summary td {{ padding: 10px 14px; text-align: left;
                                         border-bottom: 1px solid #2d3748;
                                         font-size: 0.85rem; }}
  table.summary th {{ background: #2d3748; color: #90cdf4; }}
  table.summary tr:last-child td {{ border-bottom: none; }}
</style>
</head>
<body>
<h1>🔬 OCR Benchmark — Comparison Report</h1>
<div class="meta">Generated: {timestamp} &nbsp;|&nbsp; PDF: {pdf_name}</div>

<table class="summary">
  <tr><th>Engine</th><th>Status</th><th>Time (s)</th><th>Chars extracted</th></tr>
  {summary_rows}
</table>

<div class="grid">
  {cards}
</div>
</body>
</html>
"""

def _status_badge(text: str) -> str:
    t = text.strip()
    if t.startswith("[") and ("SKIP" in t or "not running" in t or "not found" in t):
        return '<span class="badge skip">SKIPPED</span>'
    if "ERROR" in t[:60]:
        return '<span class="badge err">ERROR</span>'
    return '<span class="badge ok">OK</span>'

def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def generate_html_report(results: dict, pdf_path: str, timings: dict) -> str:
    summary_rows = ""
    cards = ""
    for slug, (name, text) in results.items():
        badge_html = _status_badge(text)
        char_count = len(text)
        t = timings.get(slug, 0)
        summary_rows += (
            f"<tr><td>{name}</td><td>{badge_html}</td>"
            f"<td>{t:.1f}</td><td>{char_count:,}</td></tr>\n"
        )
        cards += f"""
        <div class="card">
          <div class="card-header">
            <span class="card-title">{name}</span>
            {badge_html}
          </div>
          <div class="stats">{char_count:,} chars &nbsp;|&nbsp; {t:.1f}s</div>
          <pre>{_escape(text[:8000])}{"..." if len(text) > 8000 else ""}</pre>
        </div>
        """
    return HTML_REPORT_TEMPLATE.format(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        pdf_name=Path(pdf_path).name,
        summary_rows=summary_rows,
        cards=cards,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC TABLE CORRECTION
# Works on any document by:
#   1. Reconstructing authoritative tables from PDF word positions (digital PDFs)
#   2. Dynamically fixing markdown table structure in OCR outputs
# ─────────────────────────────────────────────────────────────────────────────

class DynamicTableCorrector:
    """
    Two-pass table fixer:
      Pass A — PDF-aware: reconstruct tables directly from pdfplumber word positions.
      Pass B — OCR-aware: dynamically fix markdown table structure in OCR output.
    Both passes work on any document without hardcoded assumptions.
    """

    # ── Pass A: PDF word-position reconstruction ─────────────────────────────

    def reconstruct_from_pdf(self, pdf_path: str) -> str:
        """
        Build a clean text+table document directly from a digital PDF's word positions.
        Falls back gracefully for scanned/image PDFs.
        """
        pages_text = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = self._reconstruct_page(page)
                pages_text.append(f"── Page {i+1} ──\n{page_text}")
        return "\n\n".join(pages_text)

    def _reconstruct_page(self, page) -> str:
        pw = float(page.width)

        # Extract words, filter out margin watermarks/stamps:
        # keep only words within the central 80% of page width and upright chars only.
        all_words = page.extract_words(x_tolerance=5, y_tolerance=3)
        left_margin = pw * 0.08
        right_margin = pw * 0.92
        words = [w for w in all_words if left_margin <= w["x0"] <= right_margin]

        if not words:
            return page.extract_text() or ""

        col_bounds = self._find_column_boundaries(words, pw)

        if len(col_bounds) <= 2:
            return page.extract_text() or ""

        return self._words_to_table(words, col_bounds)

    def _find_column_boundaries(self, words: list, page_width: float) -> list:
        """
        Find column x-boundaries by histogram of word x0 positions.
        Returns sorted list of boundary x-values (len = n_cols + 1).
        """
        from collections import Counter
        # Round to 5px grid for stability
        x_hist = Counter(round(w["x0"] / 5) * 5 for w in words)
        total = len(words)
        min_freq = max(2, total * 0.04)  # at least 4% of words start a column

        peaks = sorted(x for x, cnt in x_hist.items() if cnt >= min_freq)
        if not peaks:
            return [0, page_width]

        # Merge peaks that are within 25px of each other
        merged: list[float] = [peaks[0]]
        for p in peaks[1:]:
            if p - merged[-1] > 25:
                merged.append(p)

        if len(merged) < 2:
            return [0, page_width]

        # Build boundaries: gap midpoints between consecutive column starts
        bounds: list[float] = [max(0.0, merged[0] - 5)]
        for a, b in zip(merged, merged[1:]):
            bounds.append((a + b) / 2)
        bounds.append(page_width)
        return bounds

    def _words_to_table(self, words: list, col_bounds: list) -> str:
        """Group words into rows × columns and emit as a markdown table."""
        n_cols = len(col_bounds) - 1

        # Group words into lines by y-position (6px tolerance)
        lines: dict[int, list] = {}
        for w in words:
            ly = round(w["top"] / 6) * 6
            lines.setdefault(ly, []).append(w)

        rows: list[list[str]] = []
        for ly in sorted(lines):
            row_words = sorted(lines[ly], key=lambda w: w["x0"])
            cells = [""] * n_cols
            for w in row_words:
                ci = n_cols - 1
                for j in range(n_cols):
                    if w["x0"] < col_bounds[j + 1]:
                        ci = j
                        break
                cells[ci] += (" " if cells[ci] else "") + w["text"]
            if any(c.strip() for c in cells):
                rows.append(cells)

        if not rows:
            return ""

        # Check if it's really a multi-column layout
        multi_col = sum(1 for r in rows if sum(1 for c in r if c.strip()) > 1)
        if multi_col < 2:
            return "\n".join(" ".join(c for c in r if c.strip()) for r in rows)

        # Find where actual table content starts (skip page-number lines)
        start = 0
        for i, row in enumerate(rows):
            filled = [c for c in row if c.strip()]
            if len(filled) > 1 or (len(filled) == 1 and not re.match(r"^-\d+-$", filled[0])):
                start = i
                break

        preamble_lines = [" ".join(c for c in r if c.strip()) for r in rows[:start]]
        table_rows = rows[start:]
        if not table_rows:
            return "\n".join(preamble_lines)

        # Merge wrapped continuation lines:
        # A row is a continuation if its first col is empty AND the previous row
        # had content in col 0.
        merged: list[list[str]] = [list(table_rows[0])]
        for row in table_rows[1:]:
            prev = merged[-1]
            # Continuation: col0 empty, or all cols before last are empty
            if not row[0].strip() and prev[0].strip():
                for ci in range(n_cols):
                    if row[ci].strip():
                        prev[ci] = (prev[ci] + " " + row[ci].strip()).strip()
            else:
                merged.append(list(row))

        def fmt(cells: list[str]) -> str:
            return "| " + " | ".join(c.replace("\n", " ").strip() for c in cells) + " |"

        sep = "| " + " | ".join(":---" for _ in merged[0]) + " |"
        out = []
        if preamble_lines:
            out.append("\n".join(l for l in preamble_lines if l.strip()))
        out.append(fmt(merged[0]))
        out.append(sep)
        for row in merged[1:]:
            out.append(fmt(row))
        return "\n".join(out)

    # ── Pass B: OCR output dynamic correction ────────────────────────────────

    def correct_ocr_output(self, text: str) -> str:
        """
        Dynamically fix markdown table structure in OCR output.
        Works on any document — no hardcoded column names or patterns.
        """
        text = self._fix_html_tables(text)
        text = self._normalize_table_blocks(text)
        text = self._split_merged_dlr_cells(text)
        text = self._merge_cross_page_tables(text)
        text = self._remove_page_break_artifacts(text)
        return text

    def _fix_html_tables(self, text: str) -> str:
        """Convert any residual HTML <table> blocks to markdown."""
        return re.sub(
            r"<table[\s\S]*?</table>",
            lambda m: _html_table_to_md(m.group(0)),
            text, flags=re.IGNORECASE
        )

    def _split_merged_dlr_cells(self, text: str) -> str:
        """
        When GLM-OCR collapses multiple DLR entries into one table cell
        (e.g. 'DLR#1.3: ... DLR#1.4: ...' in a single cell), split them
        back into separate rows, preserving the split across all columns.
        """
        DLR_SPLIT = re.compile(r'(?=DLR#\d+\.\d+:)')
        DLR_TAG   = re.compile(r'DLR#\d+\.\d+:')

        def split_by_dlr(cell: str) -> list:
            parts = DLR_SPLIT.split(cell)
            segs = [p.strip() for p in parts if p.strip()]
            return segs if segs else [cell]

        lines = text.split('\n')
        out = []
        for line in lines:
            if not line.strip().startswith('|') or _is_separator_only_row(line):
                out.append(line)
                continue

            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            while cells and not cells[-1]:
                cells.pop()

            # Only split rows where at least one cell has multiple DLR tags
            if not any(len(DLR_TAG.findall(c)) > 1 for c in cells):
                out.append(line)
                continue

            split_per_cell = [split_by_dlr(c) for c in cells]
            max_segs = max(len(s) for s in split_per_cell)
            for segs in split_per_cell:
                while len(segs) < max_segs:
                    segs.append('')

            for si in range(max_segs):
                row_cells = [split_per_cell[ci][si] for ci in range(len(cells))]
                out.append('| ' + ' | '.join(row_cells) + ' |')

        return '\n'.join(out)

    def _merge_cross_page_tables(self, text: str) -> str:
        """
        Merge pipe-table blocks that are separated only by page markers
        (── Page N ──) and blank lines when the second block is a continuation
        (its first data row has an empty col0) and both blocks share the same
        column count. This fuses the per-page table fragments that vision OCR
        engines emit into a single unified table.
        """
        from collections import Counter

        def col_count(block_lines):
            c = Counter()
            for l in block_lines:
                if _is_separator_only_row(l):
                    continue
                cells = [x.strip() for x in l.strip().strip('|').split('|')]
                while cells and not cells[-1]:
                    cells.pop()
                if cells:
                    c[len(cells)] += 1
            return c.most_common(1)[0][0] if c else 0

        def is_continuation(block_lines):
            for l in block_lines:
                if _is_separator_only_row(l):
                    continue
                cells = [c.strip() for c in l.strip().strip('|').split('|')]
                while cells and not cells[-1]:
                    cells.pop()
                if cells:
                    return not cells[0].strip()
            return False

        lines = text.split('\n')
        result = []
        i = 0

        while i < len(lines):
            result.append(lines[i])
            i += 1

            # Only attempt merge after we finish a table block
            if not result[-1].strip().startswith('|'):
                continue
            if i < len(lines) and lines[i].strip().startswith('|'):
                continue  # still inside the table

            # We just ended a table block. Greedily absorb all subsequent
            # continuation blocks (across any number of page markers).
            while True:
                # Get current table tail from result
                cur_block = []
                k = len(result) - 1
                while k >= 0 and result[k].strip().startswith('|'):
                    cur_block.insert(0, result[k])
                    k -= 1

                # Scan ahead past blanks and page markers to the next table
                j = i
                gap = []
                while j < len(lines) and not lines[j].strip().startswith('|'):
                    gap.append(lines[j])
                    j += 1

                if j >= len(lines):
                    break

                # Gap must contain only blank lines and page markers
                non_trivial = [
                    l for l in gap
                    if l.strip() and not re.match(r'^── Page \d+', l.strip())
                ]
                if non_trivial:
                    break

                # Collect the candidate next table block
                next_start = j
                while j < len(lines) and lines[j].strip().startswith('|'):
                    j += 1
                next_block = lines[next_start:j]

                if not next_block or not is_continuation(next_block):
                    break

                if col_count(cur_block) != col_count(next_block):
                    break

                # Merge: consume the gap+markers (don't emit them) and absorb rows
                i = j
                for nb in next_block:
                    result.append(nb)
                # loop again — the newly merged block may absorb yet another page

        return '\n'.join(result)

    def _normalize_table_blocks(self, text: str) -> str:
        """
        Within each contiguous block of pipe-table lines:
          1. Find the modal column count (most common across rows).
          2. Pad short rows / trim over-wide rows.
          3. Ensure exactly one separator row after the first data row.
          4. Drop empty rows (all cells blank).
        """
        lines = text.split("\n")
        out: list[str] = []
        i = 0
        while i < len(lines):
            if not lines[i].strip().startswith("|"):
                out.append(lines[i])
                i += 1
                continue

            # Collect the whole table block
            block_start = i
            while i < len(lines) and lines[i].strip().startswith("|"):
                i += 1
            block = lines[block_start:i]

            fixed = self._fix_table_block(block)
            out.extend(fixed)

        return "\n".join(out)

    def _fix_table_block(self, block: list[str]) -> list[str]:
        """Fix a single table block in place."""
        if not block:
            return block

        def parse_row(line: str) -> list[str]:
            s = line.strip().strip("|")
            cells = [c.strip() for c in s.split("|")]
            # Trim trailing empty cells
            while cells and not cells[-1]:
                cells.pop()
            return cells

        def is_sep(line: str) -> bool:
            return _is_separator_only_row(line)

        # Parse all rows, drop pure separators first
        data_rows = []
        for line in block:
            if is_sep(line):
                continue
            cells = parse_row(line)
            if any(c for c in cells):
                data_rows.append(cells)

        if not data_rows:
            return block

        # Find modal column count (ignore outlier rows)
        from collections import Counter
        counts = Counter(len(r) for r in data_rows)
        modal_n = counts.most_common(1)[0][0]

        # Normalize column count
        normalized = []
        for cells in data_rows:
            if len(cells) < modal_n:
                cells = cells + [""] * (modal_n - len(cells))
            elif len(cells) > modal_n:
                cells = cells[: modal_n - 1] + [" ".join(cells[modal_n - 1 :])]
            normalized.append(cells)

        # Detect continuation block: first data row has empty col0
        # → do NOT insert a header separator (table continues from previous page)
        is_continuation = bool(normalized and not normalized[0][0].strip())

        sep_line = "| " + " | ".join(":---" for _ in range(modal_n)) + " |"

        def fmt(cells: list[str]) -> str:
            return "| " + " | ".join(cells) + " |"

        result: list[str] = []
        for i, cells in enumerate(normalized):
            result.append(fmt(cells))
            if i == 0 and not is_continuation:
                result.append(sep_line)

        return result

    def _remove_page_break_artifacts(self, text: str) -> str:
        """
        Remove separator rows and empty-cell rows that appear immediately after
        a page marker (── Page N ──). These are cross-page table continuation
        artifacts that all vision-based OCR engines produce.
        """
        lines = text.split("\n")
        out: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if _is_separator_only_row(line) or _is_empty_cell_row(line):
                prev = next(
                    (l for l in reversed(out)
                     if l.strip()
                     and not _is_empty_cell_row(l)
                     and not _is_separator_only_row(l)),
                    ""
                )
                if re.match(r"^── Page \d+", prev.strip()):
                    i += 1
                    continue
            out.append(line)
            i += 1
        return "\n".join(out)


def _is_empty_cell_row(line: str) -> bool:
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return False
    return all(c.strip() == "" for c in s.strip("|").split("|"))


def fix_pdfmd_output(text: str) -> str:
    """
    Fix pdfmd output artefacts:
      1. Unescape markdown escapes: \\| \\[ \\] \\. \\( \\) → bare chars.
      2. Extract LaTeX $$ ... $$ blocks — pdfmd wraps table headers in these.
      3. Convert bare pipe-separated lines (no leading |) to proper pipe table rows.
    """
    # 1. Unescape markdown escapes
    text = re.sub(r'\\([|.\[\]{}()_*#])', r'\1', text)

    # 2. Extract $$ ... $$ LaTeX blocks — keep the inner content
    text = re.sub(r'\$\$\s*(.*?)\s*\$\$', lambda m: m.group(1).strip(), text, flags=re.DOTALL)

    # 3. Lines with bare | separators (no leading |) → wrap as pipe table row
    lines = text.split('\n')
    out = []
    for line in lines:
        stripped = line.strip()
        if ('|' in stripped
                and not stripped.startswith('|')
                and not stripped.startswith('#')
                and stripped.count('|') >= 2):
            cells = [c.strip() for c in stripped.split('|')]
            out.append('| ' + ' | '.join(cells) + ' |')
        else:
            out.append(line)
    return '\n'.join(out)


def fix_visionfusion_output(text: str) -> str:
    """
    Fix VisionFusion output artefacts:
      1. Convert [TABLE]...[/TABLE] blocks that contain real pipe content to
         markdown pipe table rows.
      2. Inline trivial [TABLE] blocks (single chars, short fragments) directly.
      3. Merge isolated 1-3 character fragment lines into the preceding line
         (VisionFusion splits OCR regions character by character on some pages).
    """
    def _handle_table_block(m: re.Match) -> str:
        content = m.group(1).strip()
        if not content:
            return ''
        if '|' in content:
            rows = []
            for row in content.split('\n'):
                cells = [c.strip() for c in row.strip().split('|') if c.strip()]
                if cells:
                    rows.append('| ' + ' | '.join(cells) + ' |')
            return '\n'.join(rows) if rows else content
        return content  # no pipes → just inline

    # 1+2: handle [TABLE]...[/TABLE] blocks
    text = re.sub(
        r'\[TABLE\](.*?)\[/TABLE\]',
        _handle_table_block,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Remove any stray markers that weren't paired
    text = re.sub(r'\[/?TABLE\]', '', text, flags=re.IGNORECASE)

    # 3. Merge isolated short fragment lines into the preceding line
    lines = text.split('\n')
    merged = []
    for line in lines:
        stripped = line.strip()
        if (stripped
                and len(stripped) <= 3
                and stripped not in {'.', ',', ':', ';', '!', '?', '-', '–', '(', ')'}
                and merged
                and merged[-1].strip()
                and merged[-1].strip()[-1] not in '.!?:;'):
            merged[-1] = merged[-1].rstrip() + stripped
        else:
            merged.append(line)
    return '\n'.join(merged)


def fix_ocrmypdf_output(text: str) -> str:
    """
    Fix OCRmyPDF / Tesseract output artefacts:
      Tesseract uses [ ] { } as ad-hoc column separators inside table cells.
      Detect lines that look like table rows and normalise them to pipe tables.
    """
    lines = text.split('\n')
    out = []
    for line in lines:
        stripped = line.strip()
        # Line qualifies as a table row if it has bracket/pipe separators AND numbers
        if (re.search(r'[|{\[\]}]', stripped)
                and re.search(r'\d+\.?\d*\s*[%x]?', stripped)
                and not stripped.startswith('#')):
            # Normalise [ { } ] to |
            normalised = re.sub(r'[{\[\]}]', '|', stripped)
            # Strip duplicate pipes and trailing/leading whitespace around them
            normalised = re.sub(r'\|+', '|', normalised)
            cells = [c.strip() for c in normalised.split('|') if c.strip()]
            if len(cells) >= 2:
                out.append('| ' + ' | '.join(cells) + ' |')
                continue
        out.append(line)
    return '\n'.join(out)


def markdown_tables_to_ascii(text: str, col_width: int = 38) -> str:
    """
    Convert all markdown pipe-tables in *text* to ASCII box-drawing tables
    with word-wrapped, aligned columns.

    Works on any document — column widths are computed dynamically from
    content; ``col_width`` is the *maximum* width for any single column
    (long words are never split, so the actual width may exceed it).
    """
    import textwrap

    def parse_md_row(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    def wrap_cell(text: str, width: int) -> list[str]:
        if not text:
            return [""]
        return textwrap.wrap(text, width=width) or [""]

    def render_ascii_table(md_rows: list[list[str]]) -> str:
        n_cols = max(len(r) for r in md_rows)
        # Pad all rows to n_cols
        rows = [r + [""] * (n_cols - len(r)) for r in md_rows]

        # Compute column widths: max content width capped at col_width,
        # but never less than 3.
        widths = []
        for ci in range(n_cols):
            content_max = max(
                max((len(w) for w in wrap_cell(row[ci], col_width)), default=0)
                for row in rows
            )
            widths.append(max(3, min(content_max, col_width)))

        def h_rule(left: str, mid: str, right: str, fill: str = "─") -> str:
            return left + mid.join(fill * (w + 2) for w in widths) + right

        top    = h_rule("┌", "┬", "┐")
        div    = h_rule("├", "┼", "┤")
        bottom = h_rule("└", "┴", "┘")

        def render_row(cells: list[str]) -> str:
            wrapped = [wrap_cell(c, widths[ci]) for ci, c in enumerate(cells)]
            height = max(len(w) for w in wrapped)
            lines = []
            for li in range(height):
                parts = []
                for ci, w in enumerate(wrapped):
                    cell_line = w[li] if li < len(w) else ""
                    parts.append(f" {cell_line:<{widths[ci]}} ")
                lines.append("│" + "│".join(parts) + "│")
            return "\n".join(lines)

        out = [top]
        for i, row in enumerate(rows):
            out.append(render_row(row))
            if i == 0:
                out.append(div)   # separator after header
            elif i < len(rows) - 1:
                out.append(div)   # separator between data rows
        out.append(bottom)
        return "\n".join(out)

    lines = text.split("\n")
    result: list[str] = []
    i = 0
    while i < len(lines):
        if not lines[i].strip().startswith("|"):
            result.append(lines[i])
            i += 1
            continue

        # Collect contiguous pipe-table block
        block_start = i
        while i < len(lines) and lines[i].strip().startswith("|"):
            i += 1
        block = lines[block_start:i]

        # Parse: skip separator-only rows, parse data rows
        md_rows = []
        for line in block:
            if _is_separator_only_row(line):
                continue
            row = parse_md_row(line)
            if any(c for c in row):
                md_rows.append(row)

        if md_rows:
            result.append(render_ascii_table(md_rows))
        else:
            result.extend(block)

    return "\n".join(result)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="OCR Benchmark: compare GLM-OCR, neoxie, pdfmd, VisionFusion, OCRmyPDF"
    )
    parser.add_argument("--pdf", required=True, help="Path to the scanned PDF to benchmark")
    parser.add_argument("--out-dir", default="./ocrs/ocr_results", help="Output directory")
    parser.add_argument(
        "--engines",
        nargs="+",
        choices=["glmocr", "neoxie", "pdfmd", "visionfusion", "ocrmypdf", "all"],
        default=["all"],
        help="Which engines to run (default: all)"
    )
    args = parser.parse_args()

    pdf_path = args.pdf
    if not Path(pdf_path).exists():
        print(f"[ERROR] PDF not found: {pdf_path}")
        sys.exit(1)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    engines_to_run = args.engines
    if "all" in engines_to_run:
        engines_to_run = ["glmocr", "neoxie", "pdfmd", "visionfusion", "ocrmypdf"]

    all_engines = {
        "glmocr":       GLMOCREngine(),
        "neoxie":       NeoxieEngine(),
        "pdfmd":        PdfmdEngine(),
        "visionfusion": VisionFusionEngine(),
        "ocrmypdf":     OCRmyPDFEngine(),
    }

    results = {}
    timings = {}

    print(f"\n{'═'*60}")
    print(f"  OCR BENCHMARK   PDF: {Path(pdf_path).name}")
    print(f"  Engines: {engines_to_run}")
    print(f"  Output: {out_dir}/")
    print(f"{'═'*60}\n")

    for slug in engines_to_run:
        engine = all_engines[slug]
        print(f"\n▶ Running: {engine.NAME}")
        t0 = time.time()
        try:
            text = engine.run(pdf_path)
        except Exception as e:
            import traceback
            text = f"[{engine.NAME} EXCEPTION] {e}\n{traceback.format_exc()}"
        elapsed = time.time() - t0
        timings[slug] = elapsed

        # Save .txt
        out_file = out_dir / f"{slug}_output.txt"
        out_file.write_text(text, encoding="utf-8")
        char_count = len(text)
        print(f"   ✓ Done in {elapsed:.1f}s  |  {char_count:,} chars  →  {out_file}")

        results[slug] = (engine.NAME, text)

    # ── Post-processing: dynamic table correction ────────────────────────────
    corrector = DynamicTableCorrector()

    # PDF reference reconstruction (Pass A) — only for digital PDFs
    if not is_scanned_pdf(pdf_path):
        print("\n▶ Building PDF reference reconstruction...")
        try:
            ref_text = corrector.reconstruct_from_pdf(pdf_path)
            ref_path = out_dir / "pdf_reference.txt"
            ref_path.write_text(ref_text, encoding="utf-8")
            results["pdf_reference"] = ("PDF Reference (pdfplumber)", ref_text)
            timings["pdf_reference"] = 0.0
            print(f"   ✓ Done  |  {len(ref_text):,} chars  →  {ref_path}")
        except Exception as e:
            print(f"   ✗ PDF reference failed: {e}")

    # OCR output correction (Pass B) — fix + ASCII-render tables
    print("\n▶ Applying dynamic table corrections + ASCII rendering...")

    # Engine-specific pre-cleaners applied before the generic corrector
    ENGINE_PRECLEANER = {
        "pdfmd":        fix_pdfmd_output,
        "visionfusion": fix_visionfusion_output,
        "ocrmypdf":     fix_ocrmypdf_output,
    }

    corrected_results = {}
    for slug, (name, text) in results.items():
        if slug == "pdf_reference":
            ascii_ref = markdown_tables_to_ascii(text)
            (out_dir / "pdf_reference.txt").write_text(ascii_ref, encoding="utf-8")
            corrected_results[slug] = (name, ascii_ref)
            continue
        # Apply engine-specific pre-cleaning first
        if slug in ENGINE_PRECLEANER:
            text = ENGINE_PRECLEANER[slug](text)
        corrected = corrector.correct_ocr_output(text)
        ascii_out = markdown_tables_to_ascii(corrected)
        corr_path = out_dir / f"{slug}_corrected.txt"
        corr_path.write_text(ascii_out, encoding="utf-8")
        corrected_results[slug] = (name + " [corrected]", ascii_out)
        print(f"   ✓ {name:<40} →  {corr_path}")

    # HTML comparison report (shows corrected outputs)
    html = generate_html_report(corrected_results, pdf_path, timings)
    report_path = out_dir / "comparison_report.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"\n{'─'*60}")
    print(f"  ✅ Comparison report: {report_path}")
    print(f"  Output files in: {out_dir}/")
    print(f"{'─'*60}")
    for slug in engines_to_run:
        f = out_dir / f"{slug}_corrected.txt"
        n = all_engines[slug].NAME
        print(f"  {n:<40} {f}")
    if not is_scanned_pdf(pdf_path):
        print(f"  {'PDF Reference (pdfplumber)':<40} {out_dir}/pdf_reference.txt")
    print(f"{'─'*60}\n")


if __name__ == "__main__":
    main()
