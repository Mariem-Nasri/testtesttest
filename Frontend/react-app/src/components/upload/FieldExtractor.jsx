/**
 * FieldExtractor.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * Dynamic form to build and manage extraction fields with complete metadata.
 * Supports: keyName, keyNameDescription, page, value, score
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

export default function FieldExtractor({ fields = [], onChange, onSubmit, isLoading = false, mode = 'standalone' }) {
  const [expandedId, setExpandedId] = useState(null)

  if (!onChange || !onSubmit) {
    console.error('FieldExtractor: onChange and onSubmit are required')
    return null
  }

  const addField = () => {
    onChange([...fields, EMPTY_FIELD()])
  }

  const removeField = (id) => {
    onChange(fields.filter(f => f.id !== id))
  }

  const updateField = (id, key, val) => {
    onChange(fields.map(f => f.id === id ? { ...f, [key]: val } : f))
  }

  const downloadJson = () => {
    const exportData = fields.map(({ keyName, keyNameDescription, page, value, score }) => ({
      keyName,
      keyNameDescription,
      page,
      value,
      score,
    }))
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `extraction_fields_${new Date().getTime()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const canSubmit = () => {
    return fields.length > 0 && fields.every(f => f.keyName?.trim())
  }

  const handleSubmit = () => {
    onSubmit()
  }

  return (
    <div className="field-extractor">
      {/* Header */}
      <div className="d-flex align-items-center justify-content-between mb-4 pb-3 border-bottom">
        <div>
          <h5 className="mb-1">Champs à extraire</h5>
          <p className="text-muted small mb-0">{fields.length} champ(s) défini(s)</p>
        </div>
        <div className="d-flex gap-2">
          {fields.length > 0 && (
            <button
              className="btn btn-sm btn-outline-secondary"
              onClick={downloadJson}
              disabled={isLoading}
              title="Télécharger en JSON"
            >
              <i className="ti ti-download me-1" /> Exporter JSON
            </button>
          )}
          <button
            className="btn btn-sm btn-primary"
            onClick={addField}
            disabled={isLoading}
            title="Ajouter un nouveau champ"
          >
            <i className="ti ti-plus me-1" /> Ajouter un champ
          </button>
        </div>
      </div>

      {/* Fields list */}
      <div className="fields-container">
        {fields.length === 0 ? (
          <div className="empty-state py-5 text-center my-5">
            <div style={{ fontSize: 48, color: 'var(--text-secondary)', marginBottom: 16 }}>
              <i className="ti ti-list-details" />
            </div>
            <h5 className="text-secondary">Aucun champ défini</h5>
            <p className="text-muted mb-4">Commencez par ajouter un premier champ d'extraction</p>
            <button className="btn btn-primary btn-sm" onClick={addField} disabled={isLoading}>
              <i className="ti ti-plus me-1" /> Ajouter un champ
            </button>
          </div>
        ) : (
          fields.map((field, idx) => (
            <div
              key={field.id}
              className="field-card mb-3 p-3 border rounded"
              style={{
                background: 'rgba(255,255,255,0.02)',
                borderColor: 'var(--border-color)',
                transition: 'all 0.2s',
              }}
            >
              {/* Card header with index & actions */}
              <div className="d-flex align-items-center justify-content-between mb-3">
                <div className="d-flex align-items-center gap-2">
                  <span
                    className="badge bg-primary-app"
                    style={{ fontSize: 12, minWidth: 24, textAlign: 'center' }}
                  >
                    {idx + 1}
                  </span>
                  <span className="fw-600" style={{ flex: 1 }}>
                    {field.keyName || 'Nouveau champ'}
                  </span>
                </div>
                <div className="d-flex gap-2 align-items-center">
                  <button
                    className="btn btn-sm btn-ghost"
                    onClick={() => setExpandedId(expandedId === field.id ? null : field.id)}
                    style={{ color: 'var(--text-secondary)' }}
                    disabled={isLoading}
                  >
                    <i
                      className={`ti ti-chevron-${expandedId === field.id ? 'up' : 'down'}`}
                      style={{ fontSize: 16 }}
                    />
                  </button>
                  <button
                    className="btn btn-sm btn-ghost text-danger"
                    onClick={() => removeField(field.id)}
                    title="Supprimer ce champ"
                    disabled={isLoading}
                  >
                    <i className="ti ti-trash" style={{ fontSize: 16 }} />
                  </button>
                </div>
              </div>

              {/* Expanded content */}
              {expandedId === field.id && (
                <div className="field-details">
                  {/* Row 1: keyName (required) */}
                  <div className="mb-3">
                    <label className="form-label small fw-600">
                      Nom du champ <span className="text-danger">*</span>
                    </label>
                    <input
                      type="text"
                      className="form-control form-control-sm"
                      placeholder="ex: Loan Number, Agreement Date, ..."
                      value={field.keyName}
                      onChange={e => updateField(field.id, 'keyName', e.target.value)}
                      disabled={isLoading}
                    />
                    <div className="form-text">Identifiant unique du champ (obligatoire)</div>
                  </div>

                  {/* Row 2: keyNameDescription */}
                  <div className="mb-3">
                    <label className="form-label small fw-600">
                      Description / Contexte
                    </label>
                    <textarea
                      className="form-control form-control-sm"
                      placeholder="Décrivez le contexte ou donnez des indices pour localiser ce champ..."
                      value={field.keyNameDescription}
                      onChange={e => updateField(field.id, 'keyNameDescription', e.target.value)}
                      rows="2"
                      disabled={isLoading}
                      style={{ resize: 'vertical' }}
                    />
                    <div className="form-text">Aide le modèle à mieux identifier le champ</div>
                  </div>

                  {/* Row 3: page & value */}
                  <div className="row g-2 mb-3">
                    <div className="col-6">
                      <label className="form-label small fw-600">
                        Page
                      </label>
                      <input
                        type="text"
                        className="form-control form-control-sm"
                        placeholder="ex: 1, page 1, première page..."
                        value={field.page}
                        onChange={e => updateField(field.id, 'page', e.target.value)}
                        disabled={isLoading}
                      />
                      <div className="form-text">Page où se trouve le champ (optionnel)</div>
                    </div>
                    <div className="col-6">
                      <label className="form-label small fw-600">
                        Valeur
                      </label>
                      <input
                        type="text"
                        className="form-control form-control-sm"
                        placeholder="Valeur extraite (si connue)"
                        value={field.value}
                        onChange={e => updateField(field.id, 'value', e.target.value)}
                        disabled={isLoading}
                      />
                      <div className="form-text">Valeur actuelle (optionnel)</div>
                    </div>
                  </div>

                  {/* Row 4: score */}
                  <div className="mb-3">
                    <label className="form-label small fw-600">
                      Score de confiance
                    </label>
                    <div className="input-group input-group-sm">
                      <input
                        type="number"
                        className="form-control"
                        placeholder="0 - 1 ou 0 - 100"
                        value={field.score}
                        onChange={e => updateField(field.id, 'score', e.target.value)}
                        min="0"
                        max="1"
                        step="0.01"
                        disabled={isLoading}
                      />
                      <span className="input-group-text">%</span>
                    </div>
                    <div className="form-text">Confiance dans l'extraction (0.0 - 1.0 ou 0 - 100)</div>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Submit button */}
      {fields.length > 0 && (
        <div className="mt-4 pt-3 border-top">
          <button
            className="btn btn-primary w-100"
            onClick={handleSubmit}
            disabled={!canSubmit() || isLoading}
            style={{ padding: '10px 20px', fontSize: 15, fontWeight: 600 }}
          >
            {isLoading ? (
              <>
                <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true" />
                Envoi en cours...
              </>
            ) : (
              <>
                <i className="ti ti-send me-2" />
                Envoyer les champs ({fields.length})
              </>
            )}
          </button>
          <p className="text-muted text-center small mt-2 mb-0">
            {!canSubmit() ? '⚠️ Complétez au moins le nom des champs' : 'Les données seront envoyées au serveur'}
          </p>
        </div>
      )}
    </div>
  )
}
