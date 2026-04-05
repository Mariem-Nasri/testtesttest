"""
routers/documents.py
──────────────────────────────────────────────────────────────────────────────
All document-related endpoints + /stats.

POST   /documents/upload          — upload PDF + JSON keys
POST   /documents/{id}/analyze    — trigger pipeline
POST   /documents/{id}/reanalyze  — retry failed doc
GET    /documents                 — list with optional search/filter
GET    /documents/{id}            — detail
GET    /documents/{id}/status     — pipeline progress (polling)
GET    /documents/{id}/results    — extraction results
GET    /documents/{id}/export     — download JSON or CSV
DELETE /documents/{id}            — delete
GET    /stats                     — dashboard statistics
"""

import io
import csv
import json
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer

import database as db
import pipeline_runner
from auth import oauth2_scheme, get_current_user

router = APIRouter()

UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _doc_or_404(doc_id: str) -> dict:
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    return doc


def _require_auth(token: str = Depends(oauth2_scheme)) -> dict:
    return get_current_user(token)


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/documents/upload")
async def upload_document(
    pdf_file:        UploadFile = File(...),
    json_file:       UploadFile = File(...),
    document_type:   str        = Form("financial"),
    pipeline_config: str        = Form("{}"),   # JSON string from Upload.jsx
    _user: dict = Depends(_require_auth),
):
    """
    Accepts:
      pdf_file        — the PDF to extract from
      json_file       — keys JSON (array or {keys:[...]})
      document_type   — label (default: "financial")
      pipeline_config — JSON string with backend, groq_api_key, thresholds

    Does NOT launch the pipeline — the frontend calls /analyze right after.
    """
    # Parse pipeline config
    try:
        cfg = json.loads(pipeline_config) if pipeline_config else {}
    except Exception:
        cfg = {}

    backend      = cfg.get("backend", "groq")
    groq_api_key = cfg.get("groq_api_key", "") or GROQ_API_KEY

    doc_id   = str(uuid.uuid4())
    doc_dir  = UPLOAD_DIR / doc_id
    doc_dir.mkdir(parents=True)

    # Save uploaded files
    pdf_path  = doc_dir / pdf_file.filename
    keys_path = doc_dir / "keys.json"

    pdf_path.write_bytes(await pdf_file.read())
    keys_bytes = await json_file.read()
    keys_path.write_bytes(keys_bytes)

    # Validate keys JSON before accepting
    try:
        keys_data = json.loads(keys_bytes.decode("utf-8"))
        keys_list = keys_data.get("keys", keys_data) if isinstance(keys_data, dict) else keys_data
        if not isinstance(keys_list, list) or not keys_list:
            raise ValueError("keys list vide ou invalide")
        # Ensure keyName field exists
        if not keys_list[0].get("keyName"):
            raise ValueError("chaque entrée doit avoir un champ 'keyName'")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Fichier JSON invalide: {e}")

    # Wrap flat array in {keys:[...]} for run_pipeline.load_inputs compatibility
    if isinstance(keys_data, list):
        keys_path.write_text(json.dumps({"keys": keys_data}, ensure_ascii=False))

    now = datetime.utcnow().isoformat()
    db.insert_document({
        "id":            doc_id,
        "name":          pdf_file.filename,
        "document_type": document_type,
        "status":        "pending",
        "pipeline_step": "",
        "progress":      0,
        "created_at":    now,
        "pdf_path":      str(pdf_path),
        "keys_path":     str(keys_path),
        "backend":       backend,
        "groq_api_key":  groq_api_key,
    })

    return {
        "id":         doc_id,
        "name":       pdf_file.filename,
        "status":     "pending",
        "created_at": now,
    }


# ── Analyze / Re-analyze ──────────────────────────────────────────────────────

@router.post("/documents/{doc_id}/analyze")
async def analyze_document(doc_id: str, _user: dict = Depends(_require_auth)):
    doc = _doc_or_404(doc_id)
    if doc["status"] == "processing":
        raise HTTPException(status_code=409, detail="Pipeline déjà en cours")

    db.update_document(doc_id, {"status": "processing", "pipeline_step": "queued", "progress": 0})
    pipeline_runner.launch(
        doc_id       = doc_id,
        pdf_path     = doc["pdf_path"],
        keys_path    = doc["keys_path"],
        backend      = doc.get("backend", "groq"),
        groq_api_key = doc.get("groq_api_key", "") or GROQ_API_KEY,
    )
    return {"status": "processing"}


@router.post("/documents/{doc_id}/reanalyze")
async def reanalyze_document(doc_id: str, _user: dict = Depends(_require_auth)):
    doc = _doc_or_404(doc_id)
    db.update_document(doc_id, {
        "status": "processing", "pipeline_step": "queued",
        "progress": 0, "error_msg": None,
    })
    pipeline_runner.launch(
        doc_id       = doc_id,
        pdf_path     = doc["pdf_path"],
        keys_path    = doc["keys_path"],
        backend      = doc.get("backend", "groq"),
        groq_api_key = doc.get("groq_api_key", "") or GROQ_API_KEY,
    )
    return {"status": "processing"}


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/documents")
async def list_documents(
    search: str = "",
    filter: str = "",
    limit:  int = 100,
    _user: dict = Depends(_require_auth),
):
    docs = db.list_documents(search=search, status_filter=filter, limit=limit)
    return {"documents": docs}


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/documents/{doc_id}")
async def get_document(doc_id: str, _user: dict = Depends(_require_auth)):
    return _doc_or_404(doc_id)


# ── Status (polling) ──────────────────────────────────────────────────────────

