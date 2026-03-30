/**
 * Documents.jsx
 * ──────────────────────────────────────────────────────────────────────────────
 * All documents list page with search and filter.
 * No pagination — full list with search/filter only.
 */

import { useEffect, useState, useCallback } from 'react'
import { Link }                             from 'react-router-dom'
import toast                                from 'react-hot-toast'
import PageHeader                           from '../components/common/PageHeader'
import StatusBadge                          from '../components/common/StatusBadge'
import ConfidenceBadge                      from '../components/common/ConfidenceBadge'
import { getDocuments, deleteDocument, reanalyzeDocument } from '../services/documents'
import { formatDate }                       from '../utils/formatters'

// ── Status filter options ─────────────────────────────────────────────────────
const STATUS_OPTIONS = [
  { value: '',           label: 'Tous les statuts' },
  { value: 'completed',  label: 'Terminé' },
  { value: 'processing', label: 'En cours' },
  { value: 'error',      label: 'Erreur' },
  { value: 'pending',    label: 'En attente' },
]

// ── Mock data (dev fallback) ──────────────────────────────────────────────────
const MOCK_DOCS = [
  { id: '00024', name: 'Test2.pdf',           document_type: 'Accord de Prêt',    status: 'completed',  avg_confidence: 0.91, created_at: new Date() },
  { id: '00023', name: 'Report_2024.pdf',     document_type: 'Rapport Financier', status: 'processing', avg_confidence: null, created_at: new Date() },
  { id: '00022', name: 'Contract_Alpha.pdf',  document_type: 'Contrat',           status: 'error',      avg_confidence: null, created_at: new Date() },
  { id: '00021', name: 'Loan_IQ_9240.pdf',    document_type: 'Accord de Prêt',    status: 'completed',  avg_confidence: 0.74, created_at: new Date() },
  { id: '00020', name: 'Annual_Report.pdf',   document_type: 'Rapport Financier', status: 'completed',  avg_confidence: 0.88, created_at: new Date() },
]

