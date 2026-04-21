"""
routers/documents.py
──────────────────────────────────────────────────────────────────────────────
All document-related endpoints.

POST   /documents/upload          — upload PDF + select doc type (no JSON file needed)
POST   /documents/{id}/analyze    — trigger pipeline
POST   /documents/{id}/reanalyze  — retry failed doc
GET    /documents                 — list documents
GET    /documents/{id}            — detail
GET    /documents/{id}/status     — pipeline progress (polling)
GET    /documents/{id}/results    — extraction results
GET    /documents/{id}/export     — download JSON or CSV
DELETE /documents/{id}            — delete
GET    /stats                     — dashboard statistics
GET    /templates                 — list allowed doc types for current user's role
"""

import io
import csv
import json
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

import database as db
import pipeline_runner
from auth import oauth2_scheme, get_current_user
from template_registry import (
    load_template, merge_with_extra_keys, get_subtypes_for_role
)

router = APIRouter()

UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")


# ── Auth helper ───────────────────────────────────────────────────────────────

def _require_auth(token: str = Depends(oauth2_scheme)) -> dict:
    return get_current_user(token)


def _doc_or_404(doc_id: str) -> dict:
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    return doc


# ── Templates (role-aware) ────────────────────────────────────────────────────

@router.get("/templates")
async def list_templates(_user: dict = Depends(_require_auth)):
    """Return allowed document subtypes for the current user's role."""
    role     = _user.get("role", "banking")
    subtypes = get_subtypes_for_role(role)
    return {
        "role":     role,
        "subtypes": [
            {"subtype": s["subtype"], "display_name": s["display_name"]}
            for s in subtypes
        ],
    }


# ── Upload (new: doc_subtype + extra_keys, no JSON file needed) ───────────────

class ExtraKey(BaseModel):
    keyName: str
    keyNameDescription: str = ""
    expectedFormat: str = "text"
    searchType: str = ""