STEP_LABELS = {
    "":                    "En attente",
    "queued":              "En file d'attente",
    "ocr_processing":      "OCR en cours…",
    "ocr_done":            "OCR terminé",
    "building_index":      "Construction de l'index…",
    "index_ready":         "Index prêt",
    "initializing_agents": "Initialisation des agents…",
    "extracting_fields":   "Extraction des champs…",
    "saving_results":      "Sauvegarde des résultats…",
    "completed":           "Terminé",
    "error":               "Erreur",
}

@router.get("/documents/{doc_id}/status")
async def get_document_status(doc_id: str, _user: dict = Depends(_require_auth)):
    doc = _doc_or_404(doc_id)
    step = doc.get("pipeline_step", "")
    return {
        "status":        doc["status"],
        "pipeline_step": step,
        "step_label":    STEP_LABELS.get(step, step),
        "progress":      doc.get("progress", 0),
        "total_keys":    doc.get("total_keys", 0),
        "processed_keys": doc.get("processed_keys", 0),
        "error_msg":     doc.get("error_msg"),
    }


# ── Results ───────────────────────────────────────────────────────────────────

@router.get("/documents/{doc_id}/results")
async def get_document_results(doc_id: str, _user: dict = Depends(_require_auth)):
    doc = _doc_or_404(doc_id)
    # While still processing, return status-only (no fields yet)
    if doc["status"] != "completed":
        return {
            "id":            doc_id,
            "name":          doc.get("name"),
            "document_type": doc.get("document_type"),
            "status":        doc.get("status"),
            "pipeline_step": doc.get("pipeline_step"),
            "created_at":    doc.get("created_at"),
            "progress":      doc.get("progress", 0),
            "error_msg":     doc.get("error_msg"),
            "fields":        [],
            "ocr_text":      "",
            "avg_confidence": 0,
            "total_pages":   0,
            "total_keys":    0,
        }

    results_path = doc.get("results_path")
    if not results_path or not Path(results_path).exists():
        raise HTTPException(status_code=404, detail="Fichier de résultats introuvable")

    fields = json.loads(Path(results_path).read_text())

    # Read OCR text if available
    ocr_text = ""
    if doc.get("ocr_path") and Path(doc["ocr_path"]).exists():
        ocr_text = Path(doc["ocr_path"]).read_text(encoding="utf-8")

    return {
        # document metadata (needed by Results.jsx for header + polling check)
        "id":              doc_id,
        "name":            doc.get("name"),
        "document_type":   doc.get("document_type"),
        "status":          doc.get("status"),
        "pipeline_step":   doc.get("pipeline_step"),
        "created_at":      doc.get("created_at"),
        "avg_confidence":  doc.get("avg_confidence", 0),
        "total_pages":     doc.get("total_pages", 0),
        "total_keys":      len(fields),
        # extraction results
        "fields":          fields,
        "ocr_text":        ocr_text,
    }


# ── Export ────────────────────────────────────────────────────────────────────

@router.get("/documents/{doc_id}/export")
async def export_results(
    doc_id: str,
    format: str = "json",
    _user: dict = Depends(_require_auth),
):
    doc = _doc_or_404(doc_id)
    if doc["status"] != "completed":
        raise HTTPException(status_code=425, detail="Résultats non disponibles")

    results_path = doc.get("results_path")
    if not results_path or not Path(results_path).exists():
        raise HTTPException(status_code=404, detail="Fichier de résultats introuvable")

    fields = json.loads(Path(results_path).read_text())
    name_stem = Path(doc["name"]).stem

    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["keyName", "value", "score", "page", "expected_format", "format_valid", "reason"],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(fields)
        content = output.getvalue().encode("utf-8")
        return StreamingResponse(
            io.BytesIO(content),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{name_stem}_results.csv"'},
        )

    # Default: JSON
    content = json.dumps(fields, indent=2, ensure_ascii=False).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name_stem}_results.json"'},
    )


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, _user: dict = Depends(_require_auth)):
    doc = _doc_or_404(doc_id)

    # Remove uploaded files
    doc_dir = UPLOAD_DIR / doc_id
    if doc_dir.exists():
        import shutil
        shutil.rmtree(doc_dir, ignore_errors=True)

    db.delete_document(doc_id)
    return {"deleted": True, "id": doc_id}


# ── Extraction Fields ────────────────────────────────────────────────────────

@router.post("/extraction-fields")
async def save_extraction_fields(
    payload: list,
    _user: dict = Depends(_require_auth),
):
    """
    Accepts and saves extraction field definitions (manual form entry).
    
    Request body (JSON array):
      [
        {
          "keyName": "Loan Number",
          "keyNameDescription": "",
          "page": "",
          "value": "",
          "score": ""
        },
        ...
      ]
    
    Returns:
      {
        "status": "saved",
        "count": <number of fields>,
        "fields": [...]
      }
    """
    if not payload:
        raise HTTPException(status_code=422, detail="Fields array required and cannot be empty")
    
    # Validate each field has required keyName
    for idx, field in enumerate(payload):
        if not isinstance(field, dict):
            raise HTTPException(status_code=422, detail=f"Field {idx} must be an object")
        if not field.get("keyName") or not str(field["keyName"]).strip():
            raise HTTPException(status_code=422, detail=f"Field {idx}: keyName is required and cannot be empty")
    
    # Save to file with timestamp
    extraction_dir = UPLOAD_DIR / "extractions"
    extraction_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    extraction_file = extraction_dir / f"extraction_fields_{timestamp}.json"
    
    # Write the fields
    extraction_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    
    # Also save as "latest" for convenience
    latest_file = extraction_dir / "extraction_fields_latest.json"
    latest_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    
    return {
        "status": "saved",
        "count": len(payload),
        "file": str(extraction_file),
        "fields": payload,
    }


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(_user: dict = Depends(_require_auth)):
    return db.get_stats()
