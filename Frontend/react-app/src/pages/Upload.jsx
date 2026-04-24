/**
 * Upload.jsx  — Enhanced
 * ──────────────────────────────────────────────────────────────────────────────
 * 4-step upload wizard:
 *   Step 0 — Upload PDF + choose document type
 *   Step 1 — Upload JSON keys OR manual field builder
 *   Step 2 — Pipeline configuration (backend, thresholds)
 *   Step 3 — Review & launch
 */

import { useState, useCallback }      from 'react'
import { useNavigate }                from 'react-router-dom'
import { useDropzone }                from 'react-dropzone'
import toast                          from 'react-hot-toast'
import PageHeader                     from '../components/common/PageHeader'
import { uploadDocument, analyzeDocument } from '../services/documents'

// ── Accepted file types ────────────────────────────────────────────────────────
const PDF_TYPES  = { 'application/pdf': ['.pdf'], 'image/png': ['.png'], 'image/jpeg': ['.jpg', '.jpeg'], 'image/tiff': ['.tiff'] }
const JSON_TYPES = { 'application/json': ['.json'] }
const MAX_PDF    = 50 * 1024 * 1024  // 50 MB

const DOC_TYPES  = ['Accord de Prêt', 'Rapport Financier', 'Contrat', 'Autre']
const STEPS      = ['Document PDF', 'Champs à extraire', 'Lancer']