@router.post("/documents/upload")
async def upload_document(
    pdf_file:        UploadFile = File(...),
    doc_subtype:     str        = Form("loan"),          # "loan","isda","invoice","compliance_report"
    extra_keys:      str        = Form("[]"),             # JSON array of extra fields
    pipeline_config: str        = Form("{}"),             # {backend, groq_api_key}
    _user: dict = Depends(_require_auth),
):
    """
    Upload a PDF and select doc type from the role-based template.
    No JSON keys file needed — template is loaded automatically.
    Extra fields can be added on top of the template.

    Body (multipart):
      pdf_file        — PDF to extract from
      doc_subtype     — "loan" | "isda" | "invoice" | "compliance_report"
      extra_keys      — JSON array: [{"keyName": "X", "keyNameDescription": "..."}]
      pipeline_config — JSON: {"backend": "ollama"|"groq", "groq_api_key": "..."}
    """
    role = _user.get("role", "banking")

    # ── Parse pipeline config ─────────────────────────────────────────────────
    try:
        cfg = json.loads(pipeline_config) if pipeline_config else {}
    except Exception:
        cfg = {}

    backend      = cfg.get("backend", "groq")
    groq_api_key = cfg.get("groq_api_key", "") or GROQ_API_KEY

    # ── Parse extra keys ──────────────────────────────────────────────────────
    try:
        extra_keys_list = json.loads(extra_keys) if extra_keys else []
        if not isinstance(extra_keys_list, list):
            extra_keys_list = []
    except Exception:
        extra_keys_list = []

    # ── Load role-based template ──────────────────────────────────────────────
    try:
        template = load_template(role, doc_subtype)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # ── Merge template keys + extra keys ──────────────────────────────────────
    merged_keys = merge_with_extra_keys(template["keys"], extra_keys_list)

    # ── Save files ────────────────────────────────────────────────────────────
    doc_id  = str(uuid.uuid4())
    doc_dir = UPLOAD_DIR / doc_id
    doc_dir.mkdir(parents=True)

    pdf_path  = doc_dir / pdf_file.filename
    keys_path = doc_dir / "keys.json"

    pdf_path.write_bytes(await pdf_file.read())
    keys_path.write_text(
        json.dumps({"keys": merged_keys}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    now = datetime.utcnow().isoformat()
    db.insert_document({
        "id":            doc_id,
        "name":          pdf_file.filename,
        "document_type": f"{role}/{doc_subtype}",
        "status":        "pending",
        "pipeline_step": "",
        "progress":      0,
        "created_at":    now,
        "pdf_path":      str(pdf_path),
        "keys_path":     str(keys_path),
        "backend":       backend,
        "groq_api_key":  groq_api_key,
        "doc_subtype":   doc_subtype,
        "user_role":     role,
    })

    return {
        "id":           doc_id,
        "name":         pdf_file.filename,
        "status":       "pending",
        "created_at":   now,
        "doc_subtype":  doc_subtype,
        "total_keys":   len(merged_keys),
        "template_keys": len(template["keys"]),
        "extra_keys":    len(extra_keys_list),
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
        doc_type     = doc.get("doc_subtype", "loan"),
        role         = doc.get("user_role", "banking"),
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
        doc_type     = doc.get("doc_subtype", "loan"),
        role         = doc.get("user_role", "banking"),
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


# ── Status ────────────────────────────────────────────────────────────────────

STEP_LABELS = {
    "":                      "En attente",
    "queued":                "En file d'attente",
    "ocr_processing":        "OCR en cours…",
    "ocr_done":              "OCR terminé",
    "initializing_agents":   "Initialisation des agents…",
    "building_document_map": "Construction de la carte du document…",
    "document_map_ready":    "Carte du document prête",
    "extracting_fields":     "Extraction des champs…",
    "saving_results":        "Sauvegarde des résultats…",
    "completed":             "Terminé",
    "error":                 "Erreur",
}

@router.get("/documents/{doc_id}/status")
async def get_document_status(doc_id: str, _user: dict = Depends(_require_auth)):
    doc  = _doc_or_404(doc_id)
    step = doc.get("pipeline_step", "")
    return {
        "status":         doc["status"],
        "pipeline_step":  step,
        "step_label":     STEP_LABELS.get(step, step),
        "progress":       doc.get("progress", 0),
        "total_keys":     doc.get("total_keys", 0),
        "processed_keys": doc.get("processed_keys", 0),
        "error_msg":      doc.get("error_msg"),
    }


# ── Results ───────────────────────────────────────────────────────────────────

@router.get("/documents/{doc_id}/results")
async def get_document_results(doc_id: str, _user: dict = Depends(_require_auth)):
    doc = _doc_or_404(doc_id)
    if doc["status"] != "completed":
        return {
            "id":             doc_id,
            "name":           doc.get("name"),
            "document_type":  doc.get("document_type"),
            "doc_subtype":    doc.get("doc_subtype"),
            "status":         doc.get("status"),
            "pipeline_step":  doc.get("pipeline_step"),
            "created_at":     doc.get("created_at"),
            "progress":       doc.get("progress", 0),
            "error_msg":      doc.get("error_msg"),
            "fields":         [],
            "ocr_text":       "",
            "avg_confidence": 0,
            "total_pages":    0,
            "total_keys":     0,
        }

    results_path = doc.get("results_path")
    if not results_path or not Path(results_path).exists():
        raise HTTPException(status_code=404, detail="Fichier de résultats introuvable")

    fields   = json.loads(Path(results_path).read_text())
    ocr_text = ""
    if doc.get("ocr_path") and Path(doc["ocr_path"]).exists():
        ocr_text = Path(doc["ocr_path"]).read_text(encoding="utf-8")

    return {
        "id":              doc_id,
        "name":            doc.get("name"),
        "document_type":   doc.get("document_type"),
        "doc_subtype":     doc.get("doc_subtype"),
        "status":          doc.get("status"),
        "pipeline_step":   doc.get("pipeline_step"),
        "created_at":      doc.get("created_at"),
        "avg_confidence":  doc.get("avg_confidence", 0),
        "total_pages":     doc.get("total_pages", 0),
        "total_keys":      len(fields),
        "fields":          fields,
        "ocr_text":        ocr_text,
    }


# ── Export ────────────────────────────────────────────────────────────────────

@router.get("/documents/{doc_id}/export")
async def export_results(
    doc_id: str, format: str = "json",
    _user: dict = Depends(_require_auth),
):
    doc = _doc_or_404(doc_id)
    if doc["status"] != "completed":
        raise HTTPException(status_code=425, detail="Résultats non disponibles")

    results_path = doc.get("results_path")
    if not results_path or not Path(results_path).exists():
        raise HTTPException(status_code=404, detail="Fichier de résultats introuvable")

    fields    = json.loads(Path(results_path).read_text())
    name_stem = Path(doc["name"]).stem

    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["keyName", "value", "score", "page", "expected_format",
                        "format_valid", "reason", "found_in", "rule_context"],
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
    doc_dir = UPLOAD_DIR / doc_id
    if doc_dir.exists():
        import shutil
        shutil.rmtree(doc_dir, ignore_errors=True)
    db.delete_document(doc_id)
    return {"deleted": True, "id": doc_id}


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(_user: dict = Depends(_require_auth)):
    return db.get_stats()
