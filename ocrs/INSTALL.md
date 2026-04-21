# OCR Benchmark — Installation Guide

## What you need before running

### 1. System packages

**Ubuntu / Debian:**
```bash
sudo apt-get update
sudo apt-get install -y \
    poppler-utils \          # PDF → image conversion
    tesseract-ocr \          # Tesseract OCR engine
    tesseract-ocr-fra \      # French language pack   
    tesseract-ocr-eng \      # English (usually bundled)
    unpaper \                # Page cleaning for OCRmyPDF
    git
```

**macOS:**
```bash
brew install poppler tesseract tesseract-lang unpaper git
```

**Windows:**
```bash
# Poppler: download from https://github.com/oschwartz10612/poppler-windows/releases
# Add bin/ folder to your PATH

# Tesseract: download installer from https://github.com/UB-Mannheim/tesseract/wiki
# After install, add to PATH and set environment variable:
# TESSDATA_PREFIX=C:\Program Files\Tesseract-OCR\tessdata

conda install -c conda-forge poppler   # alternative for poppler
```

---

### 2. Python packages (auto-installed by script)

The script will auto-install these if missing:
- `pdf2image`
- `pytesseract`
- `Pillow`
- `opencv-python`
- `numpy`
- `pdfplumber`
- `requests`
- `tqdm`
- `ocrmypdf` (for the OCRmyPDF engine)

You can also pre-install everything manually:
```bash
pip install pdf2image pytesseract Pillow opencv-python numpy pdfplumber requests tqdm ocrmypdf
```

---

### 3. Ollama + GLM-OCR model (for engines 1 & 2)

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start the Ollama server
ollama serve &

# Pull the GLM-OCR model (~1.5 GB)
ollama pull glm-ocr
```

> **Note:** If Ollama is not running or the model is not pulled, engines 1 (GLM-OCR)
> and 2 (neoxie) will be automatically skipped with a clear message — they won't crash
> the benchmark.

---

### 4. Repos cloned automatically

When you run the benchmark, these repos are cloned automatically into `./repos/`:
- `https://github.com/neoxie/pdf-to-md-by-local-glmocr` (engine 2)
- `https://github.com/Siggib1054/pdfmd` (engine 3)

You need `git` installed for this.

---

## Running the benchmark

```bash
# Full benchmark (all 5 engines)
python ocr_benchmark.py --pdf OCR_platform/data/input/Test2.pdf

# Run specific engines only
python ocr_benchmark.py --pdf OCR_platform/data/input/Test2.pdf --engines visionfusion ocrmypdf

# Custom output directory
python ocr_benchmark.py --pdf OCR_platform/data/input/Test2.pdf --out-dir ./my_results
```

Available engine IDs: `glmocr`, `neoxie`, `pdfmd`, `visionfusion`, `ocrmypdf`

---

## Output files

After running, `./ocr_results/` will contain:

| File | Description |
|---|---|
| `glmocr_output.txt` | GLM-OCR via Ollama |
| `neoxie_output.txt` | neoxie pdf2md wrapper |
| `pdfmd_output.txt` | Siggib1054/pdfmd |
| `visionfusion_output.txt` | VisionFusion local OCR |
| `ocrmypdf_output.txt` | OCRmyPDF + Tesseract |
| `comparison_report.html` | Side-by-side visual comparison |

Open `comparison_report.html` in your browser to compare all outputs at once.

---

## Notes on each engine

| Engine | Approach | GPU needed? | Internet? |
|---|---|---|---|
| GLM-OCR | Multimodal LLM (0.9B), layout-aware | Recommended | No (local Ollama) |
| neoxie | Wrapper around GLM-OCR via Ollama | Same as above | No |
| pdfmd | Depends on repo content | No | No |
| VisionFusion | Tesseract + dynamic OpenCV thresholding | No | No |
| OCRmyPDF | Tesseract + unpaper + deskew | No | No |

> **VisionFusion note:** The original repo uses Google Gemini for AI-enhanced results.
> This benchmark uses only the local Tesseract pipeline (no API key needed).
> If you want the Gemini-powered version, set `GOOGLE_API_KEY` in your env and
> adapt `visionfusion_output.txt` accordingly.
