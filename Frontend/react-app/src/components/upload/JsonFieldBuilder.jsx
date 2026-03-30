/**
 * JsonFieldBuilder.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Dynamic form to build extraction fields manually.
 * Mirrors the JSON structure of Test2_pipeline_input.json:
 *   { keyName, keyNameDescription, page, value, score }
 *
 * Props:
 *   fields:   array of field objects
 *   onChange: (updatedFields) => void
 */

import { useState } from 'react'

const EMPTY_FIELD = () => ({
  id:                 Date.now() + Math.random(),
  keyName:            '',
  keyNameDescription: '',
  page:               '',
  value:              '',
  score:              '',
})

export default function JsonFieldBuilder({ fields, onChange }) {
  function addField() {
    onChange([...fields, EMPTY_FIELD()])
  }

  function removeField(id) {
    onChange(fields.filter(f => f.id !== id))
  }

  function updateField(id, key, value) {
    onChange(fields.map(f => f.id === id ? { ...f, [key]: value } : f))
  }

  function downloadJson() {
    // Export fields in the same format as Test2_pipeline_input.json
    const exportData = fields.map(({ keyName, keyNameDescription, page }) => ({
      keyName, keyNameDescription, page, value: '', score: '',
    }))
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = 'extraction_fields.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      {/* Header */}
      <div className="d-flex align-items-center justify-content-between mb-3">
        <span className="text-muted small">{fields.length} champ(s)</span>
        <div className="d-flex gap-2">
          {fields.length > 0 && (
            <button className="btn btn-sm btn-outline-secondary" onClick={downloadJson}>
              <i className="ti ti-download me-1" /> Exporter JSON
            </button>
          )}
          <button className="btn btn-sm btn-primary" onClick={addField}>
            <i className="ti ti-plus me-1" /> Ajouter un champ
          </button>
        </div>
      </div>

      {/* Column labels */}
      {fields.length > 0 && (
        <div className="row g-2 mb-1 px-1" style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          <div className="col-1" />
          <div className="col-4">Nom du champ *</div>
          <div className="col-4">Description (optionnel)</div>
          <div className="col-2">Page (optionnel)</div>
          <div className="col-1" />
        </div>
      )}

      {/* Field list */}
      <div>
        {fields.map((field, idx) => (
          <div key={field.id} className="field-item">
            {/* Drag handle (visual only) */}
            <span className="field-drag-handle">
              <i className="ti ti-grip-vertical" />
            </span>

            {/* Index */}
            <span style={{ fontSize: 12, color: '#adb5bd', minWidth: 20 }}>
              {idx + 1}
            </span>

            {/* keyName */}
            <input
              className="form-control form-control-sm"
              placeholder="ex: Loan Number"
              value={field.keyName}
              onChange={e => updateField(field.id, 'keyName', e.target.value)}
              style={{ flex: 2 }}
            />

            {/* keyNameDescription */}
            <input
              className="form-control form-control-sm"
              placeholder="Description ou indice contextuel"
              value={field.keyNameDescription}
              onChange={e => updateField(field.id, 'keyNameDescription', e.target.value)}
              style={{ flex: 2 }}
            />

            {/* page hint */}
            <input
              className="form-control form-control-sm"
              placeholder="Page"
              value={field.page}
              onChange={e => updateField(field.id, 'page', e.target.value)}
              style={{ flex: 0.6, minWidth: 64 }}
            />

            {/* Delete */}
            <button
              className="btn btn-sm btn-ghost text-danger p-1"
              onClick={() => removeField(field.id)}
              title="Supprimer"
            >
              <i className="ti ti-trash" style={{ fontSize: 16 }} />
            </button>
          </div>
        ))}
      </div>

      {/* Empty state */}
      {fields.length === 0 && (
        <div className="empty-state py-5">
          <i className="ti ti-list-details" />
          <h5>Aucun champ défini</h5>
          <p>Cliquez sur "Ajouter un champ" pour commencer</p>
          <button className="btn btn-primary btn-sm" onClick={addField}>
            <i className="ti ti-plus me-1" /> Ajouter un champ
          </button>
        </div>
      )}
    </div>
  )
}