export default function Documents() {
  const [allDocs,     setAllDocs]     = useState([])
  const [filtered,    setFiltered]    = useState([])
  const [search,      setSearch]      = useState('')
  const [statusFilter,setStatusFilter]= useState('')
  const [loading,     setLoading]     = useState(true)
  const [deleting,    setDeleting]    = useState(null)

  // ── Load ──────────────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    try {
      const data = await getDocuments({})
      const docs = data.documents || data
      setAllDocs(docs)
      setFiltered(docs)
    } catch {
      setAllDocs(MOCK_DOCS)
      setFiltered(MOCK_DOCS)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // ── Auto-poll while any document is processing ────────────────────────────
  useEffect(() => {
    const hasProcessing = allDocs.some(d => d.status === 'processing')
    if (!hasProcessing) return
    const id = setInterval(load, 4000)
    return () => clearInterval(id)
  }, [allDocs, load])

  // ── Client-side filter ────────────────────────────────────────────────────
  useEffect(() => {
    let result = allDocs
    if (search)       result = result.filter(d => d.name.toLowerCase().includes(search.toLowerCase()) || String(d.id).includes(search))
    if (statusFilter) result = result.filter(d => d.status === statusFilter)
    setFiltered(result)
  }, [search, statusFilter, allDocs])

  // ── Delete ────────────────────────────────────────────────────────────────
  async function handleDelete(doc) {
    if (!window.confirm(`Supprimer "${doc.name}" ?`)) return
    setDeleting(doc.id)
    try {
      await deleteDocument(doc.id)
      setAllDocs(prev => prev.filter(d => d.id !== doc.id))
      toast.success('Document supprimé')
    } catch {
      toast.error('Erreur lors de la suppression')
    } finally {
      setDeleting(null)
    }
  }

  // ── Reanalyze ────────────────────────────────────────────────────────────
  async function handleReanalyze(docId) {
    try {
      await reanalyzeDocument(docId)
      toast.success('Extraction relancée')
      load()
    } catch {
      toast.error('Impossible de relancer')
    }
  }

  return (
    <div>
      <PageHeader
        title="Documents"
        subtitle={`${filtered.length} document(s) trouvé(s)`}
        action={
          <Link to="/upload" className="btn btn-primary">
            <i className="ti ti-plus me-1" /> Nouveau
          </Link>
        }
      />

      {/* ── Filters ── */}
      <div className="card mb-4">
        <div className="card-body py-3">
          <div className="row g-3 align-items-center">
            {/* Search */}
            <div className="col-md-6">
              <div className="search-bar-wrap">
                <i className="ti ti-search" />
                <input
                  type="text"
                  className="form-control"
                  placeholder="Rechercher par nom ou ID..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                />
              </div>
            </div>

            {/* Status filter */}
            <div className="col-md-3">
              <select
                className="form-select"
                style={{ height: 38, fontSize: 13.5, borderRadius: 8 }}
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value)}
              >
                {STATUS_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            {/* Reset */}
            <div className="col-md-3">
              {(search || statusFilter) && (
                <button
                  className="btn btn-outline-secondary btn-sm"
                  onClick={() => { setSearch(''); setStatusFilter('') }}
                >
                  <i className="ti ti-x me-1" /> Réinitialiser
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Table ── */}
      <div className="card">
        <div className="card-body p-0">
          {loading ? (
            <div className="text-center py-5">
              <div className="spinner-border text-primary" role="status" />
              <div className="mt-2 text-muted small">Chargement...</div>
            </div>
          ) : filtered.length === 0 ? (
            <div className="empty-state">
              <i className="ti ti-file-off" />
              <h5>Aucun document trouvé</h5>
              <p>Essayez d'autres critères de recherche ou uploadez un nouveau document</p>
              <Link to="/upload" className="btn btn-primary btn-sm">
                <i className="ti ti-plus me-1" /> Upload document
              </Link>
            </div>
          ) : (
            <div className="table-responsive">
              <table className="table mb-0">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Nom du document</th>
                    <th>Type</th>
                    <th>Date d'upload</th>
                    <th>Statut</th>
                    <th>Confiance moy.</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((doc) => (
                    <tr key={doc.id}>
                      {/* ID */}
                      <td className="doc-id-cell">#{doc.id}</td>

                      {/* Name */}
                      <td>
                        <div className="d-flex align-items-center gap-2">
                          <div style={{
                            width: 32, height: 32,
                            background: 'var(--primary-light)',
                            borderRadius: 7,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            flexShrink: 0,
                          }}>
                            <i className="ti ti-file-text" style={{ color: 'var(--primary)', fontSize: 15 }} />
                          </div>
                          <span className="doc-name-cell">{doc.name}</span>
                        </div>
                      </td>

                      {/* Type */}
                      <td>
                        <span style={{ display:'inline-block', padding:'3px 10px', background:'rgba(255,255,255,0.06)', border:'1px solid rgba(255,255,255,0.1)', borderRadius:6, fontSize:12, fontWeight:500, color:'var(--text-secondary)' }}>
                          {doc.document_type || '—'}
                        </span>
                      </td>

                      {/* Date */}
                      <td style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                        {formatDate(doc.created_at)}
                      </td>

                      {/* Status */}
                      <td><StatusBadge status={doc.status} /></td>

                      {/* Confidence */}
                      <td>
                        {doc.avg_confidence != null
                          ? <ConfidenceBadge score={doc.avg_confidence} />
                          : <span style={{ color: '#adb5bd', fontSize: 12 }}>—</span>
                        }
                      </td>

                      {/* Actions */}
                      <td>
                        <div className="d-flex gap-1">
                          {/* View results */}
                          {doc.status === 'completed' && (
                            <Link
                              to={`/documents/${doc.id}/results`}
                              className="btn btn-sm btn-outline-primary"
                              title="Voir les résultats"
                            >
                              <i className="ti ti-eye" />
                            </Link>
                          )}

                          {/* Relaunch (error/pending) */}
                          {(doc.status === 'error' || doc.status === 'pending') && (
                            <button
                              className="btn btn-sm btn-outline-warning"
                              title="Relancer l'extraction"
                              onClick={() => handleReanalyze(doc.id)}
                            >
                              <i className="ti ti-refresh" />
                            </button>
                          )}

                          {/* Delete */}
                          <button
                            className="btn btn-sm btn-outline-danger"
                            title="Supprimer"
                            onClick={() => handleDelete(doc)}
                            disabled={deleting === doc.id}
                          >
                            {deleting === doc.id
                              ? <span className="spinner-border spinner-border-sm" />
                              : <i className="ti ti-trash" />
                            }
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
