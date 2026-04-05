"""
database.py
──────────────────────────────────────────────────────────────────────────────
SQLite helpers for document tracking.
Schema:
  documents   – one row per uploaded document, tracks pipeline state
"""

import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent / "docai.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id               TEXT PRIMARY KEY,
                name             TEXT NOT NULL,
                document_type    TEXT DEFAULT 'financial',
                status           TEXT DEFAULT 'pending',
                pipeline_step    TEXT DEFAULT '',
                progress         REAL DEFAULT 0,
                created_at       TEXT,
                completed_at     TEXT,
                error_msg        TEXT,
                pdf_path         TEXT,
                keys_path        TEXT,
                ocr_path         TEXT,
                results_path     TEXT,
                total_keys       INTEGER DEFAULT 0,
                processed_keys   INTEGER DEFAULT 0,
                avg_confidence   REAL DEFAULT 0,
                total_pages      INTEGER DEFAULT 0,
                backend          TEXT DEFAULT 'groq',
                groq_api_key     TEXT DEFAULT ''
            )
        """)
        conn.commit()


# ── CRUD ──────────────────────────────────────────────────────────────────────

def insert_document(doc: dict):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO documents
                (id, name, document_type, status, pipeline_step, progress,
                 created_at, pdf_path, keys_path, backend, groq_api_key)
            VALUES
                (:id, :name, :document_type, :status, :pipeline_step, :progress,
                 :created_at, :pdf_path, :keys_path,
                 :backend, :groq_api_key)
        """, doc)
        conn.commit()


def update_document(doc_id: str, fields: dict):
    if not fields:
        return
    assignments = ", ".join(f"{k} = :{k}" for k in fields)
    fields["doc_id"] = doc_id
    with get_conn() as conn:
        conn.execute(
            f"UPDATE documents SET {assignments} WHERE id = :doc_id",
            fields,
        )
        conn.commit()


def get_document(doc_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
    return dict(row) if row else None


def list_documents(search: str = "", status_filter: str = "", limit: int = 100) -> list:
    query = "SELECT * FROM documents WHERE 1=1"
    params: list = []
    if search:
        query += " AND name LIKE ?"
        params.append(f"%{search}%")
    if status_filter and status_filter != "all":
        query += " AND status = ?"
        params.append(status_filter)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def delete_document(doc_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()


def get_stats() -> dict:
    from datetime import datetime
    
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        completed = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status = 'completed'"
        ).fetchone()[0]
        processing = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status = 'processing'"
        ).fetchone()[0]
        avg_conf_row = conn.execute(
            "SELECT AVG(avg_confidence) FROM documents WHERE status = 'completed'"
        ).fetchone()[0]
        
        # Calculate average processing time PER FIELD (champ)
        processing_data = conn.execute(
            "SELECT created_at, completed_at, total_keys FROM documents WHERE status = 'completed' AND completed_at IS NOT NULL"
        ).fetchall()
        
        avg_processing_time = 0
        if processing_data:
            total_time = 0
            total_fields = 0
            for row in processing_data:
                try:
                    created = datetime.fromisoformat(row[0])
                    completed_dt = datetime.fromisoformat(row[1])
                    duration = (completed_dt - created).total_seconds()
                    total_time += duration
                    total_fields += row[2] or 0
                except:
                    pass
            # Average time per field
            avg_processing_time = round(total_time / total_fields if total_fields > 0 else 0, 2)
        
        by_type = conn.execute(
            "SELECT document_type, COUNT(*) as cnt FROM documents GROUP BY document_type"
        ).fetchall()

    success_rate = round((completed / total * 100) if total > 0 else 0, 1)
    return {
        "total_documents": total,
        "success_rate": success_rate,
        "avg_processing_time": avg_processing_time,
        "processing_count": processing,
        "avg_confidence": round(avg_conf_row or 0, 3),
        "by_type": {r["document_type"]: r["cnt"] for r in by_type},
    }