export default function Upload() {
  const navigate = useNavigate()

  const [step,        setStep]       = useState(0)
  const [pdfFile,     setPdfFile]    = useState(null)
  const [jsonFile,    setJsonFile]   = useState(null)
  const [parsedKeys,  setParsedKeys] = useState([])   // parsed content of uploaded JSON
  const [jsonMode,    setJsonMode]   = useState('upload')  // 'upload' | 'manual'
  const [fields,      setFields]     = useState([])
  const [docType,     setDocType]    = useState('Accord de Prêt')
  const [submitting,  setSubmitting] = useState(false)

  const DOC_SUBTYPE_MAP = {
    'Accord de Prêt':   'loan',
    'Rapport Financier': 'compliance_report',
    'Contrat':           'isda',
    'Autre':             'loan',
  }

  // ── PDF dropzone ──────────────────────────────────────────────────────────
  const onDropPdf = useCallback((accepted, rejected) => {
    if (rejected.length > 0) {
      const err = rejected[0].errors[0]
      toast.error(err.code === 'file-too-large' ? 'Fichier trop volumineux (max 50 MB)' : 'Format non supporté (PDF, PNG, JPG, TIFF)')
      return
    }
    setPdfFile(accepted[0])
  }, [])

  const { getRootProps: pdfRoot, getInputProps: pdfInput, isDragActive: pdfDrag } =
    useDropzone({ onDrop: onDropPdf, accept: PDF_TYPES, maxSize: MAX_PDF, multiple: false })

  // ── JSON dropzone ─────────────────────────────────────────────────────────
  const onDropJson = useCallback((accepted, rejected) => {
    if (rejected.length > 0) { toast.error('Fichier JSON invalide'); return }
    const file   = accepted[0]
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const parsed = JSON.parse(e.target.result)
        if (!Array.isArray(parsed)) throw new Error('Le JSON doit être un tableau []')
        if (parsed.length > 0 && !parsed[0]?.keyName) throw new Error('Chaque entrée doit avoir un champ "keyName"')
        setJsonFile(file)
        setParsedKeys(parsed)
        toast.success(`${parsed.length} champ(s) chargé(s)`)
      } catch (err) { toast.error(`JSON invalide : ${err.message}`) }
    }
    reader.readAsText(file)
  }, [])

  const { getRootProps: jsonRoot, getInputProps: jsonInput, isDragActive: jsonDrag } =
    useDropzone({ onDrop: onDropJson, accept: JSON_TYPES, multiple: false })

  // ── Navigation ────────────────────────────────────────────────────────────
  function next() {
    if (step === 0 && !pdfFile)                                      { toast.error('Veuillez sélectionner un fichier PDF'); return }
    if (step === 1 && jsonMode === 'upload'   && !jsonFile)           { toast.error('Importez un fichier JSON ou passez en saisie manuelle'); return }
    if (step === 1 && jsonMode === 'manual'   && fields.length === 0) { toast.error('Ajoutez au moins un champ à extraire'); return }
    setStep(s => Math.min(s + 1, STEPS.length - 1))
  }
  function prev() { setStep(s => Math.max(s - 1, 0)) }

  // ── Submit ────────────────────────────────────────────────────────────────
  async function onSubmit() {
    setSubmitting(true)
    try {
      const userKeys = jsonMode === 'upload'
        ? parsedKeys
        : fields.map(({ keyName, keyNameDescription }) => ({ keyName, keyNameDescription: keyNameDescription || '' }))

      const form = new FormData()
      form.append('pdf_file',        pdfFile)
      form.append('doc_subtype',     DOC_SUBTYPE_MAP[docType] || 'loan')
      form.append('extra_keys',      JSON.stringify(userKeys))
      form.append('pipeline_config', '{}')

      const { id } = await uploadDocument(form)
      toast.success('Document uploadé !')
      await analyzeDocument(id)
      toast.success('Pipeline lancé — suivez la progression dans Documents')
      navigate('/documents')
    } catch (err) {
      if (!err.response) {
        toast.error('Impossible de contacter le backend — lancez : uvicorn main:app --reload --port 8000', { duration: 6000 })
      } else if (err.response.status === 401) {
        toast.error('Session expirée — reconnectez-vous')
      } else {
        toast.error(err.response?.data?.detail || `Erreur ${err.response?.status}`)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <PageHeader title="Upload de Document" subtitle="Importez votre PDF et lancez l'extraction en 3 étapes" />

      {/* ── Step indicator ── */}
      <div className="card mb-4">
        <div className="card-body py-3">
          <div className="d-flex align-items-center justify-content-center">
            {STEPS.map((label, idx) => (
              <div key={label} className="d-flex align-items-center">
                <div className="d-flex flex-column align-items-center" style={{ minWidth: 100 }}>
                  <div style={{
                    width: 40, height: 40, borderRadius: '50%',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontWeight: 700, fontSize: 15,
                    background: idx < step ? 'var(--primary)' : idx === step ? 'transparent' : 'rgba(255,255,255,0.04)',
                    border: `2px solid ${idx <= step ? 'var(--primary)' : 'rgba(255,255,255,0.1)'}`,
                    color:  idx < step ? '#fff' : idx === step ? 'var(--primary)' : 'var(--text-secondary)',
                  }}>
                    {idx < step ? <i className="ti ti-check" style={{ fontSize: 16 }} /> : idx + 1}
                  </div>
                  <span style={{ fontSize: 13, fontWeight: 600, marginTop: 6, textAlign: 'center', color: idx <= step ? 'var(--primary)' : '#adb5bd' }}>
                    {label}
                  </span>
                </div>
                {idx < STEPS.length - 1 && (
                  <div style={{ width: 50, height: 2, background: idx < step ? 'var(--primary)' : 'rgba(255,255,255,0.08)', marginBottom: 20, flexShrink: 0 }} />
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ══ STEP 0 — PDF Upload ══ */}
      {step === 0 && (
        <div className="row g-4">
          <div className="col-lg-7">
            <div className="card h-100">
              <div className="card-header d-flex align-items-center gap-2">
                <i className="ti ti-file-type-pdf text-primary-app" />
                Fichier Document
                <span className="badge bg-danger ms-1" style={{ fontSize: 10 }}>Requis</span>
              </div>
              <div className="card-body">
                <div {...pdfRoot()} className={`drop-zone ${pdfDrag ? 'drag-over' : ''} ${pdfFile ? 'has-file' : ''}`}>
                  <input {...pdfInput()} />
                  {pdfFile ? (
                    <>
                      <div className="drop-zone-icon"><i className="ti ti-file-check" style={{ color: 'var(--success)' }} /></div>
                      <div className="fw-600">{pdfFile.name}</div>
                      <div className="drop-zone-hint">{(pdfFile.size / 1024 / 1024).toFixed(2)} MB · Cliquez pour changer</div>
                    </>
                  ) : (
                    <>
                      <div className="drop-zone-icon"><i className="ti ti-cloud-upload" /></div>
                      <div className="fw-600">Glissez votre fichier ici</div>
                      <div className="drop-zone-text">ou cliquez pour parcourir</div>
                      <div className="drop-zone-hint mt-2">PDF, PNG, JPG, TIFF — Max 50 MB</div>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="col-lg-5">
            <div className="card h-100">
              <div className="card-header d-flex align-items-center gap-2">
                <i className="ti ti-tag text-primary-app" />Type de document
              </div>
              <div className="card-body">
                <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  Sélectionnez le type pour catégoriser le document dans le dashboard.
                </p>
                <div className="d-flex flex-column gap-2">
                  {DOC_TYPES.map(t => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setDocType(t)}
                      style={{
                        padding: '10px 16px', borderRadius: 8, textAlign: 'left',
                        border: `2px solid ${docType === t ? 'var(--primary)' : 'var(--border-color)'}`,
                        background: docType === t ? 'rgba(0,167,111,0.1)' : 'rgba(255,255,255,0.03)',
                        color: docType === t ? 'var(--primary)' : 'var(--text-primary)',
                        fontWeight: docType === t ? 600 : 400,
                        fontSize: 13.5, cursor: 'pointer', transition: 'all 0.15s',
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      }}
                    >
                      {t}
                      {docType === t && <i className="ti ti-check" />}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══ STEP 1 — JSON Keys ══ */}
      {step === 1 && (
        <div className="card">
          <div className="card-header d-flex align-items-center gap-2">
            <i className="ti ti-braces text-primary-app" />Champs à extraire
            <span className="badge bg-danger ms-1" style={{ fontSize: 10 }}>Requis</span>
          </div>
          <div className="card-body">
            <div className="btn-group mb-4">
              <button type="button" className={`btn btn-sm ${jsonMode === 'upload' ? 'btn-primary' : 'btn-outline-secondary'}`} onClick={() => setJsonMode('upload')}>
                <i className="ti ti-upload me-1" />Importer JSON
              </button>
              <button type="button" className={`btn btn-sm ${jsonMode === 'manual' ? 'btn-primary' : 'btn-outline-secondary'}`} onClick={() => setJsonMode('manual')}>
                <i className="ti ti-pencil me-1" />Saisie manuelle
              </button>
            </div>

            {jsonMode === 'upload' ? (
              <>
                <div {...jsonRoot()} className={`drop-zone ${jsonDrag ? 'drag-over' : ''} ${jsonFile ? 'has-file' : ''}`} style={{ padding: '28px 20px' }}>
                  <input {...jsonInput()} />
                  {jsonFile ? (
                    <>
                      <div className="drop-zone-icon"><i className="ti ti-file-check" style={{ color: 'var(--success)', fontSize: 32 }} /></div>
                      <div className="fw-600">{jsonFile.name}</div>
                      <div className="drop-zone-hint">Cliquez pour changer</div>
                    </>
                  ) : (
                    <>
                      <div className="drop-zone-icon" style={{ fontSize: 32 }}><i className="ti ti-braces" /></div>
                      <div className="fw-600">Glissez votre fichier JSON</div>
                      <div className="drop-zone-hint mt-1">
                        Format : <code>[&#123;"keyName": "Loan Number", "keyNameDescription": "..."&#125;]</code>
                      </div>
                    </>
                  )}
                </div>

                {/* Format reminder */}
                <div className="alert alert-light border mt-3 d-flex gap-2" style={{ fontSize: 12.5 }}>
                  <i className="ti ti-info-circle mt-1 text-primary-app" />
                  <div>
                    Format attendu : tableau JSON avec les champs <code>keyName</code>, <code>keyNameDescription</code> (optionnel), <code>page</code> (optionnel).
                    Les champs <code>value</code> et <code>score</code> seront remplis par le pipeline.
                  </div>
                </div>
              </>
            ) : (
              // Saisie manuelle — FieldExtractor
              <div style={{ marginTop: 20 }}>
                <div className="mb-3 d-flex justify-content-between align-items-center">
                  <div>
                    <h6 className="mb-0">Champs à extraire</h6>
                    <small className="text-muted">{fields.length} champ(s) défini(s)</small>
                  </div>
                  <button
                    className="btn btn-sm btn-primary"
                    onClick={() => setFields([...fields, { id: Date.now(), keyName: '' }])}
                    disabled={submitting}
                  >
                    <i className="ti ti-plus me-1" /> Ajouter un champ
                  </button>
                </div>

                {fields.length === 0 ? (
                  <div className="text-center py-5" style={{ color: 'var(--text-secondary)' }}>
                    <i className="ti ti-list-details" style={{ fontSize: 48, opacity: 0.3, display: 'block', marginBottom: 16 }} />
                    <p>Aucun champ défini</p>
                    <button
                      className="btn btn-sm btn-primary"
                      onClick={() => setFields([{ id: Date.now(), keyName: '' }])}
                      disabled={submitting}
                    >
                      <i className="ti ti-plus me-1" /> Ajouter un champ
                    </button>
                  </div>
                ) : (
                  <div>
                    {fields.map((field, idx) => (
                      <div key={field.id} className="d-flex gap-2 mb-2" style={{ alignItems: 'center' }}>
                        <span className="badge bg-primary-app">{idx + 1}</span>
                        <input
                          type="text"
                          className="form-control form-control-sm"
                          placeholder="Nom du champ"
                          value={field.keyName}
                          onChange={(e) => setFields(fields.map(f => f.id === field.id ? { ...f, keyName: e.target.value } : f))}
                          disabled={submitting}
                          style={{ flex: 1 }}
                        />
                        <button
                          className="btn btn-sm btn-ghost text-danger"
                          onClick={() => setFields(fields.filter(f => f.id !== field.id))}
                          disabled={submitting}
                          title="Supprimer"
                        >
                          <i className="ti ti-trash" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                <button
                  className="btn btn-primary w-100 mt-3"
                  onClick={() => next()}
                  disabled={fields.length === 0 || !fields.every(f => f.keyName?.trim()) || submitting}
                >
                  <i className="ti ti-arrow-right me-1" />
                  Suivant
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ══ STEP 2 — Review & Launch ══ */}
      {step === 2 && (
        <div className="card">
          <div className="card-header d-flex align-items-center gap-2">
            <i className="ti ti-rocket text-primary-app" />Récapitulatif avant lancement
          </div>
          <div className="card-body">
            <div className="row g-3 mb-4">
              <div className="col-md-4">
                <div className="p-3 rounded-3" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-color)' }}>
                  <div className="fw-600 mb-2" style={{ fontSize: 13 }}><i className="ti ti-file-text me-1 text-primary-app" />Document</div>
                  <div style={{ fontSize: 13 }}>{pdfFile?.name}</div>
                  <div className="text-muted" style={{ fontSize: 12 }}>{(pdfFile?.size / 1024 / 1024).toFixed(2)} MB · {docType}</div>
                </div>
              </div>
              <div className="col-md-4">
                <div className="p-3 rounded-3" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-color)' }}>
                  <div className="fw-600 mb-2" style={{ fontSize: 13 }}><i className="ti ti-braces me-1 text-primary-app" />Champs</div>
                  {jsonMode === 'upload'
                    ? <div style={{ fontSize: 13 }}>{jsonFile?.name}</div>
                    : <div style={{ fontSize: 13 }}>{fields.length} champ(s) défini(s)</div>
                  }
                </div>
              </div>
              <div className="col-md-4">
                <div className="p-3 rounded-3" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-color)' }}>
                  <div className="fw-600 mb-2" style={{ fontSize: 13 }}><i className="ti ti-cpu me-1 text-primary-app" />Pipeline</div>
                  <div style={{ fontSize: 13 }}>4 Agents IA automatiques</div>
                  <div className="text-muted" style={{ fontSize: 12 }}>OCR → Indexation → Extraction → Validation</div>
                </div>
              </div>
            </div>

            {/* Pipeline flow diagram */}
            <div className="alert alert-light border d-flex align-items-center gap-2 flex-wrap" style={{ fontSize: 12.5 }}>
              <i className="ti ti-info-circle text-primary-app" />
              <span>Le pipeline va exécuter :</span>
              {[
                { icon: 'ti-scan',         label: 'OCR',        color: '#2e86ab' },
                { icon: 'ti-database',     label: 'Indexation', color: '#7c3aed' },
                { icon: 'ti-route',        label: 'Router',     color: '#1d6fa0' },
                { icon: 'ti-table',        label: 'Table',      color: '#7c3aed' },
                { icon: 'ti-shield-check', label: 'Validator',  color: '#b45309' },
                { icon: 'ti-book',         label: 'Définitions',color: '#007a52' },
              ].map((s, i, arr) => (
                <span key={s.label} className="d-flex align-items-center gap-1">
                  <span style={{ background: `${s.color}18`, color: s.color, border: `1px solid ${s.color}44`, borderRadius: 6, padding: '2px 8px', fontWeight: 600, fontSize: 12 }}>
                    <i className={`ti ${s.icon} me-1`} />{s.label}
                  </span>
                  {i < arr.length - 1 && <i className="ti ti-chevron-right" style={{ color: '#adb5bd', fontSize: 12 }} />}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Navigation ── */}
      <div className="d-flex justify-content-between mt-4">
        <button className="btn btn-outline-secondary" onClick={prev} disabled={step === 0}>
          <i className="ti ti-arrow-left me-1" />Précédent
        </button>

        {step < STEPS.length - 1 ? (
          <button className="btn btn-primary" onClick={next}>
            Suivant <i className="ti ti-arrow-right ms-1" />
          </button>
        ) : (
          <button className="btn btn-primary px-4" onClick={onSubmit} disabled={submitting}>
            {submitting
              ? <><span className="spinner-border spinner-border-sm me-2" />Traitement...</>
              : <><i className="ti ti-rocket me-1" />Lancer l'extraction</>
            }
          </button>
        )}
      </div>
    </div>
  )
}
