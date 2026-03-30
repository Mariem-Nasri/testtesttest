/**
 * documents.js
 * ──────────────────────────────────────────────────────────────────────────────
 * All document-related API calls mapped to FastAPI endpoints.
 *
 * Endpoints:
 *   POST   /documents/upload          → upload PDF + JSON
 *   POST   /documents/:id/analyze     → trigger pipeline
 *   GET    /documents                 → list (filter + search)
 *   GET    /documents/:id             → document detail
 *   GET    /documents/:id/status      → pipeline status (polling)
 *   GET    /documents/:id/results     → extraction results
 *   DELETE /documents/:id             → delete
 *   GET    /documents/:id/export      → download JSON or CSV
 *   GET    /stats                     → dashboard statistics
 */

import api from './api'

// ── Upload ────────────────────────────────────────────────────────────────────
/**
 * Upload a document (PDF + JSON keys file).
 * @param {FormData} formData  — contains pdf_file, json_file, document_type
 * @returns {{ id, name, status, created_at }}
 */
export async function uploadDocument(formData) {
  const { data } = await api.post('/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

// ── Analyze ───────────────────────────────────────────────────────────────────
/**
 * Trigger the full OCR + multi-agent pipeline.
 * @param {string} docId
 */
export async function analyzeDocument(docId) {
  const { data } = await api.post(`/documents/${docId}/analyze`)
  return data
}

/**
 * Re-trigger analysis on a failed document.
 * @param {string} docId
 */
export async function reanalyzeDocument(docId) {
  const { data } = await api.post(`/documents/${docId}/reanalyze`)
  return data
}

// ── List ──────────────────────────────────────────────────────────────────────
/**
 * Fetch all documents with optional filters.
 * @param {{ search?, filter?, limit? }} params
 * @returns {{ documents: [] }} or []
 */
export async function getDocuments(params = {}) {
  const { data } = await api.get('/documents', { params })
  return data
}

// ── Detail ────────────────────────────────────────────────────────────────────
export async function getDocument(docId) {
  const { data } = await api.get(`/documents/${docId}`)
  return data
}

// ── Status (polling) ──────────────────────────────────────────────────────────
/**
 * Get the current pipeline processing status.
 * @param {string} docId
 * @returns {{ status: 'pending'|'processing'|'completed'|'error', pipeline_step: string, progress: number }}
 */
export async function getDocumentStatus(docId) {
  const { data } = await api.get(`/documents/${docId}/status`)
  return data
}

// ── Results ───────────────────────────────────────────────────────────────────
/**
 * Get extraction results for a completed document.
 * @param {string} docId
 * @returns {{ fields: [{ keyName, value, score, page }], ocr_text, avg_confidence }}
 */
export async function getDocumentResults(docId) {
  const { data } = await api.get(`/documents/${docId}/results`)
  return data
}

// ── Export ────────────────────────────────────────────────────────────────────
/**
 * Export extraction results as JSON or CSV.
 * @param {string} docId
 * @param {'json'|'csv'} format
 * @returns {Blob}
 */
export async function exportResults(docId, format = 'json') {
  const response = await api.get(`/documents/${docId}/export`, {
    params:       { format },
    responseType: 'blob',
  })
  return response.data
}

// ── Delete ────────────────────────────────────────────────────────────────────
export async function deleteDocument(docId) {
  const { data } = await api.delete(`/documents/${docId}`)
  return data
}

// ── Stats (Dashboard) ─────────────────────────────────────────────────────────
/**
 * Get global platform statistics.
 * @returns {{ total_documents, success_rate, avg_processing_time, processing_count, by_type }}
 */
export async function getStats() {
  const { data } = await api.get('/stats')
  return data
}
